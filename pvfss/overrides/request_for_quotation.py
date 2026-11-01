"""Request for Quotation doc events (SUP-03, SUP-07, RFQ-01 to RFQ-03, CRM-07)."""

import frappe
from frappe import _
from frappe.utils import escape_html, getdate

from pvfss.gates.base import GateResult
from pvfss.pvfss_crm import inquiry as inq
from pvfss.pvfss_crm import rfq as rfq_helpers
from pvfss.pvfss_crm import supplier_rules


def validate(doc, method=None):
	set_subject(doc)
	check_suppliers(doc)
	flag_avl(doc)
	check_due_date(doc)


def check_suppliers(doc):
	"""SUP-07 [RULE]: no RFQ to a Suspended / Blacklisted supplier; warn for conditional ones."""
	result = GateResult(_("Supplier not allowed"), doc=doc, gate="SUP-07")
	warnings = []
	for row in doc.suppliers or []:
		warning = supplier_rules.check_status(result, row.supplier)
		if warning:
			warnings.append(warning)
	result.throw_if_failed()
	if warnings:
		frappe.msgprint("<br>".join(escape_html(w) for w in warnings), indicator="orange", alert=True)


def set_subject(doc):
	"""SCR-RFQ-04: "RFQ {no} - {contractor ref} - due {date}"."""
	if doc.get("subject") and not doc.get("subject").startswith("Request for Quotation"):
		return
	parts = [f"RFQ {doc.name}"]
	if doc.get("opportunity"):
		ref = frappe.db.get_value("Opportunity", doc.opportunity, "pvfss_contractor_ref")
		if ref:
			parts.append(ref)
	if doc.get("pvfss_supplier_due_date"):
		parts.append(_("due {0}").format(frappe.utils.formatdate(doc.pvfss_supplier_due_date)))
	doc.subject = " - ".join(parts)


def flag_avl(doc):
	"""SUP-03: flag (not block) suppliers missing from the client project's AVL."""
	client_project = rfq_helpers.client_project_of(doc.get("opportunity"))
	categories = rfq_helpers.categories_of([r.as_dict() for r in doc.items or []])
	missing = []
	for row in doc.suppliers or []:
		row.pvfss_avl_flag = rfq_helpers.avl_flag(client_project, row.supplier, categories)
		if row.pvfss_avl_flag == "Not on AVL":
			for category in supplier_rules.avl_gaps(client_project, row.supplier, categories):
				missing.append(supplier_rules.avl_message(row.supplier, client_project, category))
	if missing:
		frappe.msgprint(
			"<br>".join(escape_html(m) for m in missing),
			title=_("Approved Vendor List"),
			indicator="orange",
		)


def check_due_date(doc):
	if not (doc.get("opportunity") and doc.get("pvfss_supplier_due_date")):
		return
	bid_due = frappe.db.get_value("Opportunity", doc.opportunity, "pvfss_bid_due_date")
	if bid_due and getdate(doc.pvfss_supplier_due_date) >= getdate(bid_due):
		frappe.msgprint(
			_("The supplier bid due date should be before the inquiry bid due date ({0}).").format(
				frappe.utils.formatdate(bid_due)
			),
			indicator="orange",
			alert=True,
		)


def on_submit(doc, method=None):
	"""CRM-07: first RFQ submitted moves the inquiry to RFQ Sent."""
	if doc.get("opportunity"):
		inq.advance(doc.opportunity, inq.RFQ_SENT, source=doc.name)


def onload(doc, method=None):
	doc.set_onload("client_project", rfq_helpers.client_project_of(doc.get("opportunity")))
