"""Module 5 tests (PUR-01 to PUR-12, G3, SUP-03 on PO). Names carry the requirement ID (GEN-07)."""

import frappe
from erpnext.selling.doctype.quotation.quotation import make_sales_order
from frappe.model.workflow import WorkflowPermissionError, WorkflowTransitionError
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt

from pvfss.gates import g3
from pvfss.gates.base import GateFailedError
from pvfss.pvfss_crm import quotation as qtn_module
from pvfss.pvfss_crm import selection
from pvfss.pvfss_crm.doctype.costing_sheet.costing_sheet import make_or_refresh
from pvfss.pvfss_crm.test_crm import make_inquiry
from pvfss.pvfss_crm.test_quotation import make_user
from pvfss.pvfss_crm.test_rfq import make_rfq, make_sq, ref_counter
from pvfss.pvfss_purchasing import supplier_po
from pvfss.tests import factories as f
from pvfss.utils import settings

WF_ERRORS = (WorkflowPermissionError, WorkflowTransitionError)


def won_customer_po(quotes, lines=2, margin=20, delivery_days=60):
	"""Inquiry -> RFQ -> quotes -> selection -> costing -> TE -> quotation -> submitted Customer PO.

	``quotes``: {supplier_name: [rate per line or None]}
	"""
	f.price_list()
	inquiry = make_inquiry(ref=ref_counter(), lines=lines)
	suppliers = [f.make_supplier(name).name for name in quotes]
	rfq = make_rfq(inquiry.name, suppliers)
	for supplier, rates in zip(suppliers, quotes.values(), strict=True):
		make_sq(rfq, supplier, rates, lead=10)
	selection.select_lowest(inquiry.name, preview=0)
	cs = frappe.get_doc("Costing Sheet", make_or_refresh(inquiry.name))
	cs.target_margin_pct = margin
	cs.save()
	cs.submit()
	te = frappe.get_doc({"doctype": "Technical Evaluation", "inquiry": inquiry.name}).insert()
	for row in te.items:
		row.compliance = "Compliant"
	te.save()
	te.submit()
	qtn = qtn_module.make_quotation(cs.name)
	qtn.insert()
	qtn = f.submit_quotation(qtn)
	so = make_sales_order(qtn.name)
	so.delivery_date = f.delivery_date(delivery_days)
	for row in so.items:
		row.delivery_date = so.delivery_date
	f.customer_po(so).insert()
	return f.submit_sales_order(so)


def results(po):
	return {(r.line_ref, r.check): r.result for r in po.pvfss_compliance}


