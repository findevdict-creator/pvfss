"""Revenue and VC by Project (FIN-60, SCR-FIN-17)."""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {"docstatus": 1}
	for key in ("project", "customer"):
		if filters.get(key):
			conditions[key] = filters[key]
	if filters.from_date and filters.to_date:
		conditions["transaction_date"] = ["between", [filters.from_date, filters.to_date]]
	data = []
	for so in frappe.get_all(
		"Sales Order", filters=conditions, fields=["name", "project", "customer", "base_net_total", "conversion_rate"]
	):
		rows = frappe.get_all(
			"Variable Consideration",
			filters={"parent": so.name, "parenttype": "Sales Order"},
			fields=["maximum_amount", "constrained_amount", "recognised_amount", "settled_amount", "true_up_amount"],
		)
		rate = flt(so.conversion_rate or 1)
		total = {k: sum(flt(r[k]) for r in rows) * rate for k in rows[0]} if rows else {}
		invoiced = sum(
			flt(v)
			for v in frappe.get_all(
				"Sales Invoice Item",
				filters={"sales_order": so.name, "docstatus": 1},
				pluck="base_net_amount",
			)
		)
		data.append(
			{
				"project": so.project,
				"sales_order": so.name,
				"customer": so.customer,
				"contract_value": so.base_net_total,
				"vc_max": total.get("maximum_amount", 0),
				"vc_constrained": total.get("constrained_amount", 0),
				"vc_recognised": total.get("recognised_amount", 0),
				"vc_settled": total.get("settled_amount", 0),
				"true_up": total.get("true_up_amount", 0),
				"revenue": invoiced + total.get("recognised_amount", 0) + total.get("true_up_amount", 0),
			}
		)
	money = {"fieldtype": "Currency", "width": 120}
	columns = [
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 120},
		{"fieldname": "sales_order", "label": _("Customer PO"), "fieldtype": "Link", "options": "Sales Order", "width": 130},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "contract_value", "label": _("Contract Value"), **money},
		{"fieldname": "vc_max", "label": _("VC Maximum"), **money},
		{"fieldname": "vc_constrained", "label": _("VC Constrained"), **money},
		{"fieldname": "vc_recognised", "label": _("VC Recognised"), **money},
		{"fieldname": "vc_settled", "label": _("VC Settled"), **money},
		{"fieldname": "true_up", "label": _("True-up"), **money},
		{"fieldname": "revenue", "label": _("Revenue Recognised"), **money},
	]
	return columns, data
