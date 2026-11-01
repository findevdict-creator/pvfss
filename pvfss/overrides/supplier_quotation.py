"""Supplier Quotation doc events (RFQ-04, RFQ-05, RFQ-08, RFQ-09, CRM-07)."""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pvfss.gates.base import GateResult
from pvfss.overrides import opportunity as opportunity_events
from pvfss.pvfss_crm import selection, supplier_rules

NEEDS_NOTE = ("Deviation", "Not compliant")


def before_validate(doc, method=None):
	"""Runs before ERPNext recalculates totals, so negotiated rates flow into the amounts."""
	apply_negotiation_rounds(doc)


def validate(doc, method=None):
	check_supplier(doc)
	for row in doc.items:
		if cint(row.pvfss_no_quote):
			row.pvfss_selected = 0
		if row.pvfss_compliance in NEEDS_NOTE and not (row.pvfss_deviation_note or "").strip():
			frappe.throw(
				_("Line {0}: enter a deviation note for a {1} line.").format(
					row.pvfss_customer_line_ref or row.idx, _(row.pvfss_compliance)
				)
			)
	selection.assert_single_selection(doc)
	doc.pvfss_lines_quoted = sum(1 for r in doc.items if selection.is_quoted(r_dict(r)))
	doc.pvfss_lines_selected = sum(1 for r in doc.items if cint(r.pvfss_selected))
	if selection.validity_passed(doc.valid_till):
		frappe.msgprint(_("Validity date has passed."), indicator="orange", alert=True)


def r_dict(row):
	return frappe._dict(no_quote=row.pvfss_no_quote, rate=row.rate)


def check_supplier(doc):
	result = GateResult(_("Supplier not allowed"), doc=doc, gate="SUP-07")
	supplier_rules.check_status(result, doc.supplier)
	result.throw_if_failed()


def apply_negotiation_rounds(doc):
	"""RFQ-09: each new round row updates its line's rate and lead time; the old values are
	kept on the row (and in Track Changes)."""
	rounds = doc.get("pvfss_negotiation_rounds") or []
	if not rounds or doc.docstatus != 0:
		return
	lines = {}
	for row in doc.items:
		lines.setdefault(str(row.pvfss_customer_line_ref or ""), row)
	last_round = max([cint(r.round_no) for r in rounds] or [0])
	pending = [r for r in rounds if not cint(r.applied)]
	if not pending:
		return
	this_round = last_round + 1 if all(not cint(r.round_no) for r in pending) else None
	for r in pending:
		line = lines.get(str(r.line_ref or ""))
		if not line:
			frappe.throw(_("Negotiation round: line {0} is not on this quotation.").format(r.line_ref))
		r.round_no = cint(r.round_no) or this_round or last_round + 1
		r.previous_price = flt(line.rate)
		r.previous_lead_time = cint(line.lead_time_days)
		if r.revised_price:
			line.rate = flt(r.revised_price)
			line.price_list_rate = 0
			line.discount_percentage = 0
			line.margin_rate_or_amount = 0
		if r.revised_lead_time:
			line.lead_time_days = cint(r.revised_lead_time)
		r.applied = 1


def before_submit(doc, method=None):
	"""RFQ-05 [RULE] completeness: every line not marked No quote needs rate, lead time,
	availability and compliance."""
	result = GateResult(_("Supplier quotation incomplete"), doc=doc, gate="RFQ-05")
	for row in doc.items:
		if cint(row.pvfss_no_quote):
			continue
		missing = []
		if not flt(row.rate):
			missing.append(_("rate"))
		if not cint(row.lead_time_days):
			missing.append(_("lead time"))
		if not row.pvfss_availability:
			missing.append(_("availability"))
		if not row.pvfss_compliance:
			missing.append(_("compliance"))
		if missing:
			result.fail(
				_("Line {0}: {1} missing. Fill it in or tick No quote.").format(
					row.pvfss_customer_line_ref or row.idx, ", ".join(missing)
				),
				rule="RFQ-05",
			)
	result.throw_if_failed()


def on_submit(doc, method=None):
	opportunity_events.on_supplier_quotation_submit(doc, method)


def on_cancel(doc, method=None):
	for row in doc.items:
		if cint(row.pvfss_selected):
			frappe.db.set_value("Supplier Quotation Item", row.name, "pvfss_selected", 0)
	frappe.db.set_value("Supplier Quotation", doc.name, "pvfss_lines_selected", 0)
