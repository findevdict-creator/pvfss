"""Developer helper for step 14-finance: invoice, payment, Customer PO, Company and Employee fields.

bench --site pvfss.localhost execute pvfss.setup.customisations_14.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from pvfss.pvfss_finance.accounts import ACCOUNTS

MODULE = "PVFSS Finance"


def _f(fieldname, fieldtype, label, after, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype, "insert_after": after, **kw}
	if label:
		d["label"] = label
	return d


def _retention_fields(after):
	ro = {"read_only": 1, "no_copy": 1}
	posted = {"read_only": 1, "no_copy": 1, "allow_on_submit": 1}
	return [
		_f("pvfss_retention_section", "Section Break", "Retention", after, collapsible=1),
		_f("pvfss_retention_pct", "Percent", "Retention %", "pvfss_retention_section", **ro),
		_f(
			"pvfss_retention_amount",
			"Currency",
			"Retention Amount",
			"pvfss_retention_pct",
			options="currency",
			**ro,
		),
		_f("pvfss_retention_column", "Column Break", None, "pvfss_retention_amount"),
		_f(
			"pvfss_retention",
			"Link",
			"Retention Record",
			"pvfss_retention_column",
			options="Retention",
			**posted,
		),
		_f(
			"pvfss_retention_journal_entry",
			"Link",
			"Retention JE",
			"pvfss_retention",
			options="Journal Entry",
			**posted,
		),
	]


def custom_fields():
	ro = {"read_only": 1, "no_copy": 1}
	posted = {"read_only": 1, "no_copy": 1, "allow_on_submit": 1}
	company_accounts = [
		_f(
			"pvfss_accounts_section",
			"Section Break",
			"PVFSS Accounts",
			"default_payable_account",
			collapsible=1,
		)
	]
	after = "pvfss_accounts_section"
	for key, (name, *_rest) in ACCOUNTS.items():
		fieldname = f"pvfss_{key}_account"
		company_accounts.append(_f(fieldname, "Link", f"{name} Account", after, options="Account"))
		after = fieldname
	return {
		"Sales Invoice": [
			_f("pvfss_customer_po_no", "Data", "Customer PO No", "po_no", in_list_view=1, **ro),
			_f("pvfss_supply_date", "Date", "Supply Date", "pvfss_customer_po_no"),
			_f(
				"pvfss_aed_taxable",
				"Currency",
				"Taxable Total (AED)",
				"base_net_total",
				options="Company:company:default_currency",
				**ro,
			),
			_f(
				"pvfss_aed_vat",
				"Currency",
				"VAT (AED)",
				"pvfss_aed_taxable",
				options="Company:company:default_currency",
				**ro,
			),
			*_retention_fields("terms"),
			_f("pvfss_retention_base", "Data", "Retention Base", "pvfss_retention_pct", **ro),
			_f(
				"pvfss_vc_amount",
				"Currency",
				"Variable Consideration Allocated",
				"pvfss_retention_journal_entry",
				options="currency",
				**posted,
			),
			_f(
				"pvfss_vc_journal_entry",
				"Link",
				"VC Journal Entry",
				"pvfss_vc_amount",
				options="Journal Entry",
				**posted,
			),
		],
		"Purchase Invoice": [
			_f("pvfss_match_status", "Data", "3-way Match", "bill_date", **ro),
			*_retention_fields("terms"),
		],
		"Purchase Invoice Item": [
			_f("pvfss_match", "Data", "Match", "pvfss_cost_type", in_list_view=1, columns=1, **ro),
		],
		"Sales Order": [
			_f(
				"pvfss_retention_base",
				"Select",
				"Retention Base",
				"pvfss_retention_basis",
				options="Net\nGross",
				default="Net",
				description="Retention on the invoice net or gross amount (Q-06).",
			),
			_f(
				"pvfss_vc_section",
				"Section Break",
				"Variable Consideration (IFRS 15)",
				"pvfss_advance_billing_allowed",
				collapsible=1,
			),
			_f(
				"pvfss_variable_consideration",
				"Table",
				"Variable Consideration",
				"pvfss_vc_section",
				options="Variable Consideration",
				allow_on_submit=1,
			),
		],
		"Payment Entry": [
			_f("pvfss_pdc", "Link", "Post-Dated Cheque", "mode_of_payment", options="Post-Dated Cheque"),
			_f("pvfss_lc", "Link", "Letter of Credit", "pvfss_pdc", options="Letter of Credit"),
			_f("pvfss_needs_director", "Check", "Needs Director Approval", "pvfss_lc", hidden=1, **ro),
		],
		"Company": company_accounts,
		"Employee": [
			_f(
				"pvfss_petty_cash_account",
				"Link",
				"Petty Cash Account",
				"company",
				options="Account",
				description="Cash account of this custodian (FIN-65).",
			),
		],
	}


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("14-finance customisations applied")
