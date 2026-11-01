"""Module 3 tests (RFQ-01 to RFQ-12, SUP-03 flag). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from pvfss.gates import g1
from pvfss.gates.base import GateFailedError
from pvfss.pvfss_crm import inquiry as inq
from pvfss.pvfss_crm import rfq as rfq_helpers
from pvfss.pvfss_crm import selection, sq_import
from pvfss.pvfss_crm.doctype.costing_sheet.costing_sheet import make_or_refresh
from pvfss.pvfss_crm.report.competitive_statement.competitive_statement import execute as statement
from pvfss.pvfss_crm.test_crm import make_inquiry
from pvfss.tests import factories as f

USD_RATE = 3.6725


def stage(inquiry):
	return frappe.db.get_value("Opportunity", inquiry, "pvfss_stage")


def make_rfq(inquiry, suppliers, submit=True, category="Pipes - CS"):
	rfq = rfq_helpers.make_rfq(inquiry)
	for s in suppliers:
		rfq.append("suppliers", {"supplier": s, "send_email": 0})
	for row in rfq.items:
		row.pvfss_product_category = category
	rfq.insert()
	if submit:
		rfq.submit()
	return rfq


def make_sq(rfq, supplier, rates, currency="AED", compliance="Compliant", lead=20, submit=True, **kw):
	"""``rates``: list of rates by line order (None = No quote)."""
	from erpnext.buying.doctype.request_for_quotation.request_for_quotation import (
		make_supplier_quotation_from_rfq,
	)

	sq = make_supplier_quotation_from_rfq(rfq.name, for_supplier=supplier)
	sq.valid_till = add_days(nowdate(), 30)
	if currency != "AED":
		sq.currency = currency
		sq.conversion_rate = USD_RATE
	comp = compliance if isinstance(compliance, list) else [compliance] * len(sq.items)
	for row, rate, c in zip(sq.items, rates, comp, strict=False):
		if rate is None:
			row.pvfss_no_quote = 1
			row.rate = 0
			continue
		row.rate = rate
		row.lead_time_days = lead
		row.pvfss_availability = "Ready stock"
		row.pvfss_compliance = c
		if c != "Compliant":
			row.pvfss_deviation_note = "Different end finish"
	sq.update(kw)
	sq.insert()
	if submit:
		sq.submit()
	return sq


def ref_counter():
	frappe.flags.pvfss_rfq_ref = (frappe.flags.pvfss_rfq_ref or 0) + 1
	return f"RFQ-T-{frappe.flags.pvfss_rfq_ref}-{frappe.generate_hash(length=4)}"


class TestRFQ(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def setUp(self):
		self.s1 = f.make_supplier("_PVFSS RFQ Supplier A").name
		self.s2 = f.make_supplier("_PVFSS RFQ Supplier B").name
		self.s3 = f.make_supplier("_PVFSS RFQ Supplier USD").name
		self.inquiry = make_inquiry(ref=ref_counter(), lines=2)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ------------------------------------------------------------------ RFQ-01 / CRM-07
	def test_rfq01_create_rfq_maps_lines(self):
		rfq = make_rfq(self.inquiry.name, [self.s1], submit=False)
		self.assertEqual(rfq.opportunity, self.inquiry.name)
		self.assertEqual([r.pvfss_customer_line_ref for r in rfq.items], ["1", "2"])
		self.assertEqual(rfq.items[0].pvfss_specification, "Spec line 1")
		self.assertEqual(stage(self.inquiry.name), inq.NEW)
		rfq.submit()
		self.assertEqual(stage(self.inquiry.name), inq.RFQ_SENT)

	def test_rfq01_no_rfq_for_closed_inquiry(self):
		frappe.db.set_value("Opportunity", self.inquiry.name, "pvfss_stage", inq.NO_BID)
		with self.assertRaises(frappe.ValidationError):
			rfq_helpers.make_rfq(self.inquiry.name)

	# ------------------------------------------------------------------ SUP-03 / RFQ-02
	def test_sup03_avl_flag_on_rfq(self):
		cp = f.make_client_project("_PVFSS-CP-RFQAVL", avl_required=1).name
		frappe.db.set_value("Opportunity", self.inquiry.name, "pvfss_client_project", cp)
		frappe.get_doc(
			{
				"doctype": "Approved Vendor Entry",
				"client_project": cp,
				"product_category": "Pipes",
				"supplier": self.s1,
				"avl_reference": "AVL-1",
			}
		).insert()
		rfq = make_rfq(self.inquiry.name, [self.s1, self.s2], submit=False)
		flags = {r.supplier: r.pvfss_avl_flag for r in rfq.suppliers}
		self.assertEqual(flags[self.s1], "On AVL")
		self.assertEqual(flags[self.s2], "Not on AVL")

	def test_rfq02_suggest_suppliers_by_category(self):
		for name, status in ((self.s1, "Approved"), (self.s2, "Suspended")):
			doc = frappe.get_doc("Supplier", name)
			doc.set("pvfss_product_categories", [{"product_category": "Pipes"}])
			doc.pvfss_approval_status = status
			doc.pvfss_approval_remarks = "test"
			doc.save()
		rows = {r["supplier"]: r for r in rfq_helpers.suggest_suppliers(["Pipes - CS", "Flanges"])}
		self.assertIn(self.s1, rows)
		self.assertEqual(rows[self.s1]["covered"], 1)
		self.assertEqual(rows[self.s1]["total"], 2)
		self.assertTrue(rows[self.s2]["blocked"])
		self.assertNotIn(self.s3, rows)
		approved = {r["supplier"] for r in rfq_helpers.suggest_suppliers(["Pipes - CS"], only_approved=1)}
		self.assertIn(self.s1, approved)
		self.assertNotIn(self.s2, approved)

	# ------------------------------------------------------------------ RFQ-04 / RFQ-05
	def test_rfq05_completeness_blocks_submit(self):
		rfq = make_rfq(self.inquiry.name, [self.s1])
		sq = make_sq(rfq, self.s1, [100, 200], submit=False)
		sq.items[1].lead_time_days = 0
		sq.items[1].pvfss_availability = None
		sq.save()
		with self.assertRaises(GateFailedError) as ctx:
			sq.submit()
		self.assertIn("lead time", str(ctx.exception))
		self.assertIn("availability", str(ctx.exception))

	def test_rfq05_no_quote_line_passes_and_sets_stage(self):
		rfq = make_rfq(self.inquiry.name, [self.s1])
		sq = make_sq(rfq, self.s1, [100, None])
		self.assertEqual(sq.docstatus, 1)
		self.assertEqual(sq.pvfss_lines_quoted, 1)
		self.assertEqual(stage(self.inquiry.name), inq.QUOTES_RECEIVED)

	def test_rfq04_deviation_needs_note(self):
		rfq = make_rfq(self.inquiry.name, [self.s1])
		sq = make_sq(rfq, self.s1, [100, 200], submit=False)
		sq.items[0].pvfss_compliance = "Deviation"
		sq.items[0].pvfss_deviation_note = ""
		with self.assertRaises(frappe.ValidationError):
			sq.save()

	# ------------------------------------------------------------------ RFQ-06
	def test_rfq06_import_supplier_excel(self):
		rfq = make_rfq(self.inquiry.name, [self.s1])
		sq = make_sq(rfq, self.s1, [1, 1], submit=False)
		csv = (
			"Line Ref,Unit Price,Lead Time Days,Availability,Manufacturer,Origin,Compliance,Deviation Note,No Quote\n"
			"1,125.5,30,RS,Tenaris,Italy,C,,\n"
			"2,,,,,,,,yes\n"
			"9,10,5,RS,,,C,,\n"
		)
		file_doc = frappe.get_doc(
			{"doctype": "File", "file_name": "sq.csv", "content": csv, "is_private": 1}
		).insert()
		result = sq_import.preview(sq.name, file_doc.file_url)
		self.assertEqual(result["ok"], 2)
		self.assertEqual(result["errors"], 1)
		self.assertIn("Line ref not on RFQ", result["rows"][2]["message"])
		self.assertEqual(sq_import.apply(sq.name, file_doc.file_url), 2)
		sq.reload()
		self.assertEqual(flt(sq.items[0].rate), 125.5)
		self.assertEqual(sq.items[0].pvfss_manufacturer, "Tenaris")
		self.assertEqual(sq.items[0].pvfss_origin, "Italy")
		self.assertEqual(sq.items[1].pvfss_no_quote, 1)

	# ------------------------------------------------------------------ RFQ-07 / RFQ-08
	def _three_quotes(self):
		rfq = make_rfq(self.inquiry.name, [self.s1, self.s2, self.s3])
		a = make_sq(rfq, self.s1, [100, 210])
		b = make_sq(rfq, self.s2, [90, 200], compliance=["Not compliant", "Compliant"])
		usd = make_sq(rfq, self.s3, [26, 60], currency="USD")  # 95.485 AED, 220.35 AED
		return rfq, a, b, usd

	def test_rfq07_competitive_statement_lowest_compliant_in_aed(self):
		_rfq, a, b, usd = self._three_quotes()
		_cols, data, *_ = statement({"inquiry": self.inquiry.name})
		line1, line2 = data[0], data[1]
		# Line 1: B is cheapest but Not compliant; USD 26 x 3.6725 = 95.485 beats A's 100
		self.assertEqual(line1.lowest_supplier, self.s3)
		self.assertAlmostEqual(line1.lowest_price, 26 * USD_RATE, delta=0.01)
		self.assertEqual(line1[f"{frappe.scrub(b.name)}_comp"], "NC")
		self.assertEqual(line2.lowest_supplier, self.s2)
		footer = {row.specification: row for row in data if row.get("is_footer")}
		self.assertEqual(footer["Lines quoted"][f"{frappe.scrub(a.name)}_avail"], "2 / 2")
		_cols, data, *_ = statement({"inquiry": self.inquiry.name, "show_in": "Original currency"})
		self.assertEqual(data[0][f"{frappe.scrub(usd.name)}_price"], 26)

	def test_rfq08_single_selection_per_line(self):
		_rfq, a, b, _usd = self._three_quotes()
		selection.select_line(a.items[0].name)
		selection.select_line(b.items[0].name)  # moves the selection
		self.assertEqual(frappe.db.get_value("Supplier Quotation Item", a.items[0].name, "pvfss_selected"), 0)
		self.assertEqual(frappe.db.get_value("Supplier Quotation Item", b.items[0].name, "pvfss_selected"), 1)
		chosen = selection.selected_lines(self.inquiry.name)
		self.assertEqual(chosen["1"].supplier, self.s2)
		# Ticking the same line on another quotation form is refused
		a.reload()
		a.items[0].pvfss_selected = 1
		with self.assertRaises(frappe.ValidationError):
			selection.assert_single_selection(a)

	def test_rfq08_select_lowest_compliant(self):
		self._three_quotes()
		preview = selection.select_lowest(self.inquiry.name, preview=1)
		self.assertEqual({r["line_ref"]: r["supplier"] for r in preview}, {"1": self.s3, "2": self.s2})
		self.assertFalse(selection.selected_lines(self.inquiry.name))
		selection.select_lowest(self.inquiry.name, preview=0)
		self.assertEqual(len(selection.selected_lines(self.inquiry.name)), 2)
		self.assertEqual(selection.clear_selection(self.inquiry.name), 2)

	# ------------------------------------------------------------------ RFQ-09
	def test_rfq09_negotiation_round_updates_rate(self):
		rfq = make_rfq(self.inquiry.name, [self.s1])
		sq = make_sq(rfq, self.s1, [100, 200], submit=False)
		sq.append("pvfss_negotiation_rounds", {"line_ref": "1", "revised_price": 92, "revised_lead_time": 15})
		sq.save()
		self.assertEqual(flt(sq.items[0].rate), 92)
		self.assertEqual(sq.items[0].lead_time_days, 15)
		r = sq.pvfss_negotiation_rounds[0]
		self.assertEqual(
			(r.round_no, flt(r.previous_price), r.previous_lead_time, r.applied), (1, 100, 20, 1)
		)
		self.assertEqual(flt(sq.items[0].amount), 92 * sq.items[0].qty)
		sq.append("pvfss_negotiation_rounds", {"line_ref": "1", "revised_price": 90})
		sq.save()
		self.assertEqual(sq.pvfss_negotiation_rounds[1].round_no, 2)
		self.assertEqual(flt(sq.pvfss_negotiation_rounds[1].previous_price), 92)

	# ------------------------------------------------------------------ RFQ-10
	def _costed(self, margin=20):
		rfq = make_rfq(self.inquiry.name, [self.s1, self.s3])
		frappe.db.set_value("Opportunity Item", {"parent": self.inquiry.name, "idx": 1}, "qty", 10)
		frappe.db.set_value("Opportunity Item", {"parent": self.inquiry.name, "idx": 2}, "qty", 5)
		a = make_sq(rfq, self.s1, [100, 999])
		usd = make_sq(rfq, self.s3, [999, 50], currency="USD")
		selection.select_line(a.items[0].name)
		selection.select_line(usd.items[1].name)
		cs = frappe.get_doc(frappe.get_doc("Costing Sheet", make_or_refresh(self.inquiry.name)))
		cs.target_margin_pct = margin
		return cs

	def test_rfq10_costing_sheet_hand_calculation(self):
		cs = self._costed()
		self.assertEqual(stage(self.inquiry.name), inq.UNDER_EVALUATION)
		cs.append(
			"allocations", {"cost_type": "Freight", "basis": "Amount", "value": 1000, "method": "By value"}
		)
		cs.append("allocations", {"cost_type": "Testing", "basis": "%", "value": 10, "method": "By value"})
		cs.save()
		l1, l2 = cs.items
		self.assertEqual((l1.qty, l2.qty), (10, 5))
		self.assertAlmostEqual(l1.unit_cost, 100)
		self.assertAlmostEqual(l2.unit_cost, 50 * USD_RATE)  # 183.625
		supplier_total = 10 * 100 + 5 * 183.625  # 1918.125
		self.assertAlmostEqual(cs.total_supplier_cost, round(supplier_total, 2))
		# Freight 1000 by value: line 1 gets 1000 x 1000 / 1918.125 over 10 units
		self.assertAlmostEqual(l1.freight, round(1000 * 1000 / supplier_total / 10, 4), places=3)
		# Testing 10% of supplier cost by value = 10% of each line's unit cost
		self.assertAlmostEqual(l1.testing, 10, places=3)
		self.assertAlmostEqual(l2.testing, 18.3625, places=3)
		self.assertAlmostEqual(cs.total_allocations, round(1000 + supplier_total * 0.1, 2), places=1)
		# Target price = landed / (1 - 20%)
		self.assertAlmostEqual(l1.target_price, l1.landed_unit_cost / 0.8, places=3)
		self.assertAlmostEqual(cs.margin_pct, 20, places=1)
		# A selling price override changes the margin
		l1.selling_price = l1.landed_unit_cost
		cs.save()
		self.assertLess(cs.margin_pct, 20)

	def test_rfq10_allocation_by_weight_and_manual(self):
		cs = self._costed()
		cs.items[0].weight_per_unit = 30
		cs.items[1].weight_per_unit = 0
		cs.items[1].documentation = 7
		cs.append(
			"allocations", {"cost_type": "Freight", "basis": "Amount", "value": 600, "method": "By weight"}
		)
		cs.append(
			"allocations", {"cost_type": "Documentation", "basis": "Amount", "value": 0, "method": "Manual"}
		)
		cs.save()
		self.assertAlmostEqual(cs.items[0].freight, 60)  # all weight on line 1: 600 / 10 units
		self.assertAlmostEqual(cs.items[1].freight, 0)
		self.assertAlmostEqual(cs.items[1].documentation, 7)
		self.assertAlmostEqual(cs.allocations[1].allocated_amount, 35)

	def test_rfq10_one_costing_sheet_per_inquiry_and_revision(self):
		cs = self._costed()
		cs.save()
		dup = frappe.copy_doc(cs)
		with self.assertRaises(frappe.ValidationError):
			dup.insert()
		cs.submit()
		self.assertEqual(make_or_refresh(self.inquiry.name), cs.name)
		cs.cancel()
		amended = frappe.copy_doc(cs)
		amended.amended_from = cs.name
		amended.docstatus = 0
		amended.insert()
		self.assertEqual(amended.revision, 1)

	# ------------------------------------------------------------------ RFQ-11 / RFQ-12
	def _evaluation(self, compliance):
		te = frappe.get_doc({"doctype": "Technical Evaluation", "inquiry": self.inquiry.name})
		te.insert()
		for row in te.items:
			row.compliance = compliance.get(row.supplier_quotation_item, "Compliant")
			if row.compliance != "Compliant":
				row.deviation_description = "Bevel angle"
		te.save()
		return te

	def test_rfq11_blocks_noncompliant_selected_line(self):
		cs = self._costed()
		cs.save()
		line2 = cs.items[1].supplier_quotation_item
		te = self._evaluation({line2: "Not compliant"})
		self.assertEqual(len(te.items), 4)
		self.assertEqual(sum(r.selected for r in te.items), 2)
		with self.assertRaises(GateFailedError) as ctx:
			te.submit()
		self.assertIn("Line 2", str(ctx.exception))
		te.reload()
		for row in te.items:
			if row.supplier_quotation_item == line2:
				row.compliance = "Compliant with deviation"
		te.save()
		te.submit()
		self.assertEqual(te.docstatus, 1)

	def test_rfq12_blocks_quotation_creation(self):
		cs = self._costed()
		cs.save()
		cs.submit()
		result = g1.check(cs.name)
		self.assertTrue(result.failures, "no Technical Evaluation yet")
		line2 = cs.items[1].supplier_quotation_item
		te = self._evaluation({line2: "Compliant with deviation"})
		te.submit()
		self.assertFalse(g1.check(cs.name).failures)
		# A later evaluation finding line 2 Not compliant blocks the quotation again
		te2 = frappe.copy_doc(te)
		te2.docstatus = 0
		for row in te2.items:
			if row.supplier_quotation_item == line2:
				row.compliance = "Not compliant"
		te2.insert()
		frappe.db.set_value("Technical Evaluation", te2.name, "docstatus", 1)
		result = g1.check(cs.name)
		self.assertEqual(len(result.failures), 1)
		self.assertIn("Lines 2 are not technically compliant", result.failures[0]["message"])
		cs.reload()
		cs.calculate()
		self.assertEqual(cs.non_compliant_lines, 1)

	# ------------------------------------------------------------------ RFQ-03
	def test_rfq03_subject_template_and_print_format(self):
		rfq = make_rfq(self.inquiry.name, [self.s1], submit=False)
		self.assertTrue(rfq.subject.startswith(f"RFQ {rfq.name} - {self.inquiry.pvfss_contractor_ref}"))
		self.assertTrue(frappe.db.exists("Email Template", "PVFSS RFQ"))
		html = f.render_print(rfq, "PVFSS RFQ")
		self.assertIn("Spec line 1", html)
		self.assertIn("Lead time", html)
