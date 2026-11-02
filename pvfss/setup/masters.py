"""Master data seeding (GEN-10 to GEN-12, MD-10 to MD-25).

Two entry points, both idempotent (they only create what is missing):

* ``seed_global()`` - company-independent masters: item groups, item attributes, UOMs,
  lost reasons, payment terms. Runs on install and migrate.
* ``setup_company(company)`` - company defaults: currencies and the USD peg, warehouses,
  tax templates. Runs after the setup wizard, or by hand:

      bench --site <site> execute pvfss.setup.masters.setup_company --args '["PVFSS Solutions LLC"]'
"""

import frappe
from frappe.utils import flt, today

USD_AED_PEG = 3.6725  # GEN-11

# MD-10: (name, parent, is_group)
ITEM_GROUPS = [
	("Pipes", None, 1),
	("Pipes - CS", "Pipes", 0),
	("Pipes - SS", "Pipes", 0),
	("Valves", None, 0),
	("Fittings", None, 0),
	("Flanges", None, 0),
	("Plates", None, 0),
	("Services", None, 1),
	("Freight", "Services", 0),
	("Inspection", "Services", 0),
	("Documentation", "Services", 0),
	("Testing", "Services", 0),
	("Others", None, 0),
]

# MD-11: values are seeded from PVFSS's inquiries in week 1; these are starting values.
ITEM_ATTRIBUTES = {
	"Material Grade": [
		"A106 Gr.B",
		"A333 Gr.6",
		"API 5L X52",
		"A312 TP316L",
		"A105",
		"A182 F316L",
		"Duplex 2205",
	],
	"Size (NPS / OD)": ['1/2"', '3/4"', '1"', '2"', '3"', '4"', '6"', '8"', '10"', '12"'],
	"Schedule / Wall Thickness": ["SCH 10", "SCH 40", "SCH 80", "SCH 160", "STD", "XS", "XXS"],
	"Pressure Class / Rating": ["150#", "300#", "600#", "900#", "1500#", "2500#"],
	"Standard": ["ASTM", "ASME", "API", "EN", "BS", "DIN"],
	"End Type": ["BE", "PE", "TE", "Socket Weld", "Threaded", "Flanged"],
	"Facing": ["RF", "FF", "RTJ"],
	"Valve Type": ["Gate", "Globe", "Check", "Ball", "Butterfly", "Plug", "Needle"],
	"Plate Thickness": ["6 mm", "8 mm", "10 mm", "12 mm", "16 mm", "20 mm", "25 mm"],
}

# MD-14
UOMS = {"Nos": 1, "Meter": 0, "Kg": 0, "Ton": 0, "Set": 1}

# MD-25
LOST_REASONS = [
	"Price",
	"Lead time",
	"Technical non-compliance",
	"Not on AVL",
	"No bid by PVFSS",
	"Cancelled by client",
	"Other",
]

# MD-21: template -> list of (payment term, portion %, credit days, mode)
PAYMENT_TERMS = {
	"Advance 100%": [("Advance", 100, 0, None)],
	"Advance 30% / Balance on delivery": [("Advance 30%", 30, 0, None), ("Balance on delivery", 70, 0, None)],
	"TT 30 days": [("TT 30 days", 100, 30, None)],
	"TT 60 days": [("TT 60 days", 100, 60, None)],
	"TT 90 days": [("TT 90 days", 100, 90, None)],
	"LC at sight": [("LC at sight", 100, 0, None)],
	"LC usance 90 days": [("LC usance 90 days", 100, 90, None)],
	"PDC": [("PDC", 100, 0, None)],
}

# MD-20: warehouse name -> is_group
WAREHOUSES = {
	"PVFSS Yard": 0,
	"Supplier Premises": 1,
	"Port / In Transit": 0,
	"Quarantine": 0,
}


# --------------------------------------------------------------------------- global
def seed_global():
	seed_item_groups()
	seed_mtc_age_rules()
	seed_quality_masters()
	seed_item_attributes()
	seed_uoms()
	seed_lost_reasons()
	seed_payment_terms()
	seed_email_templates()
	seed_modes_of_payment()
	seed_risk_matrix()


def seed_risk_matrix():
	from pvfss.pvfss_hse import risk

	risk.seed()  # HSE-02 default bands


# FIN-30
MODES_OF_PAYMENT = (("TT", "Bank"), ("Cheque", "Bank"), ("PDC", "Bank"), ("LC", "Bank"), ("Cash", "Cash"))


def seed_modes_of_payment():
	for name, kind in MODES_OF_PAYMENT:
		if not frappe.db.exists("Mode of Payment", name):
			frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": name, "type": kind}).insert(
				ignore_permissions=True
			)


