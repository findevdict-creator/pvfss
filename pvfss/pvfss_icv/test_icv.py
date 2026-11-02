"""Module 13 tests (ICV-01 to ICV-20). Names carry the requirement ID (GEN-07)."""

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, nowdate

from pvfss.pvfss_icv import icv
from pvfss.pvfss_icv.doctype.icv_period_data import icv_period_data as period_module
from pvfss.tests import factories as f

SERVICE = "_PVFSS ICV Freight"


def certificate(no, issue_date, score=35):
	return frappe.get_doc(
		{
			"doctype": "ICV Certificate",
			"certificate_no": no,
			"certifying_body": "Certifier",
			"issue_date": issue_date,
			"score_pct": score,
			"financial_year": "2025",
			"attachment": "/files/icv.pdf",
		}
	).insert()


def supplier(name, uae, score=0):
	doc = f.make_supplier(name)
	doc.db_set(
		{
			"pvfss_uae_based": uae,
			"pvfss_icv_score": score,
			"pvfss_icv_cert_expiry": add_months(nowdate(), 12) if score else None,
			"allow_purchase_invoice_creation_without_purchase_order": 1,
		}
	)
	return doc.name


def service_invoice(supplier_name, amount, bill_no):
	item = f.make_item(SERVICE, is_stock_item=0, item_group="Testing").name
	pi = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"supplier": supplier_name,
			"company": f.TEST_COMPANY,
			"posting_date": nowdate(),
			"bill_no": bill_no,
			"bill_date": nowdate(),
			"items": [{"item_code": item, "qty": 1, "rate": amount}],
		}
	).insert()
	pi.submit()
	return pi


def period():
	fy = get_fiscal_year(nowdate(), company=f.TEST_COMPANY)
	doc = frappe.get_doc(
		{
			"doctype": "ICV Period Data",
			"financial_year": fy[0],
			"company": f.TEST_COMPANY,
			"from_date": fy[1],
			"to_date": fy[2],
		}
	)
	return doc.insert()


class TestICV(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.db.rollback()

	def test_icv01_weights_total_100(self):
		doc = frappe.get_single("ICV Settings")
		self.assertEqual(sum(flt(r.weight_pct) for r in doc.components), 100)
		doc.components[0].weight_pct = 40
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_icv02_expiry_14_months_and_one_active(self):
		old = certificate("ICV-OLD", add_months(nowdate(), -6))
		self.assertEqual(str(old.expiry_date), str(add_months(old.issue_date, 14)))
		new = certificate("ICV-NEW", nowdate(), score=41)
		self.assertEqual(frappe.db.get_value("ICV Certificate", old.name, "status"), "Superseded")
		self.assertEqual(icv.active_certificate().name, new.name)
		self.assertEqual(icv.current_score(), 41)

	def test_icv11_certificate_expiry_alert_at_90_and_30_days(self):
		certificate("ICV-EXP", add_days(add_months(nowdate(), -14), 80))
		self.assertEqual(icv.certificate_expiry(), 1)
		self.assertEqual(icv.certificate_expiry(), 0)
		self.assertEqual(frappe.db.get_value("ICV Certificate", "ICV-EXP", "expiry_alerts_sent"), "90")

	def test_icv10_supplier_spend_split_uae_and_weighted(self):
		doc = period()
		before = icv.collect(doc)
		service_invoice(supplier("_PVFSS ICV UAE Supplier", 1, 50), 1000, "ICV-A1")
		service_invoice(supplier("_PVFSS ICV Foreign Supplier", 0), 3000, "ICV-B1")
		staff = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_PVFSS Emirati",
				"gender": frappe.db.get_value("Gender", {}, "name")
				or frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert().name,
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": f.TEST_COMPANY,
				"pvfss_nationality_uae": 1,
			}
		).insert()
		self.assertTrue(staff.name)
		period_module.refresh(doc.name)
		doc.reload()
		self.assertEqual(flt(doc.procurement_spend_auto - before["procurement_spend"]), 4000)
		self.assertEqual(flt(doc.uae_spend_auto - before["uae_spend"]), 1000)
		self.assertEqual(flt(doc.icv_weighted_spend_auto - before["icv_weighted_spend"]), 500)
		self.assertEqual(doc.uae_nationals_auto - before["uae_nationals"], 1)

		doc.procurement_spend_override = 2000
		doc.procurement_spend_note = "Audited figure"
		doc.save()
		self.assertEqual(flt(doc.procurement_spend), 2000)
		local = next(r for r in doc.component_scores if r.component == "Local procurement")
		self.assertEqual(flt(local.score_pct), flt(min(doc.icv_weighted_spend * 100 / 2000, 100), 2))
		self.assertEqual(
			flt(doc.estimated_icv_pct), flt(sum(flt(r.contribution_pct) for r in doc.component_scores), 2)
		)
		rows = period_module.drill_down(doc.name, "uae_spend")["rows"]
		self.assertIn("_PVFSS ICV UAE Supplier", [r["supplier"] for r in rows])

		period_module.mark_final(doc.name)
		self.assertRaises(frappe.ValidationError, period_module.refresh, doc.name)

	def test_icv20_evaluated_price_and_competitor_comparison(self):
		r = icv.compare(100000, 40, 20, 95000, 10)
		self.assertEqual(r["pvfss_evaluated"], 92000)
		self.assertEqual(r["competitor_evaluated"], 93100)
		self.assertEqual(r["difference"], -1100)
		self.assertEqual(r["matching_bid"], flt(93100 / 0.92, 2))
