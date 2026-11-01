"""Module 2 tests (SUP-01 to SUP-07). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from pvfss.gates.base import GateFailedError, GateResult
from pvfss.overrides.supplier import document_status
from pvfss.pvfss_crm import supplier_rules
from pvfss.pvfss_crm.doctype.supplier_evaluation.supplier_evaluation import band_for
from pvfss.pvfss_crm.supplier_alerts import document_expiry
from pvfss.tests import factories as f


def make_avl(client_project, supplier, category="Pipes", **kw):
	return frappe.get_doc(
		{
			"doctype": "Approved Vendor Entry",
			"client_project": client_project,
			"product_category": category,
			"supplier": supplier,
			"avl_reference": kw.pop("avl_reference", "AVL-REV-0"),
			**kw,
		}
	).insert()


def set_status(supplier, status, remark="Test remark"):
	doc = frappe.get_doc("Supplier", supplier)
	doc.pvfss_approval_status = status
	doc.pvfss_approval_remarks = remark
	doc.save()
	return doc


def make_po(supplier, submit=False):
	item = f.make_item("_PVFSS Sup Pipe")
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": supplier,
			"company": f.TEST_COMPANY,
			"transaction_date": nowdate(),
			"schedule_date": add_days(nowdate(), 10),
			"items": [
				{
					"item_code": item.name,
					"qty": 1,
					"rate": 100,
					"schedule_date": add_days(nowdate(), 10),
					"warehouse": f.warehouse(),
				}
			],
		}
	)
	po.insert()
	if submit:
		po.submit()
	return po


class TestSupplier(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_sup01_supplier_defaults(self):
		s = f.make_supplier("_PVFSS Sup Defaults")
		self.assertEqual(s.pvfss_approval_status, "Prospect")
		self.assertEqual(s.pvfss_supplier_type, "Stockist")
		self.assertEqual(s.country, "United Arab Emirates")
		approved = set_status(s.name, "Approved")
		self.assertEqual(str(approved.pvfss_approval_date), nowdate())
		self.assertEqual(approved.pvfss_approved_by, "Administrator")

	def test_sup01_blacklist_needs_remark(self):
		s = f.make_supplier("_PVFSS Sup Remark")
		with self.assertRaises(frappe.ValidationError):
			set_status(s.name, "Blacklisted", remark="")
		set_status(s.name, "Blacklisted", remark="Fake MTCs")

	def test_sup01_only_managers_suspend(self):
		s = f.make_supplier("_PVFSS Sup Roles")
		user = "pvfss.sup.user@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "Sup", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		u = frappe.get_doc("User", user)
		u.add_roles("Pre-Bidding User")
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			set_status(s.name, "Suspended")
		frappe.set_user("Administrator")
		u.add_roles("Pre-Bidding Manager")
		frappe.set_user(user)
		set_status(s.name, "Suspended")

	def test_sup02_product_categories(self):
		s = f.make_supplier("_PVFSS Sup Categories")
		s.append("pvfss_product_categories", {"product_category": "Pipes", "material_types": "CS, SS"})
		s.save()
		self.assertEqual(s.pvfss_product_categories[0].approved, 1)

	def test_sup03_avl_parent_group_and_validity(self):
		cp = f.make_client_project("_PVFSS-CP-AVL", avl_required=1).name
		s = f.make_supplier("_PVFSS Sup AVL").name
		other = f.make_supplier("_PVFSS Sup Not AVL").name
		make_avl(cp, s, "Pipes", valid_to=add_days(nowdate(), 30))
		self.assertTrue(supplier_rules.is_on_avl(cp, s, "Pipes - CS"))
		self.assertFalse(supplier_rules.is_on_avl(cp, other, "Pipes - CS"))
		self.assertFalse(supplier_rules.is_on_avl(cp, s, "Pipes - CS", on_date=add_days(nowdate(), 31)))
		self.assertEqual(supplier_rules.avl_gaps(cp, other, ["Pipes - CS"]), ["Pipes - CS"])
		self.assertEqual(supplier_rules.avl_gaps(cp, s, ["Pipes - CS"]), [])

	def test_sup03_avl_not_required_has_no_gaps(self):
		cp = f.make_client_project("_PVFSS-CP-NOAVL").name
		s = f.make_supplier("_PVFSS Sup NoAVL").name
		self.assertEqual(supplier_rules.avl_gaps(cp, s, ["Pipes - CS"]), [])

	def test_sup03_avl_entry_validation(self):
		cp = f.make_client_project("_PVFSS-CP-AVLV").name
		s = f.make_supplier("_PVFSS Sup AVLV").name
		with self.assertRaises(frappe.ValidationError):
			make_avl(cp, None)
		with self.assertRaises(frappe.ValidationError):
			make_avl(cp, s, valid_from=nowdate(), valid_to=add_days(nowdate(), -1))
		make_avl(cp, s)
		with self.assertRaises(frappe.ValidationError):
			make_avl(cp, s)
		make_avl(cp, None, manufacturer_name="Tenaris Dalmine")
		with self.assertRaises(frappe.ValidationError):
			make_avl(cp, None, manufacturer_name="Tenaris Dalmine")

	def test_sup04_document_status(self):
		self.assertEqual(document_status(None, 30), "Valid")
		self.assertEqual(document_status(add_days(nowdate(), -1), 30), "Expired")
		self.assertEqual(document_status(add_days(nowdate(), 10), 30), "Expiring")
		self.assertEqual(document_status(add_days(nowdate(), 60), 30), "Valid")
		s = f.make_supplier("_PVFSS Sup Docs")
		s.append("pvfss_documents", {"document_type": "ISO 9001", "expiry_date": add_days(nowdate(), -5)})
		s.save()
		self.assertEqual(s.pvfss_documents[0].status, "Expired")

	def test_sup04_document_expiry_alert(self):
		s = f.make_supplier("_PVFSS Sup Expiry")
		s.append(
			"pvfss_documents", {"document_type": "Trade licence", "expiry_date": add_days(nowdate(), 30)}
		)
		s.save()
		self.assertGreaterEqual(document_expiry(), 1)
		self.assertEqual(document_expiry(add_days(nowdate(), 1)), 0)

	def test_sup05_band_for(self):
		self.assertEqual(band_for(4.2), "Good")
		self.assertEqual(band_for(3.0), "Satisfactory")
		self.assertEqual(band_for(2.5), "Weak")
		self.assertEqual(band_for(1.9), "Poor")

	def test_sup05_evaluation_weighted_total(self):
		s = f.make_supplier("_PVFSS Sup Eval").name
		ev = frappe.get_doc(
			{
				"doctype": "Supplier Evaluation",
				"supplier": s,
				"evaluation_basis": "Period",
				"period_from": add_days(nowdate(), -90),
				"period_to": nowdate(),
			}
		)
		ev.insert()
		self.assertTrue(ev.scores, "criteria load from PVFSS Settings")
		self.assertEqual(sum(r.weight_pct for r in ev.scores), 100)
		with self.assertRaises(frappe.ValidationError):
			ev.submit()
		ev.reload()
		for row in ev.scores:
			row.score = 4
		ev.scores[0].score = 2
		ev.save()
		w0 = ev.scores[0].weight_pct
		self.assertAlmostEqual(ev.weighted_total, round((2 * w0 + 4 * (100 - w0)) / 100, 2))
		ev.submit()
		self.assertIn(ev.band, ("Good", "Satisfactory"))

	def test_sup05_score_range(self):
		s = f.make_supplier("_PVFSS Sup Range").name
		ev = frappe.get_doc(
			{
				"doctype": "Supplier Evaluation",
				"supplier": s,
				"evaluation_basis": "Period",
				"period_from": nowdate(),
				"period_to": nowdate(),
			}
		)
		ev.insert()
		ev.scores[0].score = 6
		with self.assertRaises(frappe.ValidationError):
			ev.save()

	def test_sup05_reference_data_counts_pos(self):
		s = f.make_supplier("_PVFSS Sup Ref").name
		make_po(s, submit=True)
		ev = frappe.get_doc(
			{
				"doctype": "Supplier Evaluation",
				"supplier": s,
				"evaluation_basis": "Period",
				"period_from": add_days(nowdate(), -1),
				"period_to": nowdate(),
			}
		).insert()
		self.assertEqual(ev.po_count, 1)
		self.assertEqual(ev.on_time_pct, 0)

	def test_sup07_check_status(self):
		s = f.make_supplier("_PVFSS Sup Check").name
		result = GateResult("t")
		self.assertIsNone(supplier_rules.check_status(result, s))
		self.assertFalse(result.failures)
		set_status(s, "Conditionally approved", remark="Only CS pipe")
		self.assertIn("Only CS pipe", supplier_rules.check_status(result, s))
		set_status(s, "Suspended")
		supplier_rules.check_status(result, s)
		self.assertEqual(len(result.failures), 1)

	def test_sup07_blocked_supplier_po(self):
		s = f.make_supplier("_PVFSS Sup Blocked PO").name
		make_po(s)
		set_status(s, "Blacklisted", remark="Fraud")
		with self.assertRaises(GateFailedError):
			make_po(s)

	def test_sup07_blocked_supplier_rfq(self):
		s = f.make_supplier("_PVFSS Sup Blocked RFQ").name
		set_status(s, "Suspended")
		rfq = frappe.get_doc(
			{
				"doctype": "Request for Quotation",
				"company": f.TEST_COMPANY,
				"transaction_date": nowdate(),
				"message_for_supplier": "Please quote",
				"suppliers": [{"supplier": s}],
				"items": [
					{
						"item_code": f.make_item("_PVFSS Sup Pipe").name,
						"qty": 1,
						"uom": "Meter",
						"conversion_factor": 1,
						"schedule_date": add_days(nowdate(), 7),
						"warehouse": f.warehouse(),
					}
				],
			}
		)
		with self.assertRaises(GateFailedError):
			rfq.insert()