EMAIL_TEMPLATES = {
	# SCR-RFQ-04 / GEN-62: RFQ email (one per supplier, RFQ PDF attached by ERPNext)
	"PVFSS RFQ": {
		"subject": "RFQ {{ doc.name }} - due {{ frappe.utils.formatdate(doc.pvfss_supplier_due_date) }}",
		"response": (
			"<p>Dear {{ supplier_name or 'Supplier' }},</p>"
			"<p>Please find attached our Request for Quotation {{ doc.name }}. Kindly send your best "
			"offer by {{ frappe.utils.formatdate(doc.pvfss_supplier_due_date) }}, stating per line the "
			"unit price and currency, lead time, availability (ready stock or manufacture), origin, "
			"manufacturer, technical compliance and any deviations, offer validity, payment terms "
			"and Incoterm.</p><p>Regards,<br>{{ doc.company }}</p>"
		),
	},
}


def seed_email_templates():
	for name, values in EMAIL_TEMPLATES.items():
		if not frappe.db.exists("Email Template", name):
			frappe.get_doc({"doctype": "Email Template", "name": name, **values}).insert(
				ignore_permissions=True
			)


# SMR-20 company defaults; other categories stay blank (no limit, warn) until PVFSS confirms (Q-01)
MTC_AGE_RULES = [("Pipes", "CS", 24), ("Pipes", "SS", 36)]


def seed_mtc_age_rules():
	for category, material, months in MTC_AGE_RULES:
		if not frappe.db.exists("Item Group", category):
			continue
		if frappe.db.exists("MTC Age Rule", {"product_category": category, "material_type": material}):
			continue
		frappe.get_doc(
			{
				"doctype": "MTC Age Rule",
				"product_category": category,
				"material_type": material,
				"max_age_months": months,
				"reference_basis": "Company default (requirements SMR-20)",
				"active": 1,
			}
		).insert(ignore_permissions=True)


# QA-14 / SCR-QA-12 and QA-36 / SCR-QA-03 seeds
SAMPLING_RULES = [("Pipes", "1 sample of 350 mm per heat for mechanical / chemical tests", 1, 0, 350)]
SMR_ITP_TEMPLATE = "SMR - document review + visual"
SMR_ITP_POINTS = [
	(10, "Document review (MTC, tally, certificates)", "Document review", "R", "R", "R"),
	(20, "Visual and marking check", "Inspection", "H", "W", "W"),
	(30, "Dimensional check", "Inspection", "W", "W", "R"),
]


def seed_quality_masters():
	for category, text, per_heat, per_lot, length in SAMPLING_RULES:
		if frappe.db.exists("Item Group", category) and not frappe.db.exists(
			"Sampling Rule", {"product_category": category}
		):
			frappe.get_doc(
				{
					"doctype": "Sampling Rule",
					"product_category": category,
					"rule_text": text,
					"samples_per_heat": per_heat,
					"samples_per_lot": per_lot,
					"sample_length_mm": length,
					"active": 1,
				}
			).insert(ignore_permissions=True)
	if not frappe.db.exists("ITP Template", SMR_ITP_TEMPLATE):
		frappe.get_doc(
			{
				"doctype": "ITP Template",
				"template_name": SMR_ITP_TEMPLATE,
				"supply_route": "SMR",
				"points": [
					{
						"seq": seq,
						"activity": activity,
						"point_type": kind,
						"check_type": activity.split(" (")[0],
						"pvfss_point": p,
						"tpi_point": t,
						"customer_point": c,
					}
					for seq, activity, kind, p, t, c in SMR_ITP_POINTS
				],
			}
		).insert(ignore_permissions=True)


def _root_item_group():
	return frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ["in", ["", None]]})


def seed_item_groups():
	root = _root_item_group()
	if not root:
		return  # before the setup wizard; setup_wizard_complete seeds them
	for name, parent, is_group in ITEM_GROUPS:
		if frappe.db.exists("Item Group", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": name,
				"parent_item_group": parent or root,
				"is_group": is_group,
			}
		).insert(ignore_permissions=True)


def seed_item_attributes():
	for name, values in ITEM_ATTRIBUTES.items():
		if frappe.db.exists("Item Attribute", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": name,
				"item_attribute_values": [
					{"attribute_value": v, "abbr": a} for v, a in zip(values, _abbrs(values), strict=True)
				],
			}
		).insert(ignore_permissions=True)


def _abbrs(values):
	"""Short unique variant-code abbreviations, e.g. '1/2"' -> '1-2IN', 'A106 Gr.B' -> 'A106GRB'."""
	out = []
	for value in values:
		base = value.upper().replace('"', "IN").replace("/", "-").replace("#", "LB")
		base = "".join(ch for ch in base if ch.isalnum() or ch == "-")[:12] or "X"
		abbr, n = base, 1
		while abbr in out:
			n += 1
			abbr = f"{base}{n}"
		out.append(abbr)
	return out


def seed_uoms():
	for name, whole in UOMS.items():
		if not frappe.db.exists("UOM", name):
			frappe.get_doc({"doctype": "UOM", "uom_name": name, "must_be_whole_number": whole}).insert(
				ignore_permissions=True
			)


def seed_lost_reasons():
	"""MD-25: same values for inquiries and quotations."""
	for reason in LOST_REASONS:
		for doctype, field in (
			("Opportunity Lost Reason", "lost_reason"),
			("Quotation Lost Reason", "order_lost_reason"),
		):
			if not frappe.db.exists(doctype, reason):
				frappe.get_doc({"doctype": doctype, field: reason}).insert(ignore_permissions=True)


