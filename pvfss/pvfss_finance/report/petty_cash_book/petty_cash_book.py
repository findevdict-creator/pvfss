"""Petty Cash Book per custodian (FIN-65, SCR-FIN-16)."""

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "voucher_type", "label": _("Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "voucher_no", "label": _("Voucher"), "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 220},
		{"fieldname": "against", "label": _("Account"), "fieldtype": "Data", "width": 160},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 110},
		{"fieldname": "cash_in", "label": _("In"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "cash_out", "label": _("Out"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "width": 120},
	]
	if not filters.custodian:
		return columns, []
	account = frappe.db.get_value("Employee", filters.custodian, "pvfss_petty_cash_account")
	if not account:
		frappe.throw(_("Set the petty cash account on {0}.").format(filters.custodian))
	from_date = getdate(filters.from_date or add_months(nowdate(), -1))
	to_date = getdate(filters.to_date or nowdate())
	opening_rows = frappe.get_all(
		"GL Entry",
		filters={"account": account, "is_cancelled": 0, "posting_date": ["<", from_date]},
		fields=["debit", "credit"],
	)
	balance = sum(flt(r.debit) - flt(r.credit) for r in opening_rows)
	data = [{"description": _("Opening balance"), "balance": balance, "bold": 1}]
	for r in frappe.get_all(
		"GL Entry",
		filters={"account": account, "is_cancelled": 0, "posting_date": ["between", [from_date, to_date]]},
		fields=["posting_date", "voucher_type", "voucher_no", "against", "debit", "credit", "project", "remarks"],
		order_by="posting_date asc, creation asc",
	):
		balance += flt(r.debit) - flt(r.credit)
		data.append(
			{
				"posting_date": r.posting_date,
				"voucher_type": r.voucher_type,
				"voucher_no": r.voucher_no,
				"description": r.remarks,
				"against": r.against,
				"project": r.project,
				"cash_in": r.debit,
				"cash_out": r.credit,
				"balance": balance,
			}
		)
	data.append({"description": _("Closing balance"), "balance": balance, "bold": 1})
	return columns, data
