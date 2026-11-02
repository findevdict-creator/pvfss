"""Customer and supplier retention (FIN-50 to FIN-52)."""

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, getdate, nowdate

from pvfss.pvfss_finance import accounts

RECEIVABLE, PAYABLE = "Receivable", "Payable"


def _source_order(doc, field):
	return next((r.get(field) for r in doc.items if r.get(field)), None)


def sales_terms(si):
	"""(pct, basis, base, warranty months) from the Customer PO, falling back to the project."""
	so = _source_order(si, "sales_order")
	if so:
		values = frappe.db.get_value(
			"Sales Order",
			so,
			["pvfss_retention_pct", "pvfss_retention_basis", "pvfss_retention_base", "pvfss_warranty_months"],
			as_dict=True,
		)
		return (
			flt(values.pvfss_retention_pct),
			values.pvfss_retention_basis or "Per invoice",
			values.pvfss_retention_base or "Net",
			cint(values.pvfss_warranty_months),
		)
	if si.get("project"):
		values = frappe.db.get_value(
			"Project", si.project, ["pvfss_retention_pct", "pvfss_warranty_months"], as_dict=True
		)
		return flt(values.pvfss_retention_pct), "Per invoice", "Net", cint(values.pvfss_warranty_months)
	return 0, "Per invoice", "Net", 0


def preview_sales(si):
	pct, basis, base, _months = sales_terms(si)
	if basis != "Per invoice":
		pct = 0
	si.pvfss_retention_pct = pct
	si.pvfss_retention_base = base
	total = si.grand_total if base == "Gross" else si.net_total
	si.pvfss_retention_amount = flt(total * pct / 100, 2)


def preview_purchase(pi):
	po = _source_order(pi, "purchase_order")
	pct = flt(frappe.db.get_value("Purchase Order", po, "pvfss_supplier_retention_pct")) if po else 0
	pi.pvfss_retention_pct = pct
	pi.pvfss_retention_amount = flt(pi.net_total * pct / 100, 2)


def _record(doc, direction, amount, months):
	held = getdate(doc.posting_date)
	party_type, party = ("Customer", doc.customer) if direction == RECEIVABLE else ("Supplier", doc.supplier)
	ret = frappe.get_doc(
		{
			"doctype": "Retention",
			"direction": direction,
			"company": doc.company,
			"party_type": party_type,
			"party": party,
			"project": doc.get("project"),
			"source_doctype": doc.doctype,
			"source_invoice": doc.name,
			"currency": doc.currency,
			"amount": amount,
			"base_amount": flt(amount * flt(doc.conversion_rate or 1), 2),
			"held_date": held,
			"release_condition": "Warranty end",
			"release_due_date": add_months(held, months or 12),
		}
	)
	ret.flags.ignore_permissions = True
	ret.insert()
	return ret


def hold_sales(si):
	"""FIN-50: Debtors -> Retention Receivable for the same customer, on submit."""
	if si.is_return or not flt(si.get("pvfss_retention_amount")):
		return
	_pct, _basis, _base, months = sales_terms(si)
	ret = _record(si, RECEIVABLE, si.pvfss_retention_amount, months)
	base = ret.base_amount
	party = {"party_type": "Customer", "party": si.customer}
	je = accounts.post(
		si.company,
		[
			{"account": accounts.get(si.company, "retention_receivable"), "debit": base, **party},
			{
				"account": si.debit_to,
				"credit": base,
				"exchange_rate": si.conversion_rate,
				"reference_type": "Sales Invoice",
				"reference_name": si.name,
				**party,
			},
		],
		_("Retention held on {0}").format(si.name),
		posting_date=si.posting_date,
		project=si.get("project"),
	)
	ret.db_set("hold_journal_entry", je)
	si.db_set({"pvfss_retention": ret.name, "pvfss_retention_journal_entry": je})


