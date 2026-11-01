"""Supplier eligibility rules shared by RFQ (06) and Supplier PO (08): SUP-03 and SUP-07.

Messages follow screens SCR-SUP-07.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

BLOCKED = ("Suspended", "Blacklisted")
CONDITIONAL = "Conditionally approved"


def supplier_status(supplier):
	return (
		frappe.db.get_value(
			"Supplier", supplier, ["pvfss_approval_status", "pvfss_approval_remarks"], as_dict=True
		)
		or frappe._dict()
	)


def check_status(result, supplier, rule="SUP-07"):
	"""Add a blocking failure to ``result`` for a Suspended / Blacklisted supplier.

	Returns a warning message for a conditionally approved supplier, else None.
	"""
	info = supplier_status(supplier)
	status = info.pvfss_approval_status
	if status in BLOCKED:
		result.fail(
			_("{0} is {1} and cannot receive RFQs or POs.").format(supplier, _(status)),
			doctype="Supplier",
			name=supplier,
			rule=rule,
		)
	elif status == CONDITIONAL:
		return _("{0} is conditionally approved: {1}").format(
			supplier, info.pvfss_approval_remarks or _("see supplier record")
		)
	return None


def is_on_avl(client_project, supplier, product_category, on_date=None):
	"""True when ``supplier`` is on the client project's AVL for the category (or a parent group)."""
	on_date = getdate(on_date or nowdate())
	categories = [product_category, *_ancestors(product_category)] if product_category else []
	for entry in frappe.get_all(
		"Approved Vendor Entry",
		filters={
			"client_project": client_project,
			"supplier": supplier,
			"product_category": ["in", categories],
		},
		fields=["valid_from", "valid_to"],
	):
		if entry.valid_from and getdate(entry.valid_from) > on_date:
			continue
		if entry.valid_to and getdate(entry.valid_to) < on_date:
			continue
		return True
	return False


def _ancestors(item_group):
	lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return []
	return frappe.get_all("Item Group", filters={"lft": ["<", lft], "rgt": [">", rgt]}, pluck="name")


def avl_required(client_project):
	return bool(client_project and frappe.db.get_value("Client Project", client_project, "avl_required"))


def avl_gaps(client_project, supplier, categories):
	"""Categories for which ``supplier`` is missing from the AVL (empty when AVL not required)."""
	if not avl_required(client_project):
		return []
	return [c for c in sorted({c for c in categories if c}) if not is_on_avl(client_project, supplier, c)]


def avl_message(supplier, client_project, category):
	return _("{0} is not on the {1} AVL for {2}.").format(supplier, client_project, category)
