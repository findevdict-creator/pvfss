"""Win / Loss Analysis (CRM-13, SCR-CRM-07): counts and values by a chosen dimension, win rate, turnaround."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from pvfss.pvfss_crm import inquiry as stages

DIMENSIONS = {
	"Contractor": "party_name",
	"Client Project": "pvfss_client_project",
	"Owner": "pvfss_owner",
	"Product Category": None,  # from the inquiry lines
	"Lost Reason": None,  # from the lost reasons table
}


def _inquiries(filters):
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or add_days(to_date, -365))
	conditions = {"pvfss_received_on": ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]}
	for key in ("party_name", "pvfss_client_project", "pvfss_owner"):
		if filters.get(key):
			conditions[key] = filters[key]
	return frappe.get_all(
		"Opportunity",
		filters=conditions,
		fields=[
			"name",
			"party_name",
			"pvfss_client_project",
			"pvfss_owner",
			"pvfss_stage",
			"pvfss_quoted_value",
			"pvfss_turnaround_days",
		],
	)


def _keys(row, dimension, categories, reasons):
	field = DIMENSIONS.get(dimension)
	if field:
		return [row.get(field) or _("Not set")]
	if dimension == "Product Category":
		return categories.get(row.name) or [_("Not set")]
	return reasons.get(row.name) or ([_("Not set")] if row.pvfss_stage == stages.LOST else [])


def get_data(filters):
	filters = frappe._dict(filters or {})
	dimension = filters.get("group_by") or "Contractor"
	inquiries = _inquiries(filters)
	names = [r.name for r in inquiries] or [""]
	categories, reasons = {}, {}
	if dimension == "Product Category":
		for r in frappe.get_all(
			"Opportunity Item",
			filters={"parent": ["in", names], "parenttype": "Opportunity"},
			fields=["parent", "pvfss_product_category"],
		):
			value = r.pvfss_product_category or _("Not set")
			if value not in categories.setdefault(r.parent, []):
				categories[r.parent].append(value)
	if dimension == "Lost Reason":
		for r in frappe.get_all(
			"Opportunity Lost Reason Detail",
			filters={"parent": ["in", names], "parenttype": "Opportunity"},
			fields=["parent", "lost_reason"],
		):
			reasons.setdefault(r.parent, []).append(r.lost_reason)

	groups = {}
	for row in inquiries:
		for key in _keys(row, dimension, categories, reasons):
			g = groups.setdefault(
				key,
				{
					"group": key,
					"inquiries": 0,
					"quoted": 0,
					"won": 0,
					"lost": 0,
					"won_value": 0.0,
					"lost_value": 0.0,
					"days": [],
				},
			)
			g["inquiries"] += 1
			if row.pvfss_quoted_value:
				g["quoted"] += 1
			if row.pvfss_stage == stages.WON:
				g["won"] += 1
				g["won_value"] += flt(row.pvfss_quoted_value)
			elif row.pvfss_stage == stages.LOST:
				g["lost"] += 1
				g["lost_value"] += flt(row.pvfss_quoted_value)
			if row.pvfss_turnaround_days is not None and row.pvfss_quoted_value:
				g["days"].append(row.pvfss_turnaround_days)
	data = []
	for g in sorted(groups.values(), key=lambda g: (-g["inquiries"], str(g["group"]))):
		decided = g["won"] + g["lost"]
		days = g.pop("days")
		g["win_rate"] = flt(g["won"] * 100 / decided, 1) if decided else 0
		g["turnaround"] = flt(sum(days) / len(days), 1) if days else None
		data.append(g)
	return data


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	columns = [
		{
			"fieldname": "group",
			"label": _(filters.get("group_by") or "Contractor"),
			"fieldtype": "Data",
			"width": 200,
		},
		{"fieldname": "inquiries", "label": _("Inquiries"), "fieldtype": "Int", "width": 90},
		{"fieldname": "quoted", "label": _("Quoted"), "fieldtype": "Int", "width": 80},
		{"fieldname": "won", "label": _("Won"), "fieldtype": "Int", "width": 70},
		{"fieldname": "lost", "label": _("Lost"), "fieldtype": "Int", "width": 70},
		{
			"fieldname": "won_value",
			"label": _("Won value (AED)"),
			"fieldtype": "Currency",
			"options": "AED",
			"width": 140,
		},
		{
			"fieldname": "lost_value",
			"label": _("Lost value (AED)"),
			"fieldtype": "Currency",
			"options": "AED",
			"width": 140,
		},
		{"fieldname": "win_rate", "label": _("Win rate %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "turnaround", "label": _("Avg turnaround (days)"), "fieldtype": "Float", "width": 140},
	]
	won = (
		sum(r["won"] for r in data)
		if (filters.get("group_by") or "Contractor") in ("Contractor", "Client Project", "Owner")
		else None
	)
	summary = []
	if won is not None:
		lost = sum(r["lost"] for r in data)
		summary = [
			{"label": _("Won"), "value": won, "datatype": "Int", "indicator": "green"},
			{"label": _("Lost"), "value": lost, "datatype": "Int", "indicator": "red"},
			{
				"label": _("Win rate"),
				"value": flt(won * 100 / (won + lost), 1) if won + lost else 0,
				"datatype": "Percent",
			},
		]
	top = data[:10]
	chart = {
		"data": {
			"labels": [r["group"] for r in top],
			"datasets": [
				{"name": _("Won"), "values": [r["won"] for r in top]},
				{"name": _("Lost"), "values": [r["lost"] for r in top]},
			],
		},
		"type": "bar",
		"barOptions": {"stacked": 1},
	}
	return columns, data, None, chart, summary
