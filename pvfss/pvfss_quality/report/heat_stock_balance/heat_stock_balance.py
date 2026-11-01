"""Heat Stock Balance (SMR-31, SCR-SMR-08): stock by warehouse, item, batch and heat number."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), data(filters)


def columns():
	return [
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 180,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "batch", "label": _("Batch"), "fieldtype": "Link", "options": "Batch", "width": 160},
		{
			"fieldname": "heat",
			"label": _("Heat Number"),
			"fieldtype": "Link",
			"options": "Heat Number",
			"width": 140,
		},
		{"fieldname": "lot_no", "label": _("Lot No"), "fieldtype": "Data", "width": 80},
		{"fieldname": "heat_status", "label": _("Heat Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "mtc_no", "label": _("MTC No"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "supplier_po",
			"label": _("Supplier PO"),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 140,
		},
		{"fieldname": "balance", "label": _("Balance Qty"), "fieldtype": "Float", "width": 110},
	]


def data(filters):
	from frappe.query_builder.functions import Sum

	sbe = frappe.qb.DocType("Serial and Batch Entry")
	batch = frappe.qb.DocType("Batch")
	heat = frappe.qb.DocType("Heat Number")
	query = (
		frappe.qb.from_(sbe)
		.join(batch)
		.on(batch.name == sbe.batch_no)
		.left_join(heat)
		.on(heat.name == batch.pvfss_heat_number)
		.select(
			sbe.warehouse,
			batch.item.as_("item_code"),
			batch.name.as_("batch"),
			batch.pvfss_heat_number.as_("heat"),
			batch.pvfss_lot_no.as_("lot_no"),
			batch.pvfss_heat_status.as_("heat_status"),
			heat.primary_mtc.as_("mtc_no"),
			batch.pvfss_supplier_po.as_("supplier_po"),
			Sum(sbe.qty).as_("balance"),
		)
		.where((sbe.is_cancelled == 0) & (sbe.docstatus == 1))
		.groupby(sbe.warehouse, batch.name)
		.orderby(batch.pvfss_heat_number)
		.orderby(batch.name)
		.orderby(sbe.warehouse)
	)
	for key, column in (
		("warehouse", sbe.warehouse),
		("item_code", batch.item),
		("heat_number", batch.pvfss_heat_number),
		("supplier_po", batch.pvfss_supplier_po),
		("batch", batch.name),
	):
		if filters.get(key):
			query = query.where(column == filters.get(key))
	rows = query.run(as_dict=True)
	if not filters.get("show_zero"):
		rows = [r for r in rows if abs(flt(r.balance)) > 0.0001]
	return rows
