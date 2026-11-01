"""Module 1 tests (CRM-01 to CRM-12). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from pvfss.pvfss_crm import inquiry as inq
from pvfss.pvfss_crm import inquiry_import
from pvfss.pvfss_crm.alerts import inquiry_due_date
from pvfss.pvfss_crm.report.inquiry_register.inquiry_register import execute as inquiry_register
from pvfss.tests import factories as f


def make_inquiry(ref="CR-001", lines=1, customer=None, **kw):
	customer = customer or f.make_customer().name
	doc = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"opportunity_from": "Customer",
			"party_name": customer,
			"company": f.TEST_COMPANY,
			"pvfss_contractor_ref": ref,
			"pvfss_received_on": now_datetime(),
			"pvfss_bid_due_date": add_to_date(now_datetime(), days=10),
			"items": [
				{
					"item_code": f.make_item(
						"_PVFSS CRM Service", is_stock_item=0, item_group="Testing"
					).name,
					"qty": 1,
					"pvfss_customer_line_ref": str(i + 1),
					"pvfss_specification": f"Spec line {i + 1}",
				}
				for i in range(lines)
			],
			**kw,
		}
	)
	return doc.insert()


def make_quotation(inquiry, submit=True):
	from erpnext.crm.doctype.opportunity.opportunity import make_quotation as _make

	f.price_list()
	qtn = _make(inquiry.name)
	qtn.selling_price_list = f.price_list()
	for row in qtn.items:
		row.rate = 100
	qtn.insert()
	if submit:
		qtn.submit()
	return qtn


class TestInquiry(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.db.rollback()

	def test_CRM_01_inquiry_is_from_customer_and_labelled(self):
		doc = make_inquiry("CR-01")
		self.assertEqual(doc.opportunity_from, "Customer")
		self.assertTrue(doc.name.startswith("INQ-"))
		self.assertEqual(
			frappe.db.get_value("Translation", {"source_text": "Opportunity"}, "translated_text"), "Inquiry"
		)

	def test_CRM_02_due_date_after_received(self):
		with self.assertRaises(frappe.ValidationError):
			make_inquiry("CR-02", pvfss_bid_due_date=add_to_date(now_datetime(), days=-1))

	def test_CRM_03_specification_required_per_line(self):
		doc = make_inquiry("CR-03")
		doc.items[0].pvfss_specification = ""
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_CRM_03_line_ref_unique(self):
		doc = make_inquiry("CR-03B", lines=2)
		doc.items[1].pvfss_customer_line_ref = doc.items[0].pvfss_customer_line_ref
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_CRM_05_duplicate_warns_on_save_and_blocks_progress(self):
		first = make_inquiry("CR-DUP")
		second = make_inquiry("CR-DUP")  # saves, with a warning
		self.assertEqual(second.pvfss_duplicate_of, first.name)

		self.assertRaises(frappe.ValidationError, inq.advance, second.name, inq.RFQ_SENT)

		second.reload()
		second.pvfss_not_duplicate = 1
		second.save()
		self.assertTrue(inq.advance(second.name, inq.RFQ_SENT))

	def test_CRM_05_closed_inquiry_is_not_a_duplicate(self):
		first = make_inquiry("CR-DUP2")
		inq.mark_closed(first.name, inq.CANCELLED, ["Cancelled by client"], "Client cancelled")
		second = make_inquiry("CR-DUP2")
		self.assertFalse(second.pvfss_duplicate_of)

	def test_CRM_06_stage_cannot_be_edited_by_hand(self):
		doc = make_inquiry("CR-06")
		self.assertEqual(doc.pvfss_stage, inq.NEW)
		doc.pvfss_stage = inq.QUOTED
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_CRM_06_stage_only_moves_forward(self):
		doc = make_inquiry("CR-06B")
		self.assertTrue(inq.advance(doc.name, inq.QUOTES_RECEIVED))
		self.assertFalse(inq.advance(doc.name, inq.RFQ_SENT))
		self.assertEqual(frappe.db.get_value("Opportunity", doc.name, "pvfss_stage"), inq.QUOTES_RECEIVED)

	def test_CRM_07_quotation_and_sales_order_move_stage_to_won(self):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		doc = make_inquiry("CR-07")
		qtn = make_quotation(doc)
		doc.reload()
		self.assertEqual(doc.pvfss_stage, inq.QUOTED)
		self.assertEqual(doc.pvfss_quoted_value, qtn.base_net_total)
		self.assertIsNotNone(doc.pvfss_turnaround_days)

		so = make_sales_order(qtn.name)
		so.delivery_date = f.delivery_date()
		so.insert()
		so.submit()
		self.assertEqual(frappe.db.get_value("Opportunity", doc.name, "pvfss_stage"), inq.WON)

	def test_CRM_07_lost_quotation_marks_inquiry_lost(self):
		doc = make_inquiry("CR-07L")
		qtn = make_quotation(doc)
		qtn.reload()
		qtn.declare_enquiry_lost([{"lost_reason": "Price"}], [], "Competitor 8% cheaper")
		doc.reload()
		self.assertEqual(doc.pvfss_stage, inq.LOST)
		self.assertEqual([r.lost_reason for r in doc.lost_reasons], ["Price"])

	def test_CRM_08_no_bid_requires_reason_and_detail(self):
		doc = make_inquiry("CR-08")
		self.assertRaises(frappe.ValidationError, inq.mark_closed, doc.name, inq.NO_BID, [], "")
		inq.mark_closed(doc.name, inq.NO_BID, ["No bid by PVFSS"], "Outside scope", "Rival LLC", 1000)
		doc.reload()
		self.assertEqual(doc.pvfss_stage, inq.NO_BID)
		self.assertEqual(doc.pvfss_competitor_name, "Rival LLC")

	def test_CRM_08_only_no_bid_or_cancel_by_hand(self):
		doc = make_inquiry("CR-08B")
		self.assertRaises(frappe.ValidationError, inq.mark_closed, doc.name, inq.WON, ["Price"], "x")

	def test_CRM_09_owner_assigned(self):
		doc = make_inquiry("CR-09")
		self.assertEqual(doc.pvfss_owner, frappe.session.user)
		self.assertTrue(
			frappe.db.exists(
				"ToDo",
				{
					"reference_type": "Opportunity",
					"reference_name": doc.name,
					"allocated_to": doc.pvfss_owner,
				},
			)
		)

	def test_CRM_11_inquiry_register_lists_inquiry(self):
		doc = make_inquiry("CR-11", lines=3)
		_columns, data = inquiry_register({"party_name": doc.party_name})
		row = next(r for r in data if r.name == doc.name)
		self.assertEqual(row.pvfss_line_count, 3)
		self.assertEqual(row.pvfss_contractor_ref, "CR-11")

	def test_CRM_12_due_date_alert(self):
		days = inq.due_alert_days()
		doc = make_inquiry("CR-12", pvfss_bid_due_date=f"{add_days(nowdate(), days)} 12:00:00")
		before = frappe.db.count("Notification Log", {"document_name": doc.name})
		self.assertGreaterEqual(inquiry_due_date(), 1)
		# enqueue_create_notification runs inline in tests
		self.assertGreater(frappe.db.count("Notification Log", {"document_name": doc.name}), before)

	def test_CRM_12_no_alert_once_quoted(self):
		days = inq.due_alert_days()
		doc = make_inquiry("CR-12Q", pvfss_bid_due_date=f"{add_days(nowdate(), days)} 12:00:00")
		make_quotation(doc)
		before = frappe.db.count("Notification Log", {"document_name": doc.name})
		inquiry_due_date()
		self.assertEqual(frappe.db.count("Notification Log", {"document_name": doc.name}), before)


class TestInquiryImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.db.rollback()

	def _file(self, rows):
		import csv
		import io

		buf = io.StringIO()
		writer = csv.writer(buf)
		writer.writerow([c[1] for c in inquiry_import.COLUMNS])
		writer.writerows(rows)
		return frappe.get_doc(
			{"doctype": "File", "file_name": "lines.csv", "content": buf.getvalue(), "is_private": 1}
		).insert()

	def test_CRM_04_import_preview_and_commit(self):
		doc = make_inquiry("CR-04", lines=1)
		rows = [
			[str(i), "", "Pipe", f"ASTM A106 Gr.B line {i}", 10, "mtr", "CS", "Pipes - CS", "", "MTC 3.1"]
			for i in range(2, 52)
		]
		rows.append(["53", "", "Bad", "", "", "lightyears", "XX", "", "", ""])
		rows.append(["2", "", "Dup", "dup spec", 1, "Nos", "", "", "", ""])
		file_doc = self._file(rows)

		preview = inquiry_import.preview(doc.name, file_doc.file_url)
		self.assertEqual(preview["ok"], 50)
		self.assertEqual(preview["errors"], 2)
		self.assertEqual(len(doc.reload().items), 1)  # nothing written by preview

		self.assertEqual(inquiry_import.import_lines(doc.name, file_doc.file_url), 50)
		doc.reload()
		self.assertEqual(len(doc.items), 51)
		row = next(r for r in doc.items if r.pvfss_customer_line_ref == "10")
		self.assertEqual(row.pvfss_specification, "ASTM A106 Gr.B line 10")
		self.assertEqual(row.uom, "Meter")
		self.assertEqual(row.item_code, frappe.db.get_single_value("PVFSS Settings", "generic_inquiry_item"))
		self.assertEqual(doc.pvfss_line_count, 51)


class TestCRMPermissions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _user(self, email, role):
		if not frappe.db.exists("User", email):
			user = frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": role, "send_welcome_email": 0}
			)
			user.insert(ignore_permissions=True)
			user.add_roles(role)
		return email

	def test_GEN_21_pre_bidding_user_creates_inquiry(self):
		self.assertTrue(
			frappe.has_permission(
				"Opportunity", "create", user=self._user("pbu@pvfss.test", "Pre-Bidding User")
			)
		)

	def test_GEN_21_quality_user_reads_but_cannot_create_inquiry(self):
		user = self._user("qu@pvfss.test", "Quality User")
		self.assertTrue(frappe.has_permission("Opportunity", "read", user=user))
		self.assertFalse(frappe.has_permission("Opportunity", "create", user=user))

	def test_GEN_21_finance_user_cannot_read_inquiry(self):
		self.assertFalse(
			frappe.has_permission("Opportunity", "read", user=self._user("fu@pvfss.test", "Finance User"))
		)