def seed_payment_terms():
	for template, terms in PAYMENT_TERMS.items():
		for term, _portion, days, _mode in terms:
			if not frappe.db.exists("Payment Term", term):
				frappe.get_doc(
					{
						"doctype": "Payment Term",
						"payment_term_name": term,
						"due_date_based_on": "Day(s) after invoice date",
						"credit_days": days,
					}
				).insert(ignore_permissions=True)
		if frappe.db.exists("Payment Terms Template", template):
			continue
		frappe.get_doc(
			{
				"doctype": "Payment Terms Template",
				"template_name": template,
				"terms": [
					{
						"payment_term": term,
						"invoice_portion": portion,
						"due_date_based_on": "Day(s) after invoice date",
						"credit_days": days,
					}
					for term, portion, days, _mode in terms
				],
			}
		).insert(ignore_permissions=True)


GENERIC_ITEM = "GENERIC-LINE"


def seed_generic_item():
	"""Placeholder item for inquiry lines until a variant is chosen (CRM-03, CRM-04)."""
	if not frappe.db.exists("Item Group", "Others"):
		return
	if not frappe.db.exists("Item", GENERIC_ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": GENERIC_ITEM,
				"item_name": "Generic inquiry line",
				"item_group": "Others",
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 1,
				"description": "Placeholder until the variant is chosen. The line specification holds the full text.",
			}
		).insert(ignore_permissions=True)
	if not frappe.db.get_single_value("PVFSS Settings", "generic_inquiry_item"):
		frappe.db.set_single_value("PVFSS Settings", "generic_inquiry_item", GENERIC_ITEM)


# --------------------------------------------------------------------------- company
def setup_wizard_complete(wizard_args=None):
	from pvfss.setup.install import apply_operating_defaults

	company = (wizard_args or {}).get("company_name") or frappe.defaults.get_global_default("company")
	if company and frappe.db.exists("Company", company):
		setup_company(company)
	apply_operating_defaults()  # the wizard resets Buying Settings


def setup_company(company):
	seed_global()
	seed_generic_item()
	setup_currencies()
	setup_warehouses(company)
	setup_tax_templates(company)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (setup step run from install / setup wizard hooks; later steps need it persisted)


def setup_currencies():
	for currency in ("AED", "USD"):
		frappe.db.set_value("Currency", currency, "enabled", 1)
	filters = {"from_currency": "USD", "to_currency": "AED", "for_buying": 1, "for_selling": 1}
	if not frappe.db.exists("Currency Exchange", filters):
		frappe.get_doc(
			{
				"doctype": "Currency Exchange",
				"date": "2020-01-01",
				"exchange_rate": USD_AED_PEG,
				**filters,
			}
		).insert(ignore_permissions=True)


def setup_warehouses(company):
	abbr = frappe.get_cached_value("Company", company, "abbr")
	root = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]}
	)
	for name, is_group in WAREHOUSES.items():
		if frappe.db.exists("Warehouse", f"{name} - {abbr}"):
			continue
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": name,
				"company": company,
				"is_group": is_group,
				"parent_warehouse": root,
			}
		).insert(ignore_permissions=True)


def _tax_account(company, account_name, rate):
	"""Find or create a Duties and Taxes account named ``account_name``."""
	abbr = frappe.get_cached_value("Company", company, "abbr")
	name = frappe.db.get_value("Account", {"company": company, "account_name": account_name, "is_group": 0})
	if name:
		return name
	parent = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Tax", "is_group": 1}
	) or frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Liability", "is_group": 1, "parent_account": ["is", "set"]},
	)
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": account_name,
				"company": company,
				"parent_account": parent,
				"account_type": "Tax",
				"tax_rate": flt(rate),
			}
		)
		.insert(ignore_permissions=True)
		.name
		or f"{account_name} - {abbr}"
	)


# GEN-12: (title, rate, account name, sales, purchase)
TAX_TEMPLATES = [
	("UAE VAT 5%", 5, "VAT 5%", 1, 1),
	("UAE VAT Zero (Exports)", 0, "VAT Zero", 1, 1),
	("UAE VAT Exempted", 0, "VAT Exempted", 1, 1),
	("UAE Out of Scope", 0, None, 1, 1),
	("UAE Reverse Charge on Imports", 5, "VAT 5%", 0, 1),
]


def setup_tax_templates(company):
	for title, rate, account_name, sales, purchase in TAX_TEMPLATES:
		account = _tax_account(company, account_name, rate) if account_name else None
		taxes = (
			[{"charge_type": "On Net Total", "account_head": account, "rate": rate, "description": title}]
			if account
			else []
		)
		for flag, doctype in (
			(sales, "Sales Taxes and Charges Template"),
			(purchase, "Purchase Taxes and Charges Template"),
		):
			if not flag or frappe.db.exists(doctype, {"title": title, "company": company}):
				continue
			doc = frappe.get_doc({"doctype": doctype, "title": title, "company": company, "taxes": taxes})
			if title == "UAE VAT 5%":
				doc.is_default = 1
			doc.insert(ignore_permissions=True)
