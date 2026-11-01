# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
"""Inquiry Register (CRM-11, SCR-CRM-06): the live replacement for the Excel register."""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Inquiry No"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Opportunity",
			"width": 140,
		},
		{
			"label": _("Contractor Ref"),
			"fieldname": "pvfss_contractor_ref",
			"fieldtype": "Data",
			"width": 140,
		},
		{
			"label": _("Contractor"),
			"fieldname": "party_name",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{
			"label": _("Client Project"),
			"fieldname": "pvfss_client_project",
			"fieldtype": "Link",
			"options": "Client Project",
			"width": 140,
		},
		{"label": _("Received"), "fieldname": "received", "fieldtype": "Date", "width": 100},
		{"label": _("Due"), "fieldname": "due", "fieldtype": "Date", "width": 100},
		{
			"label": _("Owner"),
			"fieldname": "pvfss_owner",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": _("Lines"), "fieldname": "pvfss_line_count", "fieldtype": "Int", "width": 70},
		{"label": _("Stage"), "fieldname": "pvfss_stage", "fieldtype": "Data", "width": 130},
		{
			"label": _("Quoted Value (AED)"),
			"fieldname": "pvfss_quoted_value",
			"fieldtype": "Currency",
			"options": "AED",
			"width": 140,
		},
		{"label": _("Result"), "fieldname": "result", "fieldtype": "Data", "width": 100},
		{"label": _("Lost Reason"), "fieldname": "lost_reason", "fieldtype": "Data", "width": 180},
	]


def get_data(filters):
	conditions = {}
	if filters.received_from and filters.received_to:
		conditions["pvfss_received_on"] = [
			"between",
			[f"{filters.received_from} 00:00:00", f"{filters.received_to} 23:59:59"],
		]
	elif filters.received_from:
		conditions["pvfss_received_on"] = [">=", f"{filters.received_from} 00:00:00"]
	if filters.due_from and filters.due_to:
		conditions["pvfss_bid_due_date"] = [
			"between",
			[f"{filters.due_from} 00:00:00", f"{filters.due_to} 23:59:59"],
		]
	for key in ("party_name", "pvfss_client_project", "pvfss_owner"):
		if filters.get(key):
			conditions[key] = filters.get(key)
	if filters.get("stage"):
		stages = (
			filters.stage
			if isinstance(filters.stage, list)
			else [s.strip() for s in filters.stage.split(",") if s.strip()]
		)
		conditions["pvfss_stage"] = ["in", stages]

	rows = frappe.get_list(
		"Opportunity",
		filters=conditions,
		fields=[
			"name",
			"pvfss_contractor_ref",
			"party_name",
			"pvfss_client_project",
			"pvfss_received_on",
			"pvfss_bid_due_date",
			"pvfss_owner",
			"pvfss_line_count",
			"pvfss_stage",
			"pvfss_quoted_value",
		],
		order_by="pvfss_received_on desc",
	)
	if not rows:
		return []

	reasons = {}
	for r in frappe.get_all(
		"Opportunity Lost Reason Detail",
		filters={"parenttype": "Opportunity", "parent": ["in", [row.name for row in rows]]},
		fields=["parent", "lost_reason"],
	):
		reasons.setdefault(r.parent, []).append(r.lost_reason)

	for row in rows:
		row.received = row.pvfss_received_on and row.pvfss_received_on.date()
		row.due = row.pvfss_bid_due_date and row.pvfss_bid_due_date.date()
		row.result = row.pvfss_stage if row.pvfss_stage in ("Won", "Lost", "No Bid", "Cancelled") else ""
		row.lost_reason = ", ".join(reasons.get(row.name, []))
	return rows
