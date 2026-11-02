"""PVFSS ledger accounts (FIN-01) and a small Journal Entry helper used by every finance posting.

The extra accounts are created on first use under the matching group of the company's chart
and remembered on the Company (``pvfss_<key>_account``), so Finance can repoint them later.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from pvfss.utils.importing import is_import

# key: (account name, parent group candidates, root type, account type)
ACCOUNTS = {
	"retention_receivable": ("Retention Receivable", ("Accounts Receivable",), "Asset", "Receivable"),
	"retention_payable": ("Retention Payable", ("Accounts Payable",), "Liability", "Payable"),
	"pdc_receivable": ("PDC Receivable", ("Accounts Receivable",), "Asset", "Receivable"),
	"pdc_payable": ("PDC Payable", ("Accounts Payable",), "Liability", "Payable"),
	"lc_margin": ("LC Margin", ("Loans and Advances (Assets)", "Current Assets"), "Asset", ""),
	"vc_accrual": ("Variable Consideration Accrual", ("Loans and Advances (Assets)", "Current Assets"), "Asset", ""),
	"lc_charges": ("LC Charges", ("Indirect Expenses", "Expenses"), "Expense", ""),
	"vat_input": ("VAT Input", ("Tax Assets", "Current Assets"), "Asset", "Tax"),
}


def _parent(company, candidates, root_type):
	for name in candidates:
		parent = frappe.db.get_value(
			"Account", {"company": company, "account_name": name, "is_group": 1}, "name"
		)
		if parent:
			return parent
	return frappe.db.get_value(
		"Account", {"company": company, "root_type": root_type, "is_group": 1}, "name", order_by="lft desc"
	)


def get(company, key):
	"""The company's account for ``key``, created under the matching group when missing."""
	fieldname = f"pvfss_{key}_account"
	account = frappe.db.get_value("Company", company, fieldname)
	if account:
		return account
	name, candidates, root_type, account_type = ACCOUNTS[key]
	account = frappe.db.get_value("Account", {"company": company, "account_name": name, "is_group": 0}, "name")
	if not account:
		doc = frappe.get_doc(
			{
				"doctype": "Account",
				"company": company,
				"account_name": name,
				"parent_account": _parent(company, candidates, root_type),
				"account_type": account_type,
				"account_currency": frappe.get_cached_value("Company", company, "default_currency"),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		account = doc.name
	frappe.db.set_value("Company", company, fieldname, account, update_modified=False)
	return account


def party_account(party_type, party, company):
	from erpnext.accounts.party import get_party_account

	return get_party_account(party_type, party, company)


def post(company, rows, remark, posting_date=None, project=None):
	"""Insert and submit a Journal Entry.

	Each row: account, debit or credit (company currency), optional party_type, party,
	reference_type, reference_name, exchange_rate (for a foreign-currency account) and project.
	"""
	currency = frappe.get_cached_value("Company", company, "default_currency")
	cost_center = frappe.get_cached_value("Company", company, "cost_center")
	je = frappe.new_doc("Journal Entry")
	je.update(
		{
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": posting_date or nowdate(),
			"user_remark": remark,
		}
	)
	for row in rows:
		debit, credit = flt(row.get("debit")), flt(row.get("credit"))
		if not (debit or credit):
			continue
		account_currency = frappe.get_cached_value("Account", row["account"], "account_currency") or currency
		rate = 1
		if account_currency != currency:
			rate = flt(row.get("exchange_rate")) or 1
			je.multi_currency = 1
		je.append(
			"accounts",
			{
				"account": row["account"],
				"party_type": row.get("party_type"),
				"party": row.get("party"),
				"debit_in_account_currency": flt(debit / rate, 2),
				"credit_in_account_currency": flt(credit / rate, 2),
				"exchange_rate": rate,
				"reference_type": row.get("reference_type"),
				"reference_name": row.get("reference_name"),
				"project": row.get("project") or project,
				"cost_center": cost_center,
			},
		)
	if not je.accounts:
		return None
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return je.name


def cancel(je_name):
	if je_name and frappe.db.get_value("Journal Entry", je_name, "docstatus") == 1:
		je = frappe.get_doc("Journal Entry", je_name)
		je.flags.ignore_permissions = True
		je.cancel()


def require_finance_manager():
	if not set(frappe.get_roles()) & {"Finance Manager", "System Manager"} and not is_import():
		frappe.throw(_("Only a Finance Manager can do this."), frappe.PermissionError)
