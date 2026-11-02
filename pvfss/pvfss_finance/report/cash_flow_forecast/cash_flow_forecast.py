"""Cash-flow Forecast (FIN-70, SCR-FIN-18): 13 weekly buckets in AED.

Anything already due before the first week falls into week 1.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day_of_week, getdate, nowdate

LIVE_LC = ("Issued", "Amended", "Documents presented", "Accepted")


def _bucket(date, start, weeks):
	index = (getdate(date) - start).days // 7 if date else 0
	return min(max(index, 0), weeks - 1) if index < weeks else None


def _schedule(doctype):
	"""(due date, outstanding in AED) from the payment schedule of open invoices."""
	out = []
	for inv in frappe.get_all(
		doctype, filters={"docstatus": 1, "outstanding_amount": [">", 0]}, fields=["name", "conversion_rate"]
	):
		for row in frappe.get_all(
			"Payment Schedule",
			filters={"parent": inv.name, "parenttype": doctype},
			fields=["due_date", "outstanding"],
		):
			out.append((row.due_date, flt(row.outstanding) * flt(inv.conversion_rate or 1)))
	return out


def _pdcs(direction, statuses):
	return [
		(r.cheque_date, flt(r.amount) * flt(r.exchange_rate or 1))
		for r in frappe.get_all(
			"Post-Dated Cheque",
			filters={"docstatus": 1, "direction": direction, "status": ["in", statuses]},
			fields=["cheque_date", "amount", "exchange_rate"],
		)
	]


def _lcs(direction):
	out = []
	for r in frappe.get_all(
		"Letter of Credit",
		filters={"docstatus": 1, "direction": direction, "status": ["in", LIVE_LC]},
		fields=["presentation_deadline", "expiry_date", "usance_days", "amount", "currency"],
	):
		date = add_days(r.presentation_deadline or r.expiry_date, r.usance_days or 0)
		rate = (
			1
			if r.currency == "AED"
			else flt(
				frappe.db.get_value(
					"Currency Exchange", {"from_currency": r.currency, "to_currency": "AED"}, "exchange_rate"
				)
			)
			or 1
		)
		out.append((date, flt(r.amount) * rate))
	return out


def _retention(direction):
	return [
		(r.release_due_date, flt(r.base_amount))
		for r in frappe.get_all(
			"Retention",
			filters={"direction": direction, "status": ["in", ("Held", "Release requested")]},
			fields=["release_due_date", "base_amount"],
		)
	]


def _recurring(start, weeks):
	out = []
	end = add_days(start, weeks * 7 - 1)
	for row in frappe.get_single("PVFSS Settings").recurring_expenses:
		date = getdate(row.start_date or start)
		while date <= getdate(end) and (not row.end_date or date <= getdate(row.end_date)):
			if date >= start:
				out.append((date, flt(row.amount)))
			date = add_days(date, 7) if row.frequency == "Weekly" else getdate(add_months(date, 1))
	return out


def _opening(start, bank_accounts):
	filters = {"account_type": "Bank", "is_group": 0}
	if bank_accounts:
		filters["name"] = ["in", bank_accounts]
	accounts = frappe.get_all("Account", filters=filters, pluck="name")
	rows = frappe.get_all(
		"GL Entry",
		filters={"account": ["in", accounts or [""]], "is_cancelled": 0, "posting_date": ["<", start]},
		fields=["debit", "credit"],
	)
	return sum(flt(r.debit) - flt(r.credit) for r in rows)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	weeks = int(filters.weeks or 13)
	start = get_first_day_of_week(getdate(filters.start_date or nowdate()))
	keys = [f"w{i + 1}" for i in range(weeks)]
	lines = [
		("in", _("AR by payment schedule"), _schedule("Sales Invoice")),
		("in", _("PDCs received"), _pdcs("Received", ("In hand", "Deposited"))),
		("in", _("Export LCs"), _lcs("Export") if filters.get("include_lc", 1) else []),
		("in", _("Retention receivable due"), _retention("Receivable")),
		("out", _("AP by payment schedule"), _schedule("Purchase Invoice")),
		("out", _("PDCs issued"), _pdcs("Issued", ("Issued", "Presented"))),
		("out", _("Import LCs at maturity"), _lcs("Import")),
		("out", _("Retention payable due"), _retention("Payable")),
		("out", _("Recurring expenses"), _recurring(start, weeks)),
	]
	opening = _opening(start, frappe.parse_json(filters.bank_accounts) if filters.bank_accounts else None)
	totals = {"in": [0.0] * weeks, "out": [0.0] * weeks}
	data = [{"line": _("Opening bank balance"), keys[0]: opening, "bold": 1}]
	for side, label, items in lines:
		row = {"line": label, "side": side}
		for date, amount in items:
			index = _bucket(date, start, weeks)
			if index is None:
				continue
			row[keys[index]] = flt(row.get(keys[index])) + amount
			totals[side][index] += amount
		data.append(row)
	net = {"line": _("Net flow"), "bold": 1}
	closing = {"line": _("Closing balance"), "bold": 1}
	balance = opening
	for i, key in enumerate(keys):
		net[key] = totals["in"][i] - totals["out"][i]
		balance += net[key]
		closing[key] = balance
	data += [net, closing]
	columns = [{"fieldname": "line", "label": _("Line"), "fieldtype": "Data", "width": 220}] + [
		{
			"fieldname": key,
			"label": _("W{0} {1}").format(i + 1, frappe.utils.formatdate(add_days(start, 7 * i), "dd MMM")),
			"fieldtype": "Currency",
			"width": 110,
		}
		for i, key in enumerate(keys)
	]
	chart = {
		"data": {
			"labels": [c["label"] for c in columns[1:]],
			"datasets": [
				{"name": _("Inflows"), "chartType": "bar", "values": totals["in"]},
				{"name": _("Outflows"), "chartType": "bar", "values": totals["out"]},
				{"name": _("Closing balance"), "chartType": "line", "values": [closing[k] for k in keys]},
			],
		},
		"type": "axis-mixed",
	}
	return columns, data, None, chart
