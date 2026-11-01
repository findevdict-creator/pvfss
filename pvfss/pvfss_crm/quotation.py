"""Customer Quotation from the Costing Sheet, margin and approval route (SQ-01 to SQ-06, ICV-20)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate

from pvfss.gates import g1
from pvfss.pvfss_crm.doctype.technical_evaluation import technical_evaluation as te_module
from pvfss.utils import settings

PBM_ROLE = "Pre-Bidding Manager"
DIR_ROLE = "PVFSS Director"
LINE_FIELDS = (
	"pvfss_customer_line_ref",
	"pvfss_specification",
	"pvfss_material_type",
	"pvfss_product_category",
	"pvfss_inspection_req",
	"pvfss_doc_req",
)


# ----------------------------------------------------------------------------- SQ-01
@frappe.whitelist()
def make_quotation(costing_sheet):
	"""Create a draft Quotation from a submitted Costing Sheet; blocked by G1 (RFQ-12)."""
	cs = frappe.get_doc("Costing Sheet", costing_sheet)
	cs.check_permission("read")
	frappe.has_permission("Quotation", "create", throw=True)
	g1.check(cs).throw_if_failed()

	inquiry = frappe.get_doc("Opportunity", cs.inquiry)
	opp_lines = {r.pvfss_customer_line_ref: r for r in inquiry.items}
	buffer = settings.get_int("quotation_lead_time_buffer_days", 0)

	qtn = frappe.new_doc("Quotation")
	qtn.quotation_to = "Customer"
	qtn.party_name = inquiry.party_name
	qtn.company = inquiry.company
	qtn.opportunity = inquiry.name
	qtn.transaction_date = nowdate()
	qtn.valid_till = add_days(nowdate(), settings.get_int("default_quotation_validity_days", 30))
	qtn.selling_price_list = (
		frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	)
	qtn.pvfss_costing_sheet = cs.name
	qtn.ignore_pricing_rule = 1
	max_lead = 0
	for row in cs.items:
		src = opp_lines.get(row.line_ref) or frappe._dict()
		lead = cint(row.lead_time_days) + buffer
		max_lead = max(max_lead, lead)
		line = {
			"item_code": row.item_code,
			"item_name": src.item_name or frappe.db.get_value("Item", row.item_code, "item_name"),
			"description": src.description or row.specification,
			"qty": row.qty,
			"uom": row.uom or src.uom,
			"rate": flt(row.selling_price),
			"price_list_rate": 0,
			"pvfss_landed_cost": flt(row.landed_unit_cost),
			"pvfss_lead_time_days": lead,
		}
		for field in LINE_FIELDS:
			line[field] = src.get(field)
		line["pvfss_customer_line_ref"] = row.line_ref
		line["pvfss_specification"] = src.get("pvfss_specification") or row.specification
		qtn.append("items", line)
	if max_lead:
		qtn.pvfss_delivery_terms = _("Delivery within {0} days from receipt of PO.").format(max_lead)
	qtn.pvfss_technical_deviations = deviations_text(cs)
	qtn.pvfss_icv_weightage_pct = icv_weightage(inquiry.pvfss_client_project)
	qtn.run_method("set_missing_values")
	return qtn


def deviations_text(cs):
	"""Accepted deviations of the costed lines (Technical Evaluation, Compliant with deviation)."""
	te = te_module.latest_for(cs.inquiry)
	if not te:
		return ""
	costed = {r.supplier_quotation_item: r.line_ref for r in cs.items}
	lines = [
		_("Line {0}: {1}").format(r.line_ref, r.deviation_description)
		for r in te.items
		if r.supplier_quotation_item in costed and r.compliance == "Compliant with deviation"
	]
	return "\n".join(lines)


def icv_weightage(client_project):
	if client_project:
		value = frappe.db.get_value("Client Project", client_project, "icv_weightage_pct")
		if value:
			return flt(value)
	return settings.get_float("default_icv_weightage_pct")


# ----------------------------------------------------------------------------- SQ-02 / SQ-06
def calculate_margin(doc):
	"""Margin of the quotation against the costing landed cost (company currency)."""
	landed = sum(flt(r.pvfss_landed_cost) * flt(r.stock_qty or r.qty) for r in doc.items)
	selling = sum(flt(r.base_net_amount) for r in doc.items)
	for r in doc.items:
		base_rate = flt(r.base_net_rate)
		r.pvfss_line_margin_pct = (
			(base_rate - flt(r.pvfss_landed_cost)) * 100.0 / base_rate
			if base_rate and flt(r.pvfss_landed_cost)
			else 0
		)
	has_costing = bool(doc.get("pvfss_costing_sheet")) and all(flt(r.pvfss_landed_cost) for r in doc.items)
	doc.pvfss_landed_cost = flt(landed, 2)
	doc.pvfss_margin_amount = flt(selling - landed, 2) if has_costing else 0
	doc.pvfss_margin_pct = flt((selling - landed) * 100.0 / selling, 2) if has_costing and selling else 0
	doc.pvfss_approver_role = approver_role(doc.pvfss_margin_pct if has_costing else None)


def approver_role(margin_pct):
	"""SQ-06: at or above the minimum margin a Pre-Bidding Manager approves, below it a Director.

	A quotation without a costing (margin unknown) goes to a Director.
	"""
	if margin_pct is None:
		return DIR_ROLE
	return PBM_ROLE if flt(margin_pct) >= settings.get_float("min_target_margin_pct") else DIR_ROLE


def approval_route_text(doc):
	minimum = settings.get_float("min_target_margin_pct")
	if doc.pvfss_approver_role == PBM_ROLE:
		return _("Approval: Pre-Bidding Manager")
	if not doc.get("pvfss_costing_sheet"):
		return _("Approval: Director - no costing sheet")
	return _("Approval: Director - margin {0}% below {1}%").format(flt(doc.pvfss_margin_pct, 2), minimum)


def calculate_icv(doc):
	"""ICV-20: evaluated price = bid price x (1 - ICV score x weightage)."""
	score = flt(doc.get("pvfss_icv_score_used")) / 100.0
	weight = flt(doc.get("pvfss_icv_weightage_pct")) / 100.0
	doc.pvfss_evaluated_price = flt(flt(doc.grand_total) * (1 - score * weight), 2)


# ----------------------------------------------------------------------------- SQ-04
@frappe.whitelist()
def make_revision(quotation):
	"""Cancel the submitted quotation and return its amendment (QTN-...-1, -2) as a draft."""
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission("cancel")
	if doc.docstatus != 1:
		frappe.throw(_("Only a submitted quotation can be revised."))
	doc.workflow_state = "Cancelled"
	doc.flags.pvfss_revision = True
	doc.cancel()
	new = frappe.copy_doc(doc)
	new.amended_from = doc.name
	new.docstatus = 0
	new.workflow_state = "Draft"
	new.status = "Draft"
	new.insert()
	return new.name