def hold_purchase(pi):
	"""FIN-51: Creditors -> Retention Payable for the same supplier, on submit."""
	if pi.is_return or not flt(pi.get("pvfss_retention_amount")):
		return
	months = (
		cint(frappe.db.get_value("Project", pi.project, "pvfss_warranty_months")) if pi.get("project") else 0
	)
	ret = _record(pi, PAYABLE, pi.pvfss_retention_amount, months)
	base = ret.base_amount
	party = {"party_type": "Supplier", "party": pi.supplier}
	je = accounts.post(
		pi.company,
		[
			{
				"account": pi.credit_to,
				"debit": base,
				"exchange_rate": pi.conversion_rate,
				"reference_type": "Purchase Invoice",
				"reference_name": pi.name,
				**party,
			},
			{"account": accounts.get(pi.company, "retention_payable"), "credit": base, **party},
		],
		_("Retention held on {0}").format(pi.name),
		posting_date=pi.posting_date,
		project=pi.get("project"),
	)
	ret.db_set("hold_journal_entry", je)
	pi.db_set({"pvfss_retention": ret.name, "pvfss_retention_journal_entry": je})


def undo(doc):
	"""Before an invoice is cancelled: reverse its retention posting and drop the record."""
	accounts.cancel(doc.get("pvfss_retention_journal_entry"))
	if doc.get("pvfss_retention"):
		status = frappe.db.get_value("Retention", doc.pvfss_retention, "status")
		if status == "Released":
			frappe.throw(_("Retention {0} is already released.").format(doc.pvfss_retention))
		frappe.delete_doc("Retention", doc.pvfss_retention, ignore_permissions=True, force=True)
		doc.db_set({"pvfss_retention": None, "pvfss_retention_journal_entry": None})


def release_entry(ret):
	company = ret.company
	party = {"party_type": ret.party_type, "party": ret.party}
	main = accounts.party_account(ret.party_type, ret.party, company)
	if ret.direction == RECEIVABLE:
		rows = [
			{"account": main, "debit": ret.base_amount, **party},
			{"account": accounts.get(company, "retention_receivable"), "credit": ret.base_amount, **party},
		]
	else:
		rows = [
			{"account": accounts.get(company, "retention_payable"), "debit": ret.base_amount, **party},
			{"account": main, "credit": ret.base_amount, **party},
		]
	return accounts.post(company, rows, _("Retention {0} released").format(ret.name), project=ret.project)


@frappe.whitelist()
def hold_project_retention(project: str):
	"""FIN-50 (Total project value basis): record the retention once against the project."""
	accounts.require_finance_manager()
	doc = frappe.get_doc("Project", project)
	if frappe.db.exists("Retention", {"source_doctype": "Project", "source_invoice": project}):
		frappe.throw(_("Retention for {0} is already recorded.").format(project))
	so = doc.get("sales_order") or frappe.db.get_value(
		"Sales Order", {"project": project, "docstatus": 1}, "name"
	)
	if not so:
		frappe.throw(_("Project {0} has no Customer PO.").format(project))
	so_doc = frappe.get_doc("Sales Order", so)
	amount = flt(so_doc.base_grand_total * flt(so_doc.pvfss_retention_pct) / 100, 2)
	ret = frappe.get_doc(
		{
			"doctype": "Retention",
			"direction": RECEIVABLE,
			"company": so_doc.company,
			"party_type": "Customer",
			"party": so_doc.customer,
			"project": project,
			"source_doctype": "Project",
			"source_invoice": project,
			"currency": frappe.get_cached_value("Company", so_doc.company, "default_currency"),
			"amount": amount,
			"base_amount": amount,
			"held_date": nowdate(),
			"release_due_date": add_months(nowdate(), cint(so_doc.pvfss_warranty_months) or 12),
		}
	)
	ret.flags.ignore_permissions = True
	ret.insert()
	party = {"party_type": "Customer", "party": so_doc.customer}
	je = accounts.post(
		so_doc.company,
		[
			{"account": accounts.get(so_doc.company, "retention_receivable"), "debit": amount, **party},
			{
				"account": accounts.party_account("Customer", so_doc.customer, so_doc.company),
				"credit": amount,
				**party,
			},
		],
		_("Retention held on project {0}").format(project),
		project=project,
	)
	ret.db_set("hold_journal_entry", je)
	return ret.name
