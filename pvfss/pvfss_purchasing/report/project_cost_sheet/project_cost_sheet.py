# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
"""Project Cost Sheet (PRJ-31): Costing Sheet budget vs committed (Supplier POs) vs actual
(Purchase Invoices and Journal Entries tagged with the project), by cost type, in AED."""

import frappe
from frappe import _
from frappe.utils import flt

from pvfss.setup.customisations_09 import COST_TYPES

# Costing Sheet Item per-unit field for each cost type
BUDGET_FIELDS = {
	"Material": "unit_cost",
	"Freight": "freight",
	"Inspection / TPI": "inspection",
	"Documentation": "documentation",
	"Testing": "testing",
	"Finance": "finance_cost",
	"Other": "contingency",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.project:
		return columns(), []
	frappe.has_permission("Project", "read", filters.project, throw=True)
	figures = build(filters.project)
	return columns(), figures["rows"], None, None, summary(figures)


def columns():
	return [
		{"fieldname": "cost_type", "label": _("Cost Type"), "fieldtype": "Data", "width": 200},
		{"fieldname": "budget", "label": _("Budget AED"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "committed", "label": _("Committed AED"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "actual", "label": _("Actual AED"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "variance", "label": _("Budget - Actual"), "fieldtype": "Currency", "width": 140},
	]


def costing_sheet(sales_order):
	quotation = frappe.db.get_value("Sales Order Item", {"parent": sales_order}, "prevdoc_docname")
	return frappe.db.get_value("Quotation", quotation, "pvfss_costing_sheet") if quotation else None


def budget(cs):
	out = dict.fromkeys(COST_TYPES.split("\n"), 0.0)
	if not cs:
		return out
	for row in frappe.get_all(
		"Costing Sheet Item", filters={"parent": cs}, fields=["qty", *BUDGET_FIELDS.values()]
	):
		for cost_type, field in BUDGET_FIELDS.items():
			out[cost_type] += flt(row.get(field)) * flt(row.qty)
	return out


def actual(project):
	out = dict.fromkeys(COST_TYPES.split("\n"), 0.0)
	for r in frappe.db.sql(
		"""select ifnull(pii.pvfss_cost_type, 'Material') cost_type, sum(pii.base_net_amount) amount
		from `tabPurchase Invoice Item` pii join `tabPurchase Invoice` pi on pi.name = pii.parent
		where pi.docstatus = 1 and ifnull(pi.is_return, 0) = 0 and (pii.project = %(p)s or (ifnull(pii.project, '') = '' and pi.project = %(p)s))
		group by 1""",
		{"p": project},
		as_dict=True,
	):
		out[r.cost_type] = out.get(r.cost_type, 0) + flt(r.amount)
	for r in frappe.db.sql(
		"""select ifnull(jea.pvfss_cost_type, 'Other') cost_type,
			sum(jea.debit_in_account_currency * ifnull(jea.exchange_rate, 1)
				- jea.credit_in_account_currency * ifnull(jea.exchange_rate, 1)) amount
		from `tabJournal Entry Account` jea join `tabJournal Entry` je on je.name = jea.parent
		join `tabAccount` acc on acc.name = jea.account
		where je.docstatus = 1 and jea.project = %(p)s and acc.root_type = 'Expense'
		group by 1""",
		{"p": project},
		as_dict=True,
	):
		out[r.cost_type] = out.get(r.cost_type, 0) + flt(r.amount)
	return out


def committed(project):
	return flt(
		frappe.db.sql(
			"select sum(base_net_total) from `tabPurchase Order` where project = %s and docstatus = 1",
			project,
		)[0][0]
	)


def build(project):
	sales_order = frappe.db.get_value("Project", project, "sales_order")
	cs = costing_sheet(sales_order) if sales_order else None
	b, a = budget(cs), actual(project)
	c = {"Material": committed(project)}
	rows = []
	for cost_type in COST_TYPES.split("\n"):
		if not (b.get(cost_type) or a.get(cost_type) or c.get(cost_type)):
			continue
		rows.append(
			{
				"cost_type": _(cost_type),
				"budget": flt(b.get(cost_type), 2),
				"committed": flt(c.get(cost_type), 2),
				"actual": flt(a.get(cost_type), 2),
				"variance": flt(b.get(cost_type, 0) - a.get(cost_type, 0), 2),
			}
		)
	revenue = flt(frappe.db.get_value("Sales Order", sales_order, "base_net_total")) if sales_order else 0
	invoiced = (
		flt(
			frappe.db.sql(
				"""select sum(sii.base_net_amount) from `tabSales Invoice Item` sii
			join `tabSales Invoice` si on si.name = sii.parent
			where si.docstatus = 1 and sii.sales_order = %s""",
				sales_order,
			)[0][0]
		)
		if sales_order
		else 0
	)
	budget_cost = sum(b.values())
	actual_cost = sum(a.values())
	return {
		"rows": rows,
		"costing_sheet": cs,
		"revenue": revenue,
		"invoiced": invoiced,
		"budget_cost": budget_cost,
		"actual_cost": actual_cost,
		"budget_margin": revenue - budget_cost,
		"actual_margin": (invoiced or revenue) - actual_cost,
	}


def summary(f):
	def pct(margin, base):
		return flt(margin * 100.0 / base, 2) if base else 0

	actual_base = f["invoiced"] or f["revenue"]
	return [
		{"label": _("Customer PO value"), "value": f["revenue"], "datatype": "Currency"},
		{"label": _("Invoiced"), "value": f["invoiced"], "datatype": "Currency"},
		{
			"label": _("Budget margin"),
			"value": f["budget_margin"],
			"datatype": "Currency",
			"indicator": "green" if f["budget_margin"] >= 0 else "red",
		},
		{
			"label": _("Budget margin %"),
			"value": pct(f["budget_margin"], f["revenue"]),
			"datatype": "Percent",
		},
		{
			"label": _("Actual margin"),
			"value": f["actual_margin"],
			"datatype": "Currency",
			"indicator": "green" if f["actual_margin"] >= 0 else "red",
		},
		{"label": _("Actual margin %"), "value": pct(f["actual_margin"], actual_base), "datatype": "Percent"},
	]
