"""Supplier PO (Purchase Order) doc events: G3 (PUR-02 to PUR-10, SUP-03, SUP-07)."""

import frappe
from frappe import _
from frappe.utils import escape_html

from pvfss.gates import g3
from pvfss.gates.base import GateResult
from pvfss.pvfss_crm import supplier_rules


def validate(doc, method=None):
	if doc.get("amended_from") and not (doc.get("pvfss_amendment_reason") or "").strip():
		frappe.throw(_("Enter the amendment reason (PUR-09)."), frappe.MandatoryError)
	check_supplier(doc)
	g3.check_locked_links(doc)
	g3.check_avl_ref_role(doc)
	g3.refresh(doc)
	return_to_draft_on_change(doc)


def check_supplier(doc):
	"""SUP-07 [RULE]: no PO to a Suspended / Blacklisted supplier; warn for conditional ones."""
	result = GateResult(_("Supplier not allowed"), doc=doc, gate="SUP-07")
	warning = supplier_rules.check_status(result, doc.supplier)
	result.throw_if_failed()
	if warning:
		frappe.msgprint(escape_html(warning), indicator="orange", alert=True)


def return_to_draft_on_change(doc):
	"""Edits that change what was approved send the PO back to Draft."""
	before = doc.get_doc_before_save()
	if doc.docstatus != 0 or not before or doc.get("workflow_state") != g3.APPROVED:
		return
	if before.get("workflow_state") != g3.APPROVED:
		return

	def snapshot(d):
		return sorted(
			(r.item_code, float(r.qty or 0), float(r.rate or 0), str(r.schedule_date)) for r in d.items
		)

	if snapshot(before) != snapshot(doc) or before.get("supplier") != doc.supplier:
		doc.workflow_state = "Draft"
		frappe.msgprint(
			_("The Supplier PO changed after approval and is back in Draft."), indicator="orange", alert=True
		)


def before_submit(doc, method=None):
	g3.refresh(doc)
	g3.check(doc).throw_if_failed()
