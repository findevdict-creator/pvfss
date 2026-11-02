"""Invoice & Payment Status (FIN-12, SCR-FIN-05): receivable or payable side."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate


def columns(side):
	party = _("Customer") if side == "Receivable" else _("Supplier")
	paid = _("Received") if side == "Receivable" else _("Paid")
	dt = "Sales Invoice" if side == "Receivable" else "Purchase Invoice"
	return [
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 120},
		{"fieldname": "party", "label": party, "fieldtype": "Data", "width": 160},
		{"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link", "options": dt, "width": 140},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "currency", "label": _("Currency"), "fieldtype": "Link", "options": "Currency", "width": 70},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "vat", "label": _("VAT"), "fieldtype": "Currency", "options": "currency", "width": 100},
		{"fieldname": "retention", "label": _("Retention Held"), "fieldtype": "Currency", "options": "currency", "width": 110},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "paid", "label": paid, "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "balance", "label": _("Balance"), "fieldtype": "Currency", "options": "currency", "width": 120},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 90},
		{"fieldname": "payment_method", "label": _("Payment Method"), "fieldtype": "Data", "width": 90},
		{"fieldname": "reference", "label": _("PDC / LC"), "fieldtype": "Data", "width": 140},
	]


def _references(doctype, names):
	"""PDC and LC references per invoice."""
	out = {}
	for row in frappe.get_all(
		"PDC Invoice",
		filters={"invoice_type": doctype, "invoice": ["in", names or [""]], "docstatus": 1},
		fields=["invoice", "parent"],
	):
		out.setdefault(row.invoice, []).append(row.parent)
	return out


def execute(filters=None):
	filters = frappe._dict(filters or {})
	side = filters.side or "Receivable"
	dt, party_field = ("Sales Invoice", "customer") if side == "Receivable" else ("Purchase Invoice", "supplier")
	conditions = {"docstatus": 1, "is_return": 0}
	if filters.party:
		conditions[party_field] = filters.party
	if filters.project:
		conditions["project"] = filters.project
	if filters.from_date and filters.to_date:
		conditions["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	order_field = "pvfss_payment_method"
	rows = frappe.get_all(
		dt,
		filters=conditions,
		fields=[
			"name", party_field + " as party", "project", "posting_date", "currency", "grand_total",
			"total_taxes_and_charges", "outstanding_amount", "due_date", "pvfss_retention_amount",
			"pvfss_retention",
		],
		order_by="posting_date desc",
	)
	refs = _references(dt, [r.name for r in rows])
	methods = {}
	today = getdate(nowdate())
	data = []
	for r in rows:
		so_or_po = frappe.db.get_value(
			dt + " Item", {"parent": r.name}, "sales_order" if side == "Receivable" else "purchase_order"
		)
		if so_or_po and so_or_po not in methods:
			methods[so_or_po] = frappe.db.get_value(
				"Sales Order" if side == "Receivable" else "Purchase Order", so_or_po, order_field
			)
		retention = flt(r.pvfss_retention_amount) if r.pvfss_retention else 0
		balance = flt(r.outstanding_amount)
		paid = flt(r.grand_total) - retention - balance
		overdue = date_diff(today, r.due_date) if r.due_date and balance > 0 else 0
		status = "Paid" if balance <= 0 else ("Overdue" if overdue > 0 else "Open")
		if filters.status and filters.status != status:
			continue
		method = methods.get(so_or_po) or ""
		if filters.payment_method and filters.payment_method != method:
			continue
		data.append(
			{
				"project": r.project,
				"party": r.party,
				"invoice": r.name,
				"posting_date": r.posting_date,
				"currency": r.currency,
				"amount": r.grand_total,
				"vat": r.total_taxes_and_charges,
				"retention": retention,
				"due_date": r.due_date,
				"paid": paid,
				"balance": balance,
				"days_overdue": max(overdue, 0),
				"payment_method": method,
				"reference": ", ".join(refs.get(r.name, [])),
			}
		)
	return columns(side), data
