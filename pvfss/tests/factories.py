"""Test data factories shared by every PVFSS test (plan §4.3).

Each factory returns an existing record when one with the same name is already there, so
tests can call them freely.
"""

import frappe
from frappe.utils import add_days, nowdate

TEST_COMPANY = "PVFSS Test LLC"
TEST_ABBR = "PTL"


def ensure_test_company():
	"""Run the setup wizard once on a blank test site and apply PVFSS company defaults."""
	from pvfss.setup import masters

	if not frappe.db.exists("Company", TEST_COMPANY):
		if not frappe.get_all("Company", limit=1):
			_run_setup_wizard()
		else:
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": TEST_COMPANY,
					"abbr": TEST_ABBR,
					"country": "United Arab Emirates",
					"default_currency": "AED",
					"chart_of_accounts": "Standard",
				}
			).insert(ignore_permissions=True)
	masters.setup_company(TEST_COMPANY)
	return TEST_COMPANY


def _run_setup_wizard():
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = nowdate()[:4]
	setup_complete(
		{
			"language": "English",
			"country": "United Arab Emirates",
			"timezone": "Asia/Dubai",
			"currency": "AED",
			"full_name": "Test Administrator",
			"email": "test-admin@example.com",
			"password": "test-admin-password-1",
			"company_name": TEST_COMPANY,
			"company_abbr": TEST_ABBR,
			"chart_of_accounts": "Standard",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"setup_demo": 0,
		}
	)
	frappe.set_user("Administrator")


def price_list(name="Standard Selling", selling=1):
	if not frappe.db.exists("Price List", name):
		frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": name,
				"currency": "AED",
				"selling": selling,
				"buying": 0 if selling else 1,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
	return name


def warehouse(name="PVFSS Yard"):
	return f"{name} - {TEST_ABBR}"


def make_customer(name="_PVFSS Test Contractor", **kw):
	if frappe.db.exists("Customer", name):
		return frappe.get_doc("Customer", name)
	return frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Company",
			"pvfss_customer_type": "EPC",
			**kw,
		}
	).insert(ignore_permissions=True)


def make_supplier(name="_PVFSS Test Supplier", **kw):
	if frappe.db.exists("Supplier", name):
		return frappe.get_doc("Supplier", name)
	return frappe.get_doc(
		{"doctype": "Supplier", "supplier_name": name, "supplier_group": _supplier_group(), **kw}
	).insert(ignore_permissions=True)


def _supplier_group():
	return (
		frappe.db.get_value("Supplier Group", {"is_group": 0})
		or frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": "_PVFSS Test Suppliers"})
		.insert(ignore_permissions=True)
		.name
	)


def make_item(item_code="_PVFSS Test Pipe", is_stock_item=1, item_group="Pipes - CS", **kw):
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code)
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": item_group,
			"stock_uom": "Meter",
			"is_stock_item": is_stock_item,
			"pvfss_material_type": "CS",
			**kw,
		}
	).insert(ignore_permissions=True)


def make_client_project(code="_PVFSS-CP-001", **kw):
	if frappe.db.exists("Client Project", code):
		return frappe.get_doc("Client Project", code)
	return frappe.get_doc(
		{
			"doctype": "Client Project",
			"project_code": code,
			"title": "Test Client Project",
			"main_contractor": make_customer().name,
			"contract_model": "EPC",
			**kw,
		}
	).insert(ignore_permissions=True)


def delivery_date(days=30):
	return add_days(nowdate(), days)
