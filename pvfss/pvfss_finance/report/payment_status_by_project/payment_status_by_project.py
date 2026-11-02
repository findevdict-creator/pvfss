"""Payment Status by Project (FIN-71, SCR-FIN-19)."""

import frappe
from frappe import _
from frappe.utils import flt


def _sum(rows, field):
	return sum(flt(r.get(field)) for r in rows)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	if filters.project:
		conditions["name"] = filters.project
	if filters.customer:
		conditions["customer"] = filters.customer
	data = []
	for project in frappe.get_all("Project", filters=conditions, fields=["name", "customer"]):
		orders = frappe.get_all(
			"Sales Order", filters={"project": project.name, "docstatus": 1}, fields=["base_grand_total"]
		)
		sales = frappe.get_all(
			"Sales Invoice",
			filters={"project": project.name, "docstatus": 1},
			fields=[
				"base_grand_total",
				"outstanding_amount",
				"conversion_rate",
				"pvfss_retention_amount",
				"pvfss_retention",
			],
		)
		purchases = frappe.get_all(
			"Purchase Invoice",
			filters={"project": project.name, "docstatus": 1},
			fields=[
				"base_grand_total",
				"outstanding_amount",
				"conversion_rate",
				"pvfss_retention_amount",
				"pvfss_retention",
			],
		)
		if not (orders or sales or purchases):
			continue
		held = sum(
			flt(r)
			for r in frappe.get_all(
				"Retention",
				filters={
					"project": project.name,
					"direction": "Receivable",
					"status": ["in", ("Held", "Release requested")],
				},
				pluck="base_amount",
			)
		)

		def split(invoices):
			total = _sum(invoices, "base_grand_total")
			outstanding = sum(flt(r.outstanding_amount) * flt(r.conversion_rate or 1) for r in invoices)
			retained = sum(
				flt(r.pvfss_retention_amount) * flt(r.conversion_rate or 1)
				for r in invoices
				if r.pvfss_retention
			)
			return total, total - outstanding - retained, outstanding

		invoiced, received, outstanding = split(sales)
		supplier_invoiced, paid, supplier_outstanding = split(purchases)
		data.append(
			{
				"project": project.name,
				"customer": project.customer,
				"contract_value": _sum(orders, "base_grand_total"),
				"invoiced": invoiced,
				"received": received,
				"retention_held": held,
				"outstanding": outstanding,
				"supplier_invoiced": supplier_invoiced,
				"supplier_paid": paid,
				"supplier_outstanding": supplier_outstanding,
				"net_cash": received - paid,
			}
		)
	money = {"fieldtype": "Currency", "width": 120}
	columns = [
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 160,
		},
		{"fieldname": "contract_value", "label": _("Contract Value"), **money},
		{"fieldname": "invoiced", "label": _("Invoiced"), **money},
		{"fieldname": "received", "label": _("Received"), **money},
		{"fieldname": "retention_held", "label": _("Retention Held"), **money},
		{"fieldname": "outstanding", "label": _("Customer Outstanding"), **money},
		{"fieldname": "supplier_invoiced", "label": _("Supplier Invoiced"), **money},
		{"fieldname": "supplier_paid", "label": _("Supplier Paid"), **money},
		{"fieldname": "supplier_outstanding", "label": _("Supplier Outstanding"), **money},
		{"fieldname": "net_cash", "label": _("Net Cash Position"), **money},
	]
	return columns, data
