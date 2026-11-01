"""Step 02 tests: company defaults, masters, custom fields and the GEN-50 carry-forward."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from pvfss.setup import masters
from pvfss.setup.customisations_02 import LINE_TABLES, NAMING_SERIES
from pvfss.tests import factories as f

LINE_FIELDS = (
	"pvfss_customer_line_ref",
	"pvfss_specification",
	"pvfss_material_type",
	"pvfss_product_category",
	"pvfss_inspection_req",
	"pvfss_doc_req",
	"pvfss_heat_traceable",
)


class TestCompanyDefaults(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def test_GEN_11_usd_aed_peg(self):
		rate = frappe.db.get_value(
			"Currency Exchange", {"from_currency": "USD", "to_currency": "AED"}, "exchange_rate"
		)
		self.assertEqual(rate, masters.USD_AED_PEG)
		self.assertTrue(frappe.db.get_value("Currency", "USD", "enabled"))

	def test_GEN_12_tax_templates(self):
		for title, _rate, _acc, sales, purchase in masters.TAX_TEMPLATES:
			if sales:
				self.assertTrue(
					frappe.db.exists(
						"Sales Taxes and Charges Template", {"title": title, "company": f.TEST_COMPANY}
					),
					title,
				)
			if purchase:
				self.assertTrue(
					frappe.db.exists(
						"Purchase Taxes and Charges Template", {"title": title, "company": f.TEST_COMPANY}
					),
					title,
				)

	def test_MD_20_warehouses(self):
		for name in masters.WAREHOUSES:
			self.assertTrue(frappe.db.exists("Warehouse", f.warehouse(name)), name)

	def test_MD_seed_is_idempotent(self):
		before = frappe.db.count("Item Group"), frappe.db.count("Payment Terms Template")
		masters.setup_company(f.TEST_COMPANY)
		self.assertEqual(before, (frappe.db.count("Item Group"), frappe.db.count("Payment Terms Template")))


class TestMasters(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.db.rollback()

	def test_MD_10_item_groups(self):
		for name, parent, _is_group in masters.ITEM_GROUPS:
			self.assertTrue(frappe.db.exists("Item Group", name), name)
			if parent:
				self.assertEqual(frappe.db.get_value("Item Group", name, "parent_item_group"), parent)

	def test_MD_11_item_attributes(self):
		for name in masters.ITEM_ATTRIBUTES:
			self.assertTrue(frappe.db.exists("Item Attribute", name), name)

	def test_MD_14_uoms(self):
		for name in masters.UOMS:
			self.assertTrue(frappe.db.exists("UOM", name), name)

	def test_MD_21_payment_terms(self):
		for name in masters.PAYMENT_TERMS:
			self.assertTrue(frappe.db.exists("Payment Terms Template", name), name)

	def test_MD_25_lost_reasons(self):
		for reason in masters.LOST_REASONS:
			self.assertTrue(frappe.db.exists("Opportunity Lost Reason", reason), reason)

	def test_MD_01_customer_fields(self):
		customer = f.make_customer("_PVFSS MD01 Contractor", pvfss_portal_vendor_code="V-123")
		self.assertEqual(customer.pvfss_customer_type, "EPC")
		self.assertEqual(customer.pvfss_portal_vendor_code, "V-123")

	def test_MD_12_heat_traceable_stock_item_gets_batch_tracking(self):
		item = f.make_item("_PVFSS MD12 Pipe")
		self.assertTrue(item.pvfss_heat_traceable)
		self.assertTrue(item.has_batch_no)
		self.assertTrue(item.pvfss_irn_required)

	def test_MD_13_service_item_not_heat_traceable(self):
		item = f.make_item("_PVFSS MD13 Freight", is_stock_item=0, item_group="Freight")
		self.assertFalse(item.pvfss_heat_traceable)
		self.assertFalse(item.has_batch_no)

	def test_MD_02_client_project_unique_mtc_override(self):
		cp = f.make_client_project("_PVFSS-MD02")
		cp.append(
			"mtc_age_overrides",
			{"product_category": "Pipes - CS", "material_type": "CS", "max_age_months": 24},
		)
		cp.save()
		cp.append(
			"mtc_age_overrides",
			{"product_category": "Pipes - CS", "material_type": "CS", "max_age_months": 12},
		)
		self.assertRaises(frappe.ValidationError, cp.save)

		cp.reload()
		self.assertEqual(cp.get_mtc_age_override("Pipes - CS", "CS").max_age_months, 24)
		self.assertIsNone(cp.get_mtc_age_override("Pipes - CS", "SS"))

	def test_MD_23_inspection_agency(self):
		agency = frappe.get_doc(
			{"doctype": "Inspection Agency", "agency_name": "_PVFSS TPI Ltd", "agency_type": "Third-party"}
		).insert()
		self.assertTrue(agency.active)

	def test_MD_24_employee_inspector_fields(self):
		meta = frappe.get_meta("Employee")
		for fieldname in ("pvfss_is_inspector", "pvfss_inspector_qualifications", "pvfss_nationality_uae"):
			self.assertTrue(meta.has_field(fieldname), fieldname)


class TestNamingAndLineFields(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.db.rollback()

	def test_GEN_40_naming_series_defaults(self):
		for dt, series in NAMING_SERIES.items():
			field = frappe.get_meta(dt).get_field("naming_series")
			self.assertEqual(field.default, series, dt)
			self.assertEqual(field.options.split("\n")[0], series, dt)

	def test_GEN_50_line_fields_on_every_item_table(self):
		for dt in LINE_TABLES:
			meta = frappe.get_meta(dt)
			for fieldname in LINE_FIELDS:
				self.assertTrue(meta.has_field(fieldname), f"{dt}.{fieldname}")

	def test_GEN_50_line_values_carry_from_quotation_to_invoice(self):
		"""One value entered on a line arrives on every later document (plan §5.4)."""
		from erpnext.selling.doctype.quotation.quotation import make_sales_order
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice

		customer = f.make_customer()
		item = f.make_item("_PVFSS GEN50 Service", is_stock_item=0, item_group="Testing")
		line = {
			"item_code": item.name,
			"qty": 2,
			"rate": 100,
			"pvfss_customer_line_ref": "L-0007",
			"pvfss_specification": "ASTM A106 Gr.B 6in SCH40 BE",
			"pvfss_inspection_req": "TPI witness hydro",
			"pvfss_doc_req": "MTC 3.2",
		}
		qtn = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": customer.name,
				"company": f.TEST_COMPANY,
				"transaction_date": nowdate(),
				"currency": "AED",
				"selling_price_list": f.price_list(),
				"valid_till": f.delivery_date(),
				"items": [line],
			}
		).insert()
		qtn = f.submit_quotation(qtn)

		so = make_sales_order(qtn.name)
		so.delivery_date = f.delivery_date()
		f.customer_po(so).insert()
		so = f.submit_sales_order(so)

		dn = make_delivery_note(so.name)
		si = make_sales_invoice(so.name)
		for doc in (so, dn, si):
			row = doc.items[0]
			for fieldname in (
				"pvfss_customer_line_ref",
				"pvfss_specification",
				"pvfss_inspection_req",
				"pvfss_doc_req",
			):
				self.assertEqual(row.get(fieldname), line[fieldname], f"{doc.doctype}.{fieldname}")
		self.assertTrue(so.name.startswith("CPO-"))
