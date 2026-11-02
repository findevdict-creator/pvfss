"""Quotation doc events (SQ-01 to SQ-06, RFQ-12, ICV-20, CRM-07)."""

import frappe
from frappe import _
from frappe.utils import flt

from pvfss.gates import g1
from pvfss.gates.base import GateResult
from pvfss.overrides import opportunity as opportunity_events
from pvfss.pvfss_crm import quotation as qtn

APPROVED = "Approved"


def validate(doc, method=None):
	qtn.calculate_margin(doc)
	if not doc.get("pvfss_icv_score_used") and doc.docstatus == 0:
		from pvfss.pvfss_icv.icv import current_score

		doc.pvfss_icv_score_used = current_score()  # ICV-20 default
	qtn.calculate_icv(doc)
	if doc.get("pvfss_costing_sheet") and doc.docstatus == 0:
		# RFQ-12 [RULE]: a quotation cannot stand on a non-compliant selection
		g1.check(doc.pvfss_costing_sheet).throw_if_failed()
	return_to_draft_on_change(doc)
	stamp_approver(doc)


def stamp_approver(doc):
	"""Record who moved the quotation to Approved."""
	before = doc.get_doc_before_save()
	if doc.get("workflow_state") == APPROVED and before and before.get("workflow_state") != APPROVED:
		doc.pvfss_approved_by = frappe.session.user


def return_to_draft_on_change(doc):
	"""SCR-SQ-02: rate or qty edits after approval send the quotation back to Draft."""
	before = doc.get_doc_before_save()
	if doc.docstatus != 0 or not before or doc.get("workflow_state") != APPROVED:
		return
	if before.get("workflow_state") != APPROVED:
		return
	old = {(r.name): (flt(r.qty), flt(r.rate), r.item_code) for r in before.items}
	new = {(r.name): (flt(r.qty), flt(r.rate), r.item_code) for r in doc.items}
	if old != new:
		doc.workflow_state = "Draft"
		doc.pvfss_approved_by = None
		frappe.msgprint(
			_("Rates or quantities changed after approval: the quotation is back in Draft."),
			indicator="orange",
			alert=True,
		)


def before_submit(doc, method=None):
	"""G2 [RULE] (SQ-06): only an Approved quotation can be submitted (sent)."""
	before = doc.get_doc_before_save()
	result = GateResult(_("Quotation not approved"), doc=doc, gate="G2")
	result.check(
		before is not None and before.get("workflow_state") == APPROVED,
		_("The quotation must be approved before it is sent ({0}).").format(qtn.approval_route_text(doc)),
		rule="SQ-06",
	)
	result.throw_if_failed()


def before_cancel(doc, method=None):
	"""The Costing Sheet keeps pointing at its quotation; that link must not block a cancel."""
	doc.ignore_linked_doctypes = (*(getattr(doc, "ignore_linked_doctypes", None) or ()), "Costing Sheet")


def after_insert(doc, method=None):
	if doc.get("pvfss_costing_sheet"):
		frappe.db.set_value("Costing Sheet", doc.pvfss_costing_sheet, "quotation", doc.name)


def on_submit(doc, method=None):
	opportunity_events.on_quotation_submit(doc, method)


def on_update_after_submit(doc, method=None):
	opportunity_events.on_quotation_update_after_submit(doc, method)


def onload(doc, method=None):
	if doc.get("pvfss_approver_role"):
		doc.set_onload("pvfss_approval_route", qtn.approval_route_text(doc))
