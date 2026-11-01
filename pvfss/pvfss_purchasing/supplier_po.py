"""Create Supplier POs from a Customer PO (PUR-01, PUR-03, SCR-PUR-03)."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from pvfss.gates import g3
from pvfss.pvfss_crm import selection
from pvfss.utils import settings

GEN50 = (
	"pvfss_customer_line_ref",
	"pvfss_specification",
	"pvfss_material_type",
	"pvfss_product_category",
	"pvfss_inspection_req",
	"pvfss_doc_req",
)


@frappe.whitelist()
def get_plan(sales_order):
	"""One row per Customer PO line with the selected supplier line (RFQ-08) and what is left to order."""
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")
	if so.docstatus != 1:
		frappe.throw(_("Submit the Customer PO before creating Supplier POs."))
	chosen = selection.selected_lines(so.pvfss_inquiry) if so.get("pvfss_inquiry") else {}
	plan = []
	for row in so.items:
		pick = chosen.get(row.pvfss_customer_line_ref)
		ordered = g3.ordered_elsewhere(row.name, None)
		remaining = max(flt(row.stock_qty) - ordered, 0)
		plan.append(
			{
				"so_item": row.name,
				"line_ref": row.pvfss_customer_line_ref,
				"item_code": row.item_code,
				"qty": row.qty,
				"uom": row.uom,
				"supplier": pick.supplier if pick else None,
				"sq_item": pick.sq_item if pick else None,
				"supplier_quotation": pick.supplier_quotation if pick else None,
				"supplier_rate": pick.rate if pick else None,
				"currency": pick.currency if pick else None,
				"lead_time_days": pick.lead_time_days if pick else None,
				"ordered": ordered,
				"qty_to_order": remaining / flt(row.conversion_factor or 1),
			}
		)
	return plan


@frappe.whitelist()
def make_supplier_pos(sales_order, lines=None):
	"""Create one draft Supplier PO per supplier. ``lines``: rows of get_plan (edited)."""
	so = frappe.get_doc("Sales Order", sales_order)
	frappe.has_permission("Purchase Order", "create", throw=True)
	if isinstance(lines, str):
		lines = json.loads(lines)
	lines = lines or get_plan(sales_order)
	by_supplier = {}
	for line in lines:
		if not line.get("supplier") or flt(line.get("qty_to_order")) <= 0:
			continue
		by_supplier.setdefault(line["supplier"], []).append(frappe._dict(line))
	if not by_supplier:
		frappe.throw(_("Pick a supplier and a quantity for at least one line."))

	so_items = {r.name: r for r in so.items}
	created = []
	for supplier, rows in by_supplier.items():
		po = build_po(so, supplier, rows, so_items)
		po.insert()
		created.append(po.name)
	return created


def build_po(so, supplier, rows, so_items):
	buffer = settings.get_int("default_transit_buffer_days", 0)
	po = frappe.new_doc("Purchase Order")
	po.supplier = supplier
	po.company = so.company
	po.transaction_date = nowdate()
	po.pvfss_sales_order = so.name
	po.pvfss_customer_po_no = so.po_no
	po.pvfss_client_project = so.get("pvfss_client_project")
	po.pvfss_payment_method = so.get("pvfss_payment_method")
	po.pvfss_lc_required = 1 if so.get("pvfss_payment_method") == "LC" else 0
	po.pvfss_supplier_retention_pct = frappe.db.get_value("Supplier", supplier, "pvfss_default_retention_pct")
	if so.get("project"):
		po.project = so.project

	quotation = None
	inspection, documents = [], []
	for line in rows:
		so_row = so_items[line.so_item]
		sq = None
		if line.get("sq_item"):
			sq = frappe.db.get_value(
				"Supplier Quotation Item",
				line.sq_item,
				["parent", "rate", "lead_time_days", "uom", "conversion_factor"],
				as_dict=True,
			)
			quotation = quotation or sq.parent
		schedule = schedule_date(so_row, sq, buffer)
		item = {
			"item_code": so_row.item_code,
			"qty": flt(line.qty_to_order),
			"uom": so_row.uom,
			"stock_uom": so_row.stock_uom,
			"conversion_factor": so_row.conversion_factor or 1,
			"schedule_date": schedule,
			"warehouse": so_row.warehouse,
			"sales_order": so.name,
			"sales_order_item": so_row.name,
			"description": so_row.description,
		}
		for field in GEN50:
			item[field] = so_row.get(field)
		if sq:
			item.update(
				{
					"supplier_quotation": sq.parent,
					"supplier_quotation_item": line.sq_item,
					"rate": flt(sq.rate),
					"price_list_rate": 0,
				}
			)
		po.append("items", item)
		if so_row.get("pvfss_inspection_req"):
			inspection.append(f"{so_row.pvfss_customer_line_ref}: {so_row.pvfss_inspection_req}")
		if so_row.get("pvfss_doc_req"):
			documents.append(f"{so_row.pvfss_customer_line_ref}: {so_row.pvfss_doc_req}")

	if quotation:
		head = frappe.db.get_value(
			"Supplier Quotation", quotation, ["currency", "conversion_rate", "incoterm"], as_dict=True
		)
		po.currency = head.currency
		po.conversion_rate = head.conversion_rate
		po.incoterm = head.incoterm
	po.pvfss_inspection_requirements = "\n".join(inspection)
	po.pvfss_document_requirements = "\n".join(documents)
	po.schedule_date = min(getdate(r.schedule_date) for r in po.items)
	po.ignore_pricing_rule = 1
	po.run_method("set_missing_values")
	return po


def schedule_date(so_row, sq, buffer):
	"""Latest date the supplier may deliver: SO line delivery date minus transit buffer, but not
	before today + the quoted lead time."""
	latest = add_days(getdate(so_row.delivery_date), -buffer) if so_row.delivery_date else None
	earliest = add_days(getdate(nowdate()), cint(sq.lead_time_days)) if sq and sq.lead_time_days else None
	if latest and earliest:
		return max(latest, earliest)  # later than the SO allows shows up as a Deviation
	return latest or earliest or getdate(add_days(nowdate(), 7))
