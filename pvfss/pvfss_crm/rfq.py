"""Request for Quotation helpers (RFQ-01 to RFQ-03, SUP-03 flag, SCR-RFQ-02/03)."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from pvfss.pvfss_crm import inquiry as inq
from pvfss.pvfss_crm import supplier_rules
from pvfss.utils.line_import import template_response

OPEN_FOR_RFQ = (inq.NEW, inq.RFQ_SENT, inq.QUOTES_RECEIVED, inq.UNDER_EVALUATION)


# ----------------------------------------------------------------------------- RFQ-01
@frappe.whitelist()
def make_rfq(inquiry: str):
	"""Map the inquiry lines (with GEN-50 fields) to a new draft RFQ linked to the inquiry."""
	from erpnext.crm.doctype.opportunity.opportunity import make_request_for_quotation

	source = frappe.get_doc("Opportunity", inquiry)
	source.check_permission("read")
	if (source.pvfss_stage or inq.NEW) not in OPEN_FOR_RFQ:
		frappe.throw(_("An RFQ cannot be created for an inquiry at stage {0}.").format(_(source.pvfss_stage)))
	if not source.items:
		frappe.throw(_("Add inquiry lines before creating an RFQ."))
	inq.assert_not_unconfirmed_duplicate(source)

	rfq = make_request_for_quotation(inquiry)
	rfq.opportunity = inquiry
	rfq.company = source.company
	rfq.transaction_date = nowdate()
	if source.pvfss_bid_due_date:
		due = add_days(getdate(source.pvfss_bid_due_date), -2)
		rfq.pvfss_supplier_due_date = max(due, getdate(nowdate()))
	rfq.schedule_date = rfq.pvfss_supplier_due_date or add_days(nowdate(), 7)
	for row in rfq.items:
		row.schedule_date = rfq.schedule_date
		if not (row.uom and row.stock_uom):
			stock_uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
			row.stock_uom = row.stock_uom or stock_uom
			row.uom = row.uom or stock_uom
			row.conversion_factor = row.conversion_factor or 1
	if not rfq.message_for_supplier:
		rfq.message_for_supplier = _("Please quote for the attached lines by {0}.").format(
			frappe.utils.formatdate(rfq.pvfss_supplier_due_date or rfq.schedule_date)
		)
	return rfq


# ----------------------------------------------------------------------------- SUP-03 flag
def categories_of(rows):
	return sorted({r.get("pvfss_product_category") or r.get("item_group") for r in rows if r} - {None, ""})


def avl_flag(client_project, supplier, categories):
	if not supplier_rules.avl_required(client_project):
		return "Not required"
	return "Not on AVL" if supplier_rules.avl_gaps(client_project, supplier, categories) else "On AVL"


def client_project_of(inquiry):
	return inquiry and frappe.db.get_value("Opportunity", inquiry, "pvfss_client_project")


# ----------------------------------------------------------------------------- RFQ-02
@frappe.whitelist()
def suggest_suppliers(
	categories: str | list,
	client_project: str | None = None,
	only_approved: int | str = 0,
	only_avl: int | str = 0,
):
	"""Suppliers whose Product Categories cover the RFQ lines (SCR-RFQ-03)."""
	if isinstance(categories, str):
		categories = json.loads(categories)
	categories = [c for c in categories or [] if c]
	frappe.has_permission("Supplier", "read", throw=True)
	wanted = {c: {c, *_ancestors(c)} for c in categories}
	rows = frappe.get_all(
		"Supplier Product Category",
		filters={"parenttype": "Supplier", "approved": 1},
		fields=["parent", "product_category"],
	)
	covered = {}
	for row in rows:
		for cat, accepted in wanted.items():
			if row.product_category in accepted:
				covered.setdefault(row.parent, set()).add(cat)

	out = []
	for supplier, cats in covered.items():
		info = frappe.db.get_value(
			"Supplier",
			supplier,
			["supplier_name", "pvfss_approval_status", "pvfss_approval_remarks", "disabled"],
			as_dict=True,
		)
		if not info or info.disabled:
			continue
		blocked = info.pvfss_approval_status in supplier_rules.BLOCKED
		flag = avl_flag(client_project, supplier, cats)
		if frappe.utils.cint(only_approved) and info.pvfss_approval_status not in (
			"Approved",
			supplier_rules.CONDITIONAL,
		):
			continue
		if frappe.utils.cint(only_avl) and flag == "Not on AVL":
			continue
		last_quote = frappe.db.get_value(
			"Supplier Quotation",
			{"supplier": supplier, "docstatus": 1},
			"transaction_date",
			order_by="transaction_date desc",
		)
		out.append(
			{
				"supplier": supplier,
				"supplier_name": info.supplier_name,
				"categories": [{"category": c, "covered": c in cats} for c in categories],
				"covered": len(cats),
				"total": len(categories),
				"approval_status": info.pvfss_approval_status,
				"remarks": info.pvfss_approval_remarks,
				"blocked": blocked,
				"avl": flag,
				"last_quote": last_quote,
				"lowest_share": lowest_share(supplier),
			}
		)
	out.sort(key=lambda r: (r["blocked"], -r["covered"], r["supplier_name"] or ""))
	return out


def _ancestors(item_group):
	return supplier_rules._ancestors(item_group)


def lowest_share(supplier):
	"""Share of inquiries this supplier quoted on where it had the lowest line price (approx.)."""
	quoted = frappe.db.sql(
		"""select count(distinct opportunity) from `tabSupplier Quotation`
		where supplier=%s and docstatus=1 and ifnull(opportunity,'')!=''""",
		supplier,
	)[0][0]
	if not quoted:
		return 0
	lowest = frappe.db.sql(
		"""select count(distinct sq.opportunity)
		from `tabSupplier Quotation Item` sqi
		join `tabSupplier Quotation` sq on sq.name = sqi.parent
		where sq.supplier=%(s)s and sq.docstatus=1 and ifnull(sq.opportunity,'')!=''
		and sqi.pvfss_no_quote=0 and sqi.base_rate > 0
		and sqi.base_rate <= (
			select min(o.base_rate) from `tabSupplier Quotation Item` o
			join `tabSupplier Quotation` osq on osq.name = o.parent
			where osq.opportunity = sq.opportunity and osq.docstatus=1 and o.pvfss_no_quote=0
			and o.base_rate > 0 and o.pvfss_customer_line_ref = sqi.pvfss_customer_line_ref
		)""",
		{"s": supplier},
	)[0][0]
	return round(lowest * 100.0 / quoted, 1)


# ----------------------------------------------------------------------------- RFQ-06 source
SUPPLIER_COLUMNS = [
	("pvfss_customer_line_ref", "Line Ref"),
	("item_code", "Item Code"),
	("pvfss_specification", "Specification"),
	("qty", "Qty"),
	("uom", "UOM"),
	("rate", "Unit Price"),
	("lead_time_days", "Lead Time Days"),
	("pvfss_availability", "Availability"),
	("pvfss_manufacturer", "Manufacturer"),
	("pvfss_origin", "Origin"),
	("pvfss_compliance", "Compliance"),
	("pvfss_deviation_note", "Deviation Note"),
	("pvfss_no_quote", "No Quote"),
]


@frappe.whitelist()
def download_supplier_excel(rfq: str):
	"""RFQ lines as an Excel the supplier can price (the RFQ-06 import reads it back)."""
	doc = frappe.get_doc("Request for Quotation", rfq)
	doc.check_permission("read")
	rows = [
		[
			r.pvfss_customer_line_ref,
			r.item_code,
			r.pvfss_specification or r.description,
			r.qty,
			r.uom,
			*([""] * 8),
		]
		for r in doc.items
	]
	template_response(f"{doc.name} - price sheet.xlsx", SUPPLIER_COLUMNS, rows)
