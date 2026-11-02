"""Retention Register (FIN-52, SCR-FIN-14)."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	for key in ("direction", "party", "project", "status"):
		if filters.get(key):
			conditions[key] = filters[key]
	if filters.from_date and filters.to_date:
		conditions["release_due_date"] = ["between", [filters.from_date, filters.to_date]]
	today = getdate(nowdate())
	data = []
	for r in frappe.get_all(
		"Retention",
		filters=conditions,
		fields=["name", "direction", "party", "project", "source_invoice", "base_amount", "held_date", "release_due_date", "status"],
		order_by="release_due_date asc",
	):
		r.days_to_due = date_diff(r.release_due_date, today) if r.release_due_date else None
		data.append(r)
	columns = [
		{"fieldname": "name", "label": _("Retention"), "fieldtype": "Link", "options": "Retention", "width": 120},
		{"fieldname": "direction", "label": _("Direction"), "fieldtype": "Data", "width": 90},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 170},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 120},
		{"fieldname": "source_invoice", "label": _("Source"), "fieldtype": "Data", "width": 130},
		{"fieldname": "base_amount", "label": _("Amount (AED)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "held_date", "label": _("Held"), "fieldtype": "Date", "width": 95},
		{"fieldname": "release_due_date", "label": _("Release Due"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_to_due", "label": _("Days to Due"), "fieldtype": "Int", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
	]
	return columns, data
