"""Inspection / IRN Release Tracker (QA-35, SCR-QA-20): one row per Supplier PO."""

import frappe
from frappe import _
from frappe.utils import flt

RFI_STATES = ("Raised", "Scheduled", "Inspected", "Closed")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), data(filters)


def columns():
	cols = [
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 130,
		},
		{
			"fieldname": "supplier_po",
			"label": _("Supplier PO"),
			"fieldtype": "Link",
			"options": "Purchase Order",
			"width": 140,
		},
		{
			"fieldname": "supplier",
			"label": _("Supplier"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 150,
		},
		{"fieldname": "points_open", "label": _("ITP Points Open"), "fieldtype": "Int", "width": 90},
		{"fieldname": "points_closed", "label": _("ITP Points Closed"), "fieldtype": "Int", "width": 90},
	]
	cols += [
		{
			"fieldname": f"rfi_{s.lower()}",
			"label": _("RFIs {0}").format(_(s)),
			"fieldtype": "Int",
			"width": 80,
		}
		for s in RFI_STATES
	]
	cols += [
		{"fieldname": "ncrs_open", "label": _("NCRs Open"), "fieldtype": "Int", "width": 80},
		{"fieldname": "po_qty", "label": _("PO Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "irn_qty", "label": _("IRN Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "irn_pct", "label": _("IRN %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "last_irn", "label": _("Last IRN Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "next_rfi", "label": _("Next RFI Date"), "fieldtype": "Date", "width": 100},
	]
	return cols


def data(filters):
	po_filters = {"docstatus": 1}
	for key, field in (("project", "project"), ("supplier_po", "name"), ("supplier", "supplier")):
		if filters.get(key):
			po_filters[field] = filters.get(key)
	if filters.get("from_date") and filters.get("to_date"):
		po_filters["transaction_date"] = ["between", [filters.from_date, filters.to_date]]
	pos = frappe.get_all(
		"Purchase Order", filters=po_filters, fields=["name", "project", "supplier", "total_qty"]
	)
	rows = []
	for po in pos:
		points = frappe.db.sql(
			"""select p.status, count(*) from `tabITP Point` p join `tabITP` i on i.name = p.parent
			where i.supplier_po = %s and i.docstatus = 1 group by p.status""",
			po.name,
		)
		points = dict(points)
		rfis = dict(
			frappe.db.sql(
				"select status, count(*) from `tabRFI` where supplier_po = %s group by status", po.name
			)
		)
		irn = frappe.db.sql(
			"""select sum(l.qty_released), max(i.issue_date) from `tabIRN Line` l join `tabIRN` i on i.name = l.parent
			where i.supplier_po = %s and i.docstatus = 1""",
			po.name,
		)[0]
		ncrs = frappe.db.count(
			"Non Conformance",
			{"pvfss_supplier_po": po.name, "workflow_state": ["!=", "Closed"], "status": ["!=", "Cancelled"]},
		)
		next_rfi = frappe.db.sql(
			"""select min(coalesce(scheduled_date, proposed_date)) from `tabRFI`
			where supplier_po = %s and status in ('Raised', 'Scheduled', 'Rescheduled')""",
			po.name,
		)[0][0]
		if not (points or rfis or irn[0] or ncrs):
			continue
		row = {
			"project": po.project,
			"supplier_po": po.name,
			"supplier": po.supplier,
			"points_open": points.get("Open", 0),
			"points_closed": points.get("Closed", 0) + points.get("Waived", 0),
			"ncrs_open": ncrs,
			"po_qty": flt(po.total_qty),
			"irn_qty": flt(irn[0]),
			"irn_pct": flt(irn[0]) / flt(po.total_qty) * 100 if po.total_qty else 0,
			"last_irn": irn[1],
			"next_rfi": next_rfi,
		}
		row["rfi_raised"] = rfis.get("Raised", 0)
		row["rfi_scheduled"] = rfis.get("Scheduled", 0) + rfis.get("Rescheduled", 0)
		row["rfi_inspected"] = rfis.get("Inspected", 0)
		row["rfi_closed"] = rfis.get("Closed", 0)
		rows.append(row)
	return rows