class TestPurchasing(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	def one_po(self, **kw):
		self.so = won_customer_po({"_PVFSS PUR Supplier A": [100, 50]}, **kw)
		names = supplier_po.make_supplier_pos(self.so.name)
		self.assertEqual(len(names), 1)
		return frappe.get_doc("Purchase Order", names[0])

	# ------------------------------------------------------------------ PUR-01 / PUR-03
	def test_pur01_supplier_po_from_customer_po(self):
		po = self.one_po()
		self.assertEqual(po.supplier, "_PVFSS PUR Supplier A")
		self.assertEqual(po.pvfss_sales_order, self.so.name)
		self.assertEqual(po.pvfss_customer_po_no, self.so.po_no)
		self.assertEqual([flt(r.rate) for r in po.items], [100, 50])
		self.assertTrue(all(r.sales_order_item and r.supplier_quotation_item for r in po.items))
		self.assertEqual(po.items[0].pvfss_customer_line_ref, "1")
		self.assertEqual(po.pvfss_deviation_count, 0, results(po))
		self.assertEqual(po.pvfss_compliance_status, "All checks match")
		self.assertEqual(po.pvfss_approval_route, "Value Approval")
		self.assertGreater(po.pvfss_margin_pct, 0)

	def test_pur01_one_po_per_supplier(self):
		so = won_customer_po({"_PVFSS PUR Supplier A": [100, 80], "_PVFSS PUR Supplier B": [120, 50]})
		plan = supplier_po.get_plan(so.name)
		self.assertEqual(
			{r["line_ref"]: r["supplier"] for r in plan},
			{"1": "_PVFSS PUR Supplier A", "2": "_PVFSS PUR Supplier B"},
		)
		names = supplier_po.make_supplier_pos(so.name)
		self.assertEqual(len(names), 2)
		self.assertEqual(
			sorted(frappe.db.get_value("Purchase Order", n, "supplier") for n in names),
			["_PVFSS PUR Supplier A", "_PVFSS PUR Supplier B"],
		)

	def test_pur01_matching_po_needs_only_value_approval(self):
		po = self.one_po()
		po = f.walk_workflow(po, "Send for Approval")
		self.assertEqual(po.workflow_state, "Value Approval")
		po = f.walk_workflow(po, "Approve", "Submit")
		self.assertEqual(po.docstatus, 1)

	# ------------------------------------------------------------------ PUR-02
	def test_pur02_so_link_cannot_change(self):
		po = self.one_po()
		po.items[0].sales_order_item = po.items[1].sales_order_item
		with self.assertRaises(frappe.ValidationError):
			po.save()

	# ------------------------------------------------------------------ PUR-04 / PUR-05
	def test_pur04_later_date_and_lower_qty_create_deviations(self):
		po = self.one_po()
		po.items[0].qty = flt(po.items[0].qty) / 2
		po.items[1].schedule_date = add_days(self.so.delivery_date, 5)
		po.save()
		res = results(po)
		self.assertEqual(res[("1", "Quantity")], "Deviation")
		self.assertEqual(res[("2", "Delivery date")], "Deviation")
		self.assertEqual(po.pvfss_deviation_count, 2)
		po = f.walk_workflow(po, "Send for Approval")
		self.assertEqual(po.workflow_state, "Deviation Approval")
		po = f.walk_workflow(po, "Approve Deviations", "Approve")
		with self.assertRaises(GateFailedError) as ctx:
			f.walk_workflow(po, "Submit")
		self.assertIn("needs a justification", str(ctx.exception))

	def test_pur04_justification_survives_rerun(self):
		po = self.one_po()
		po.items[0].qty = flt(po.items[0].qty) / 2
		po.save()
		for row in po.pvfss_compliance:
			if row.result == "Deviation":
				row.justification = "Balance from stock"
		po.save()
		po.reload()
		self.assertEqual(
			[r.justification for r in po.pvfss_compliance if r.result == "Deviation"], ["Balance from stock"]
		)

	def test_pur04_payment_terms_timing_is_a_flag(self):
		po = self.one_po()
		frappe.db.set_value("Sales Order", self.so.name, "payment_terms_template", "TT 60 days")
		po.payment_terms_template = "TT 30 days"
		po.set("payment_schedule", [])
		po.save()
		self.assertEqual(results(po)[("", "Payment terms")], "Flag")
		self.assertEqual(po.pvfss_deviation_count, 0)

	# ------------------------------------------------------------------ PUR-06 / PUR-10
	def test_pur06_negative_margin_routes_to_director(self):
		po = self.one_po(margin=-50)  # sold below cost
		self.assertEqual(po.pvfss_negative_margin_lines, "1, 2")
		self.assertEqual(po.pvfss_approval_route, "Director Approval")
		po = f.walk_workflow(po, "Send for Approval")
		self.assertEqual(po.workflow_state, "Director Approval")
		frappe.set_user(make_user("pvfss.pom2@example.com", "Post-Bidding Manager"))
		with self.assertRaises(WF_ERRORS):
			f.walk_workflow(po, "Approve")

	def test_pur10_threshold_from_settings(self):
		frappe.db.set_single_value("PVFSS Settings", "spo_value_approval_threshold", 1)
		settings.clear_cache()
		po = self.one_po()
		self.assertEqual(po.pvfss_approval_route, "Director Approval")

	def test_pur10_unapproved_po_cannot_be_submitted(self):
		po = self.one_po()
		with self.assertRaises(GateFailedError):
			po.submit()

	# ------------------------------------------------------------------ PUR-07
	def test_pur07_second_po_overorder_blocked(self):
		po = self.one_po()
		f.submit_purchase_order(po)
		second = supplier_po.build_po(
			self.so,
			"_PVFSS PUR Supplier A",
			[frappe._dict(so_item=self.so.items[0].name, qty_to_order=1, sq_item=None)],
			{r.name: r for r in self.so.items},
		)
		second.items[0].rate = 10
		second.insert()
		self.assertEqual(second.pvfss_over_order_lines, 1)
		self.assertEqual(results(second)[("1", "Over-ordering")], "Deviation")
		with self.assertRaises(GateFailedError):
			second.submit()
		second = f.walk_workflow(second, "Send for Approval")
		self.assertEqual(second.workflow_state, "Deviation Approval")

	def test_pur07_plan_shows_remaining(self):
		po = self.one_po()
		f.submit_purchase_order(po)
		plan = supplier_po.get_plan(self.so.name)
		self.assertTrue(all(flt(r["qty_to_order"]) == 0 for r in plan))
		with self.assertRaises(frappe.ValidationError):
			supplier_po.make_supplier_pos(self.so.name)

	# ------------------------------------------------------------------ SUP-03 / SUP-07 on PO
	def test_sup03_blocks_po_for_non_avl_supplier(self):
		po = self.one_po()
		cp = f.make_client_project("_PVFSS-CP-PURAVL", avl_required=1).name
		po.db_set("pvfss_client_project", cp)
		po.reload()
		result = g3.check(po, require_approval=False)
		self.assertTrue(any(r.rule == "SUP-03" for r in result.failures))
		po.pvfss_avl_customer_approval_ref = "Contractor letter CL-123"
		po.save()
		self.assertFalse(any(r.rule == "SUP-03" for r in g3.check(po, require_approval=False).failures))

	def test_sup03_only_pom_records_avl_approval(self):
		po = self.one_po()
		frappe.set_user(make_user("pvfss.pou2@example.com", "Post-Bidding User"))
		po.reload()
		po.pvfss_avl_customer_approval_ref = "X"
		with self.assertRaises(frappe.PermissionError):
			po.save()

	# ------------------------------------------------------------------ PUR-09 / PUR-12 / PUR-08
	def test_pur09_amendment_needs_reason_and_rechecks(self):
		po = f.submit_purchase_order(self.one_po())
		po = f.walk_workflow(po, "Cancel")
		amended = frappe.copy_doc(po)
		amended.amended_from = po.name
		amended.docstatus = 0
		amended.workflow_state = "Draft"
		with self.assertRaises(frappe.MandatoryError):
			amended.insert()
		amended.pvfss_amendment_reason = "Supplier changed mill"
		amended.insert()
		self.assertEqual(amended.name, f"{po.name}-1")
		self.assertEqual(amended.pvfss_deviation_count, 0)

	def test_pur12_three_way_match_settings(self):
		self.assertEqual(frappe.db.get_single_value("Buying Settings", "po_required"), "Yes")
		self.assertEqual(frappe.db.get_single_value("Buying Settings", "pr_required"), "Yes")
		self.assertEqual(flt(frappe.db.get_single_value("Accounts Settings", "over_billing_allowance")), 0)

	def test_pur08_supplier_po_print_format(self):
		po = self.one_po()
		html = frappe.get_print("Purchase Order", po.name, print_format="PVFSS Supplier PO", doc=po)
		self.assertIn("Spec line 1", html)
		self.assertIn("Supplier acceptance", html)
