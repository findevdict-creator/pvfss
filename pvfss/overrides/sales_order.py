"""Customer PO (Sales Order) doc events (SQ-07 to SQ-10)."""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pvfss.gates.base import GateResult
from pvfss.overrides import opportunity as opportunity_events
from pvfss.utils import alerts, settings

# SQ-09: which review check covers a difference on each compared field
REVIEW_FOR = {
	"Qty": "Quantities",
	"Rate": "Price",
	"Item": "Scope matches quotation",
	"Specification": "Specification",
	"Line added": "Scope matches quotation",
	"Line removed": "Scope matches quotation",
}
APPROVED = "Approved"
FM_ROLES = ("Finance Manager", "System Manager")


def onload(doc, method=None):
	if doc.is_new() and not doc.get("pvfss_po_review"):
		prefill_review(doc)


def before_validate(doc, method=None):
	if not doc.get("pvfss_po_review"):
		prefill_review(doc)
	set_links(doc)


def validate(doc, method=None):
	from pvfss.pvfss_finance import vc

	check_advance_billing(doc)
	compare_with_quotation(doc)
	vc.estimate(doc)  # FIN-60


def prefill_review(doc):
	"""SQ-08: the review checklist comes from the PVFSS Settings template."""
	for row in settings.get_table("po_review_template"):
		doc.append("pvfss_po_review", {"check_item": row.check_item})


def source_quotation(doc):
	for row in doc.items:
		if row.get("prevdoc_docname"):
			return row.prevdoc_docname
	return None


def set_links(doc):
	quotation = source_quotation(doc)
	if not quotation:
		return
	inquiry = frappe.db.get_value("Quotation", quotation, "opportunity")
	if inquiry:
		doc.pvfss_inquiry = inquiry
		if not doc.get("pvfss_client_project"):
			doc.pvfss_client_project = frappe.db.get_value("Opportunity", inquiry, "pvfss_client_project")


def check_advance_billing(doc):
	before = doc.get_doc_before_save()
	old = cint(before.get("pvfss_advance_billing_allowed")) if before else 0
	if cint(doc.get("pvfss_advance_billing_allowed")) != old and not set(frappe.get_roles()) & set(FM_ROLES):
		frappe.throw(_("Only a Finance Manager can change Advance Billing Allowed."), frappe.PermissionError)


def _fmt(value):
	if isinstance(value, float):
		return frappe.utils.fmt_money(value, precision=2)
	return str(value or "")


def compare_with_quotation(doc):
	"""SQ-09: list every difference between the Customer PO and its quotation, by line ref."""
	doc.set("pvfss_differences", [])
	quotation = source_quotation(doc)
	review = {r.check_item: r for r in doc.get("pvfss_po_review") or []}
	if quotation:
		q_lines = {}
		for r in frappe.get_all(
			"Quotation Item",
			filters={"parent": quotation, "parenttype": "Quotation"},
			fields=["pvfss_customer_line_ref", "qty", "rate", "item_code", "pvfss_specification"],
		):
			q_lines[str(r.pvfss_customer_line_ref or "")] = r
		seen = set()
		for row in doc.items:
			ref = str(row.pvfss_customer_line_ref or "")
			seen.add(ref)
			q = q_lines.get(ref)
			if not q:
				_add(doc, ref, "Line added", "", row.item_code)
				continue
			if flt(q.qty) != flt(row.qty):
				_add(doc, ref, "Qty", flt(q.qty), flt(row.qty), flt(row.qty) - flt(q.qty))
			if flt(q.rate, 2) != flt(row.rate, 2):
				_add(doc, ref, "Rate", flt(q.rate), flt(row.rate), flt(row.rate) - flt(q.rate))
			if q.item_code != row.item_code:
				_add(doc, ref, "Item", q.item_code, row.item_code)
			if (q.pvfss_specification or "").strip() != (row.pvfss_specification or "").strip():
				_add(doc, ref, "Specification", q.pvfss_specification, row.pvfss_specification)
		for ref, q in q_lines.items():
			if ref not in seen:
				_add(doc, ref, "Line removed", q.item_code, "")

	for d in doc.pvfss_differences:
		check = review.get(d.review_item)
		d.reviewed = 1 if check and check.result == "Deviation" and (check.remark or "").strip() else 0

	doc.pvfss_difference_count = len(doc.pvfss_differences)
	doc.pvfss_review_complete = 1 if review and all(r.result for r in review.values()) else 0
	for r in review.values():
		if r.result == "Deviation" and not (r.remark or "").strip():
			frappe.throw(_("PO review: enter a remark for the deviation on '{0}'.").format(r.check_item))
	if not quotation:
		doc.pvfss_review_status = _("No source quotation")
	elif doc.pvfss_difference_count:
		doc.pvfss_review_status = _("{0} differences vs {1}, review required").format(
			doc.pvfss_difference_count, quotation
		)
	else:
		doc.pvfss_review_status = _("Matches quotation {0}").format(quotation)


def _add(doc, ref, field, q_value, po_value, diff=None):
	doc.append(
		"pvfss_differences",
		{
			"line_ref": ref,
			"field": field,
			"quotation_value": _fmt(q_value),
			"po_value": _fmt(po_value),
			"difference": _fmt(diff) if diff is not None else "",
			"review_item": REVIEW_FOR[field],
		},
	)


def before_submit(doc, method=None):
	"""SQ-09 [RULE]: differences reviewed (Deviation with remark) and approved by a POM."""
	compare_with_quotation(doc)
	result = GateResult(_("Customer PO review"), doc=doc, gate="SQ-09")
	result.check(doc.pvfss_review_complete, _("Complete every check of the PO review."), rule="SQ-08")
	for d in doc.pvfss_differences:
		if not d.reviewed:
			result.fail(
				_(
					"Line {0} {1}: quotation {2}, Customer PO {3}. Record a Deviation with remark on '{4}'."
				).format(
					d.line_ref, _(d.field), d.quotation_value or "-", d.po_value or "-", _(d.review_item)
				),
				rule="SQ-09",
			)
	if doc.pvfss_difference_count:
		before = doc.get_doc_before_save()
		result.check(
			before is not None and before.get("workflow_state") == APPROVED,
			_("Differences vs the quotation need Post-Bidding Manager approval."),
			rule="SQ-09",
		)
	result.throw_if_failed()


def on_submit(doc, method=None):
	"""SQ-10: inquiry Won and the Post-Bidding Managers notified."""
	opportunity_events.on_sales_order_submit(doc, method)
	alerts.send(
		alerts.users_with_role("Post-Bidding Manager"),
		_("Customer PO {0} received: {1} ({2}), {3}.").format(
			doc.name,
			doc.customer_name or doc.customer,
			doc.po_no or "-",
			frappe.utils.fmt_money(doc.grand_total, currency=doc.currency),
		),
		"Sales Order",
		doc.name,
	)
