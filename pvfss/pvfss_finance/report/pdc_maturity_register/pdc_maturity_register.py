"""PDC Maturity Register (FIN-45, SCR-FIN-11): by cheque date, grouped by week with subtotals."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_first_day_of_week, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date = getdate(filters.from_date or nowdate())
	to_date = getdate(filters.to_date or add_days(from_date, 30))
	conditions = {"docstatus": 1, "cheque_date": ["between", [from_date, to_date]]}
	for key in ("direction", "party", "status"):
		if filters.get(key):
			conditions[key] = filters[key]
	rows = frappe.get_all(
		"Post-Dated Cheque",
		filters=conditions,
		fields=[
			"name",
			"cheque_date",
			"direction",
			"party",
			"bank",
			"cheque_no",
			"amount",
			"exchange_rate",
			"status",
		],
		order_by="cheque_date asc",
	)
	links = {}
	for row in frappe.get_all(
		"PDC Invoice",
		filters={"parent": ["in", [r.name for r in rows] or [""]]},
		fields=["parent", "invoice"],
	):
		links.setdefault(row.parent, []).append(row.invoice)
	data, week, subtotal = [], None, 0.0
	for r in rows:
		start = get_first_day_of_week(r.cheque_date)
		if week and start != week:
			data.append(
				{
					"party": _("Week of {0}").format(frappe.utils.formatdate(week)),
					"amount_aed": subtotal,
					"bold": 1,
				}
			)
			subtotal = 0.0
		week = start
		amount = flt(r.amount) * flt(r.exchange_rate or 1)
		subtotal += amount
		data.append(
			{
				"cheque_date": r.cheque_date,
				"pdc": r.name,
				"direction": r.direction,
				"party": r.party,
				"bank": r.bank,
				"cheque_no": r.cheque_no,
				"amount_aed": amount,
				"status": r.status,
				"invoices": ", ".join(links.get(r.name, [])),
			}
		)
	if week:
		data.append(
			{
				"party": _("Week of {0}").format(frappe.utils.formatdate(week)),
				"amount_aed": subtotal,
				"bold": 1,
			}
		)
	columns = [
		{"fieldname": "cheque_date", "label": _("Cheque Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "pdc",
			"label": _("PDC"),
			"fieldtype": "Link",
			"options": "Post-Dated Cheque",
			"width": 130,
		},
		{"fieldname": "direction", "label": _("Direction"), "fieldtype": "Data", "width": 90},
		{"fieldname": "party", "label": _("Party"), "fieldtype": "Data", "width": 180},
		{"fieldname": "bank", "label": _("Bank"), "fieldtype": "Data", "width": 120},
		{"fieldname": "cheque_no", "label": _("Cheque No"), "fieldtype": "Data", "width": 100},
		{"fieldname": "amount_aed", "label": _("Amount (AED)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "invoices", "label": _("Linked Invoices"), "fieldtype": "Data", "width": 200},
	]
	return columns, data
