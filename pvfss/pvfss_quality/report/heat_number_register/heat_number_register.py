# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
"""Heat Number Register (TRC-12, SCR-TRC-06): one row per heat with MTC age and quantities."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, month_diff, nowdate

# Hooks for later modules: fn(heats) -> {heat: {column: value}} (MTC status, released qty, open NCRs)
EXTRA_COLUMNS = []


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), data(filters)


def columns():
	return [
		{"fieldname": "heat", "label": _("Heat"), "fieldtype": "Link", "options": "Heat Number", "width": 160},
		{"fieldname": "manufacturer", "label": _("Manufacturer"), "fieldtype": "Link", "options": "Manufacturer", "width": 140},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "grade", "label": _("Grade"), "fieldtype": "Data", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 80},
		{"fieldname": "mtc_no", "label": _("MTC No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "mtc_date", "label": _("MTC Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "mtc_age", "label": _("MTC Age (months)"), "fieldtype": "Int", "width": 90},
		{"fieldname": "mtc_status", "label": _("MTC Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "qty_received", "label": _("Qty Received"), "fieldtype": "Float", "width": 100},
		{"fieldname": "qty_released", "label": _("Qty Released"), "fieldtype": "Float", "width": 100},
		{"fieldname": "qty_shipped", "label": _("Qty Shipped"), "fieldtype": "Float", "width": 100},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Float", "width": 100},
		{"fieldname": "open_ncrs", "label": _("Open NCRs"), "fieldtype": "Int", "width": 80},
	]


def data(filters):
	conditions = {}
	for key in ("manufacturer", "item_code", "status"):
		if filters.get(key):
			conditions[key] = filters[key]
	if filters.get("supplier_po") or filters.get("project"):
		batch_filters = {"pvfss_heat_number": ["is", "set"]}
		if filters.get("supplier_po"):
			batch_filters["pvfss_supplier_po"] = filters.supplier_po
		if filters.get("project"):
			pos = frappe.get_all("Purchase Order", filters={"project": filters.project}, pluck="name")
			batch_filters["pvfss_supplier_po"] = ["in", pos or [""]]
		heats = frappe.get_all("Batch", filters=batch_filters, pluck="pvfss_heat_number", distinct=True)
		conditions["name"] = ["in", heats or [""]]
	rows = frappe.get_all(
		"Heat Number",
		filters=conditions,
		fields=[
			"name", "manufacturer", "item_code", "grade", "status", "primary_mtc", "mtc_date",
			"qty_received", "qty_shipped", "balance_qty",
		],
		order_by="name",
	)
	today = getdate(nowdate())
	out = []
	for r in rows:
		out.append(
			{
				"heat": r.name,
				"manufacturer": r.manufacturer,
				"item_code": r.item_code,
				"grade": r.grade,
				"status": _(r.status),
				"mtc_no": r.primary_mtc,
				"mtc_date": r.mtc_date,
				"mtc_age": max(month_diff(today, r.mtc_date) - 1, 0) if r.mtc_date else None,
				"qty_received": flt(r.qty_received),
				"qty_shipped": flt(r.qty_shipped),
				"balance": flt(r.balance_qty),
				"open_ncrs": 0,
			}
		)
	by_heat = {r["heat"]: r for r in out}
	for path in EXTRA_COLUMNS:
		for heat, values in (frappe.get_attr(path)(list(by_heat)) or {}).items():
			if heat in by_heat:
				by_heat[heat].update(values)
	return out
