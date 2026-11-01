"""Module 4 tests (SQ-01 to SQ-10, RFQ-12, ICV-20). Names carry the requirement ID (GEN-07)."""

import frappe
from erpnext.selling.doctype.quotation.quotation import make_sales_order
from frappe.model.workflow import WorkflowPermissionError, WorkflowTransitionError
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from pvfss.gates.base import GateFailedError
from pvfss.pvfss_crm import inquiry as inq
from pvfss.pvfss_crm import quotation as qtn_module
from pvfss.pvfss_crm import selection
from pvfss.pvfss_crm.doctype.costing_sheet.costing_sheet import make_or_refresh
from pvfss.pvfss_crm.test_crm import make_inquiry
from pvfss.pvfss_crm.test_rfq import make_rfq, make_sq, ref_counter
from pvfss.tests import factories as f
from pvfss.utils import settings


def make_user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.add_roles(*roles)
	return email


class TestQuotation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()
		f.price_list()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	def costed(self, margin=20, evaluate=True, deviation=False):
		"""Inquiry with 2 lines, one supplier quote, selection, costing sheet (submitted) and TE."""
		f.price_list()
		supplier = f.make_supplier("_PVFSS QTN Supplier").name
		self.inquiry = make_inquiry(ref=ref_counter(), lines=2)
		rfq = make_rfq(self.inquiry.name, [supplier])
		sq = make_sq(rfq, supplier, [100, 50], lead=25)
		selection.select_lowest(self.inquiry.name, preview=0)
		cs = frappe.get_doc("Costing Sheet", make_or_refresh(self.inquiry.name))
		cs.target_margin_pct = margin
		cs.save()
		cs.submit()
		if evaluate:
			te = frappe.get_doc({"doctype": "Technical Evaluation", "inquiry": self.inquiry.name}).insert()
			for row in te.items:
				row.compliance = "Compliant"
			if deviation:
				te.items[1].compliance = "Compliant with deviation"
				te.items[1].deviation_description = "Bevel 30 deg instead of 37.5"
			te.save()
			te.submit()
		self.sq = sq
		return cs

	def quotation(self, margin=20, **kw):
		cs = self.costed(margin=margin, **kw)
		qtn = qtn_module.make_quotation(cs.name)
		qtn.insert()
		return cs, qtn

	# ------------------------------------------------------------------ SQ-01 / SQ-02
	def test_sq01_quotation_from_costing_sheet(self):
		frappe.db.set_single_value("PVFSS Settings", "quotation_lead_time_buffer_days", 5)
		settings.clear_cache()
		cs, qtn = self.quotation(deviation=True)
		self.assertEqual(qtn.opportunity, self.inquiry.name)
		self.assertEqual(qtn.pvfss_costing_sheet, cs.name)
		self.assertEqual([r.pvfss_customer_line_ref for r in qtn.items], ["1", "2"])
		self.assertAlmostEqual(flt(qtn.items[0].rate), flt(cs.items[0].selling_price), places=2)
		self.assertEqual(qtn.items[0].pvfss_lead_time_days, 30)
		self.assertIn("30 days", qtn.pvfss_delivery_terms)
		self.assertIn("Line 2: Bevel 30 deg", qtn.pvfss_technical_deviations)
		self.assertAlmostEqual(qtn.pvfss_margin_pct, 20, places=1)
		self.assertEqual(frappe.db.get_value("Costing Sheet", cs.name, "quotation"), qtn.name)

	def test_rfq12_make_quotation_needs_technical_evaluation(self):
		cs = self.costed(evaluate=False)
		with self.assertRaises(GateFailedError) as ctx:
			qtn_module.make_quotation(cs.name)
		self.assertIn("No submitted Technical Evaluation", str(ctx.exception))

	# ------------------------------------------------------------------ SQ-06 / G2
	def test_sq06_approver_from_margin(self):
		frappe.db.set_single_value("PVFSS Settings", "min_target_margin_pct", 10)
		settings.clear_cache()
		_cs, qtn = self.quotation(margin=20)
		self.assertEqual(qtn.pvfss_approver_role, "Pre-Bidding Manager")
		for row in qtn.items:
			row.rate = flt(row.pvfss_landed_cost) * 1.05
		qtn.save()
		self.assertLess(qtn.pvfss_margin_pct, 10)
		self.assertEqual(qtn.pvfss_approver_role, "PVFSS Director")

	def test_sq06_low_margin_routes_to_director(self):
		frappe.db.set_single_value("PVFSS Settings", "min_target_margin_pct", 10)
		settings.clear_cache()
		_cs, qtn = self.quotation(margin=5)
		pbm = make_user("pvfss.pbm@example.com", "Pre-Bidding Manager")
		director = make_user("pvfss.dir@example.com", "PVFSS Director")
		qtn = f.walk_workflow(qtn, "Send for Approval")
		frappe.set_user(pbm)
		with self.assertRaises((WorkflowPermissionError, WorkflowTransitionError)):
			f.walk_workflow(qtn, "Approve")
		frappe.set_user(director)
		qtn = f.walk_workflow(qtn, "Approve")
		self.assertEqual(qtn.workflow_state, "Approved")
		self.assertEqual(qtn.pvfss_approved_by, director)

	def test_sq06_unapproved_quotation_cannot_be_submitted(self):
		_cs, qtn = self.quotation()
		with self.assertRaises(GateFailedError):
			qtn.submit()

	def test_sq06_rate_change_after_approval_returns_to_draft(self):
		_cs, qtn = self.quotation()
		qtn = f.walk_workflow(qtn, "Send for Approval", "Approve")
		qtn.items[0].rate = flt(qtn.items[0].rate) + 10
		qtn.save()
		self.assertEqual(qtn.workflow_state, "Draft")
		qtn = f.submit_quotation(qtn)
		self.assertEqual(qtn.docstatus, 1)
		self.assertEqual(frappe.db.get_value("Opportunity", self.inquiry.name, "pvfss_stage"), inq.QUOTED)

	# ------------------------------------------------------------------ SQ-04
	def test_sq04_revision_cancels_previous(self):
		_cs, qtn = self.quotation()
		qtn = f.submit_quotation(qtn)
		rev = qtn_module.make_revision(qtn.name)
		self.assertEqual(rev, f"{qtn.name}-1")
		self.assertEqual(frappe.db.get_value("Quotation", qtn.name, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Quotation", rev, "workflow_state"), "Draft")
		self.assertEqual(frappe.db.get_value("Costing Sheet", _cs.name, "quotation"), rev)

	# ------------------------------------------------------------------ ICV-20
	def test_icv20_evaluated_price(self):
		_cs, qtn = self.quotation()
		qtn.pvfss_icv_score_used = 40
		qtn.pvfss_icv_weightage_pct = 25
		qtn.save()
		self.assertAlmostEqual(qtn.pvfss_evaluated_price, flt(qtn.grand_total * 0.9, 2), places=2)

	# ------------------------------------------------------------------ SQ-07 to SQ-10
	def customer_po(self, qty_change=None):
		_cs, qtn = self.quotation()
		qtn = f.submit_quotation(qtn)
		so = make_sales_order(qtn.name)
		so.delivery_date = f.delivery_date()
		if qty_change:
			so.items[0].qty = qty_change
		return f.customer_po(so)

	def test_sq07_customer_po_number_and_file_mandatory(self):
		so = self.customer_po()
		so.pvfss_customer_po_file = None
		with self.assertRaises(frappe.MandatoryError):
			so.insert()

	def test_sq08_review_checklist_from_template(self):
		so = self.customer_po()
		so.insert()
		self.assertEqual(len(so.pvfss_po_review), 10)
		self.assertEqual(so.pvfss_po_review[0].check_item, "Scope matches quotation")
		self.assertEqual(so.pvfss_inquiry, self.inquiry.name)
		self.assertTrue(so.pvfss_review_complete)
		self.assertEqual(so.pvfss_difference_count, 0)

	def test_sq09_qty_change_requires_review(self):
		so = self.customer_po(qty_change=7)
		so.insert()
		self.assertEqual(so.pvfss_difference_count, 1)
		diff = so.pvfss_differences[0]
		self.assertEqual(
			(diff.line_ref, diff.field, diff.review_item, diff.reviewed), ("1", "Qty", "Quantities", 0)
		)
		# Without a Deviation remark the review blocks submit
		so = f.walk_workflow(so, "Submit for Review", "Approve")
		with self.assertRaises(GateFailedError) as ctx:
			f.walk_workflow(so, "Submit")
		self.assertIn("Line 1 Qty", str(ctx.exception))
		# Record the deviation, then the POM approval is still needed
		so = f.walk_workflow(so, "Return to Draft")
		for row in so.pvfss_po_review:
			if row.check_item == "Quantities":
				row.result = "Deviation"
				row.remark = "Contractor reduced line 1 to 7 m"
		so.save()
		self.assertEqual(so.pvfss_differences[0].reviewed, 1)
		so = f.walk_workflow(so, "Submit for Review")
		with self.assertRaises((WorkflowPermissionError, WorkflowTransitionError)):
			f.walk_workflow(so, "Submit")  # needs the Approve step when differences exist
		so = f.walk_workflow(so, "Approve", "Submit")
		self.assertEqual(so.docstatus, 1)

	def test_sq09_direct_submit_without_approval_blocked(self):
		so = self.customer_po(qty_change=7)
		for row in so.pvfss_po_review:
			if row.check_item == "Quantities":
				row.result = "Deviation"
				row.remark = "Reduced"
		so.insert()
		with self.assertRaises(GateFailedError) as ctx:
			so.submit()
		self.assertIn("Post-Bidding Manager approval", str(ctx.exception))

	def test_sq10_submit_sets_won_and_notifies_pom(self):
		pom = make_user("pvfss.pom@example.com", "Post-Bidding Manager")
		so = self.customer_po()
		so.insert()
		f.submit_sales_order(so)
		self.assertEqual(frappe.db.get_value("Opportunity", self.inquiry.name, "pvfss_stage"), inq.WON)
		self.assertTrue(
			frappe.db.exists(
				"Notification Log",
				{"for_user": pom, "document_type": "Sales Order", "document_name": so.name},
			)
		)

	def test_fin10_only_finance_manager_allows_advance_billing(self):
		so = self.customer_po()
		so.insert()
		user = make_user("pvfss.pou@example.com", "Post-Bidding User")
		frappe.set_user(user)
		so.reload()
		so.pvfss_advance_billing_allowed = 1
		with self.assertRaises(frappe.PermissionError):
			so.save()

	def test_sq03_quotation_print_format(self):
		_cs, qtn = self.quotation(deviation=True)
		html = frappe.get_print("Quotation", qtn.name, print_format="PVFSS Quotation", doc=qtn)
		self.assertIn(self.inquiry.pvfss_contractor_ref, html)
		self.assertIn("Technical Deviations", html)
		self.assertIn("Authorised Signatory", html)
