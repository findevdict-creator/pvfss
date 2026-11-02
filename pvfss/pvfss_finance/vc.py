"""IFRS 15 variable consideration on the Customer PO (FIN-60)."""

import frappe
from frappe import _
from frappe.utils import flt

from pvfss.pvfss_finance import accounts


def estimate(so):
	"""Sales Order validate: expected value or most likely amount per row."""
	for row in so.get("pvfss_variable_consideration") or []:
		row.currency = so.currency
		if row.estimation_method == "Most likely amount":
			row.estimated_amount = flt(row.likely_amount)
		else:
			row.estimated_amount = flt(flt(row.maximum_amount) * flt(row.probability_pct) / 100, 2)
		if abs(flt(row.constrained_amount)) > abs(flt(row.maximum_amount)) and row.maximum_amount:
			frappe.throw(
				_("Variable consideration row {0}: the constrained amount exceeds the maximum.").format(row.idx)
			)


def _rows(so_name):
	return frappe.get_all(
		"Variable Consideration",
		filters={"parent": so_name, "parenttype": "Sales Order"},
		fields=["name", "vc_type", "constrained_amount", "recognised_amount"],
		order_by="idx",
	)


def _entry(company, base, remark, project, posting_date=None):
	"""Positive: VC Accrual -> Revenue. Negative (LD / penalty): the reverse."""
	accrual = accounts.get(company, "vc_accrual")
	income = frappe.get_cached_value("Company", company, "default_income_account")
	debit, credit = (accrual, income) if base > 0 else (income, accrual)
	return accounts.post(
		company,
		[{"account": debit, "debit": abs(base)}, {"account": credit, "credit": abs(base)}],
		remark,
		posting_date=posting_date,
		project=project,
	)


def recognise(si):
	"""On invoice submit: allocate the constrained VC pro rata to the invoiced value."""
	if si.is_return:
		return
	so_name = next((r.sales_order for r in si.items if r.get("sales_order")), None)
	if not so_name:
		return
	rows = [r for r in _rows(so_name) if flt(r.constrained_amount)]
	if not rows:
		return
	so_total = flt(frappe.db.get_value("Sales Order", so_name, "net_total"))
	share = min(flt(si.net_total) / so_total, 1) if so_total else 0
	total = 0.0
	for row in rows:
		remaining = flt(row.constrained_amount) - flt(row.recognised_amount)
		amount = flt(row.constrained_amount) * share
		amount = max(amount, remaining) if remaining < 0 else min(amount, remaining)
		amount = flt(amount, 2)
		if amount:
			frappe.db.set_value(
				"Variable Consideration", row.name, "recognised_amount", flt(row.recognised_amount) + amount
			)
			total += amount
	if not total:
		return
	base = flt(total * flt(si.conversion_rate or 1), 2)
	je = _entry(si.company, base, _("Variable consideration on {0}").format(si.name), si.get("project"), si.posting_date)
	si.db_set({"pvfss_vc_amount": total, "pvfss_vc_journal_entry": je})


def reverse(si):
	"""Before an invoice is cancelled."""
	if not si.get("pvfss_vc_journal_entry"):
		return
	accounts.cancel(si.pvfss_vc_journal_entry)
	so_name = next((r.sales_order for r in si.items if r.get("sales_order")), None)
	rows = [r for r in _rows(so_name) if flt(r.constrained_amount)] if so_name else []
	so_total = flt(frappe.db.get_value("Sales Order", so_name, "net_total")) if so_name else 0
	share = min(flt(si.net_total) / so_total, 1) if so_total else 0
	for row in rows:
		amount = flt(flt(row.constrained_amount) * share, 2)
		frappe.db.set_value("Variable Consideration", row.name, "recognised_amount", flt(row.recognised_amount) - amount)
	si.db_set({"pvfss_vc_amount": 0, "pvfss_vc_journal_entry": None})


@frappe.whitelist()
def settle(sales_order: str, row: str, actual_amount: float):
	"""SCR-FIN-17 Settle VC: true-up JE for actual - recognised."""
	accounts.require_finance_manager()
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")
	vc = next((r for r in so.get("pvfss_variable_consideration") if r.name == row), None)
	if not vc:
		frappe.throw(_("Row {0} is not on {1}.").format(row, sales_order))
	if vc.true_up_journal_entry:
		frappe.throw(_("This variable consideration is already settled."))
	actual = flt(actual_amount)
	true_up = flt(actual - flt(vc.recognised_amount), 2)
	je = None
	if true_up:
		base = flt(true_up * flt(so.conversion_rate or 1), 2)
		je = _entry(so.company, base, _("VC true-up on {0} ({1})").format(so.name, vc.vc_type), so.get("project"))
	frappe.db.set_value(
		"Variable Consideration",
		vc.name,
		{"settled_amount": actual, "true_up_amount": true_up, "true_up_journal_entry": je},
	)
	return {"true_up": true_up, "journal_entry": je}
