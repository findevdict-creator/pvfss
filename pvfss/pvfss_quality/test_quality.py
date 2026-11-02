"""Module 8 tests (QA-01 to QA-35, G5, TRC-04). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, nowdate

from pvfss.gates.base import GateFailedError
from pvfss.overrides import non_conformance as ncr_module
from pvfss.pvfss_crm.test_quotation import make_user
from pvfss.pvfss_purchasing.project import ensure_expediting_log
from pvfss.pvfss_quality import traceability
from pvfss.pvfss_quality.doctype.irn import irn as irn_module
from pvfss.pvfss_quality.doctype.itp import itp as itp_module
from pvfss.pvfss_quality.doctype.quality_document_submittal import quality_document_submittal as qds
from pvfss.pvfss_quality.doctype.rfi import rfi as rfi_module
from pvfss.pvfss_quality.report.inspection_release_tracker import inspection_release_tracker
from pvfss.pvfss_quality.test_smr import ITEM, item, make_po
from pvfss.pvfss_quality.test_traceability import mill
from pvfss.tests import factories as f
from pvfss.utils import settings

POINTS = [
	(10, "Raw material verification", "H", "W", ""),
	(20, "Dimensional check", "W", "", ""),
	(30, "Hydrotest", "H", "H", "W"),
]


def make_itp(po, points=POINTS, approve=True, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "ITP",
			"supplier_po": po.name,
			"points": [
				{"seq": s, "activity": a, "pvfss_point": p, "tpi_point": t, "customer_point": c}
				for s, a, p, t, c in points
			],
			**kw,
		}
	).insert()
	return apply_workflow(doc.as_dict(), "Approve") if approve else doc


def make_rfi(po, itp, seqs, heats=()):
	return frappe.get_doc(
		{
			"doctype": "RFI",
			"supplier_po": po.name,
			"itp": itp.name,
			"proposed_date": add_days(nowdate(), 3),
			"location": "Supplier works",
			"points": [{"seq": s} for s in seqs],
			"material": [{"line_ref": "1", "item_code": item(), "heat_number": h, "qty": 10} for h in heats],
		}
	).insert()


def inspect(rfi, result="Accepted", tests=(), submit=True):
	rfi_module.schedule(rfi.name)
	ir = frappe.get_doc("Inspection Report", rfi_module.make_inspection_report(rfi.name))
	for row in ir.point_results:
		row.result = result
	for t in tests:
		ir.append("test_results", t)
	ir.save()
	if submit:
		ir.submit()
	return ir


def accept_mtc(mtc_doc):
	doc = frappe.get_doc("MTC", mtc_doc.name)
	doc.append(
		"verifications", {"method": "Mill / supplier confirmation", "reference": "mail", "result": "Verified"}
	)
	doc.save()
	doc = apply_workflow(doc.as_dict(), "Submit for Review")
	doc = apply_workflow(doc.as_dict(), "Send to Quality Manager")
	return apply_workflow(doc.as_dict(), "Accept")


def draft_mtc(po, heats, issue_date=None):
	doc = frappe.get_doc(
		{
			"doctype": "MTC",
			"certificate_no": "CERT-Q1",
			"manufacturer": mill(),
			"issue_date": issue_date or add_months(nowdate(), -3),
			"certificate_type": "EN 10204 3.1",
			"product_standard": "ASTM A106",
			"grade": "B",
			"supplier_po": po.name,
			"attachment": "/files/mtc.pdf",
			"items": [{"item_code": item()}],
			"heats": [{"heat_no": h, "qty": q} for h, q in heats],
		}
	)
	return doc.insert()


class TestQuality(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	# ------------------------------------------------------------------ QA-01
	def test_qa01_submittal_revisions(self):
		po = make_po()
		doc = frappe.get_doc(
			{
				"doctype": "Quality Document Submittal",
				"supplier_po": po.name,
				"document_type": "ITP",
				"document_no": "ITP-SUP-01",
				"revision": 0,
				"attachment": "/files/itp.pdf",
				"customer_approval_required": 1,
				"sent_to_customer_date": add_days(nowdate(), -4),
			}
		).insert()
		self.assertEqual(doc.days_waiting, 4)
		rev = frappe.get_doc("Quality Document Submittal", qds.new_revision(doc.name))
		self.assertEqual((rev.revision, rev.customer_response), (1, "Pending"))
		dup = frappe.copy_doc(doc)
		with self.assertRaises(frappe.ValidationError):
			dup.insert()

	# ------------------------------------------------------------------ QA-02
	def test_qa02_manufacturing_start_needs_approved_submittals(self):
		po = make_po()
		doc = frappe.get_doc(
			{
				"doctype": "Quality Document Submittal",
				"supplier_po": po.name,
				"document_type": "Drawing",
				"document_no": "DWG-1",
				"revision": 0,
				"attachment": "/files/dwg.pdf",
				"customer_approval_required": 1,
			}
		).insert()
		log = frappe.get_doc("Expediting Log", ensure_expediting_log(po.name))
		log.supply_route = "Manufacturing"
		log.save()
		row = next(r for r in log.milestones if r.milestone == "Manufacturing start")
		row.actual_date = nowdate()
		with self.assertRaises(frappe.ValidationError) as ctx:
			log.save()
		self.assertIn("Drawing DWG-1 rev 0", str(ctx.exception))
		doc.customer_response = "Approved with comments"
		doc.save()
		log = frappe.get_doc("Expediting Log", log.name)
		next(r for r in log.milestones if r.milestone == "Manufacturing start").actual_date = nowdate()
		log.save()

	# ------------------------------------------------------------------ QA-03 / QA-04
	def test_qa04_itp_from_template_and_customer_approval(self):
		po = make_po()
		itp = frappe.get_doc(
			{
				"doctype": "ITP",
				"supplier_po": po.name,
				"template": "SMR - document review + visual",
				"points": [],
			}
		)
		itp.flags.ignore_mandatory = True
		itp.insert()
		self.assertEqual([p.seq for p in itp.points], [10, 20, 30])
		self.assertEqual(itp.next_hold_point, "20 (Visual and marking check)")
		other = make_itp(po, approve=False, customer_approval_required=1)
		other = apply_workflow(other.as_dict(), "Send for Customer Approval")
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(other.as_dict(), "Approve")
		other = frappe.get_doc("ITP", other.name)
		other.customer_approval_ref = "CUST-ITP-OK"
		other.save()
		self.assertEqual(apply_workflow(other.as_dict(), "Approve").docstatus, 1)

	def test_qa04_rfi_needs_approved_itp(self):
		po = make_po()
		itp = make_itp(po, approve=False)
		with self.assertRaises(frappe.ValidationError):
			make_rfi(po, itp, [10])

	# ------------------------------------------------------------------ QA-12
	def test_qa12_hold_point_waits_for_earlier_hold(self):
		po = make_po()
		itp = make_itp(po)
		late = make_rfi(po, itp, [30])
		self.assertEqual(late.points_label, "30 (H)")
		self.assertEqual(late.parties_required, "PVFSS, TPI, Customer")
		with self.assertRaises(GateFailedError) as ctx:
			rfi_module.schedule(late.name)
		self.assertIn(
			"Hold point 30 (Hydrotest) cannot be scheduled: Hold point 10 (Raw material verification) is still open.",
			str(ctx.exception),
		)
		first = make_rfi(po, itp, [10])
		inspect(first)
		self.assertEqual(frappe.db.get_value("RFI", first.name, "status"), "Closed")
		itp.reload()
		self.assertEqual(itp.points[0].status, "Closed")
		self.assertEqual(rfi_module.schedule(late.name), "Scheduled")
		self.assertEqual(
			rfi_module.reschedule(late.name, add_days(nowdate(), 9), "Supplier delay"), "Rescheduled"
		)

	# ------------------------------------------------------------------ QA-13 / QA-24
	def test_qa13_report_results_close_points_and_auto_pass_fail(self):
		po = make_po()
		itp = make_itp(po)
		rfi = make_rfi(po, itp, [10, 20])
		ir = inspect(
			rfi,
			tests=[
				{"test_type": "Hardness", "parameter": "HB", "spec_max": 200, "actual": 210},
				{
					"test_type": "Dimensional",
					"parameter": "OD",
					"spec_min": 168,
					"spec_max": 169,
					"actual": 168.3,
				},
			],
			submit=False,
		)
		self.assertEqual([r.result for r in ir.test_results], ["Fail", "Pass"])
		self.assertEqual((ir.tests_failed, ir.result_summary), (1, "Accepted"))
		ir.point_results[1].result = "Rejected"
		ir.save()
		ir.submit()
		itp.reload()
		self.assertEqual([p.status for p in itp.points], ["Closed", "Open", "Open"])
		self.assertEqual(itp.points[0].closed_by, ir.name)
		self.assertEqual(frappe.db.get_value("RFI", rfi.name, "status"), "Inspected")
		ncr = frappe.get_doc(
			"Non Conformance",
			frappe.get_attr("pvfss.pvfss_quality.doctype.inspection_report.inspection_report.make_ncr")(
				ir.name
			),
		)
		self.assertIn("Hardness HB", ncr.details)

	# ------------------------------------------------------------------ QA-14
	def test_qa14_pipe_sampling_needs_sample_per_heat(self):
		po = make_po()
		mtc = draft_mtc(po, [("Q1", 10), ("Q2", 10)])
		heats = [r.heat_number for r in mtc.heats]
		itp = make_itp(po)
		rfi = make_rfi(po, itp, [10], heats=heats)
		ir = inspect(
			rfi,
			tests=[
				{"test_type": "Mechanical", "heat_number": heats[0], "sample_id": "S-1", "parameter": "UTS"}
			],
			submit=False,
		)
		self.assertIn(heats[1], ir.sampling_check)
		with self.assertRaises(GateFailedError) as ctx:
			ir.submit()
		self.assertIn(f"350 mm sample ID: {heats[1]}", str(ctx.exception))
		ir = frappe.get_doc("Inspection Report", ir.name)
		ir.append("test_results", {"test_type": "Mechanical", "heat_number": heats[1], "sample_id": "S-2"})
		ir.save()
		ir.submit()

	# ------------------------------------------------------------------ QA-20 to QA-23
	def test_qa22_mtc_accept_needs_verified_authenticity(self):
		po = make_po()
		mtc = draft_mtc(po, [("Q5", 10)])
		self.assertTrue(mtc.heats[0].heat_number)  # TRC-01: heat linked on save
		self.assertEqual(mtc.authenticity, "Not verified")
		doc = apply_workflow(mtc.as_dict(), "Submit for Review")
		self.assertEqual(doc.reviewer, "Administrator")
		doc = apply_workflow(doc.as_dict(), "Send to Quality Manager")
		with self.assertRaises(GateFailedError) as ctx:
			apply_workflow(doc.as_dict(), "Accept")
		self.assertIn("Add at least one verified authenticity check", str(ctx.exception))
		doc = frappe.get_doc("MTC", doc.name)
		doc.append("verifications", {"method": "QR / electronic verification", "result": "Verified"})
		doc.append("chemical", {"element": "C", "value": 0.31, "spec_max": 0.30})
		doc.save()
		self.assertEqual(doc.chemical[0].result, "Fail")
		doc = apply_workflow(doc.as_dict(), "Accept")
		self.assertEqual((doc.docstatus, doc.review_result), (1, "Accepted"))

	def test_qa21_over_age_mtc_needs_retest(self):
		po = make_po()
		mtc = draft_mtc(po, [("Q6", 10)], issue_date=add_months(nowdate(), -26))
		mtc.append("verifications", {"method": "Repeat testing", "result": "Verified"})
		mtc.save()
		self.assertTrue(mtc.age_over)
		doc = apply_workflow(mtc.as_dict(), "Submit for Review")
		doc = apply_workflow(doc.as_dict(), "Send to Quality Manager")
		with self.assertRaises(GateFailedError) as ctx:
			apply_workflow(doc.as_dict(), "Accept")
		self.assertIn("Use Accepted with re-test", str(ctx.exception))
		with self.assertRaises(GateFailedError):
			apply_workflow(doc.as_dict(), "Accept with Re-test")
		itp = make_itp(po)
		ir = inspect(make_rfi(po, itp, [10]))
		doc = frappe.get_doc("MTC", doc.name)
		doc.retest_report = ir.name
		doc.save()
		self.assertEqual(
			apply_workflow(doc.as_dict(), "Accept with Re-test").review_result, "Accepted with re-test"
		)

	# ------------------------------------------------------------------ QA-30 / TRC-04
	def make_ncr(self, heat, severity="Major", po=None):
		return frappe.get_doc(
			{
				"doctype": "Non Conformance",
				"subject": "Pitting on pipe ends",
				"pvfss_source": "Internal",
				"pvfss_supplier_po": po and po.name,
				"pvfss_severity": severity,
				"pvfss_heats": [{"heat_number": heat}],
			}
		).insert()

	def test_qa30_major_ncr_holds_heat_until_closed(self):
		po = make_po()
		heat = draft_mtc(po, [("Q7", 10)]).heats[0].heat_number
		minor = self.make_ncr(heat, "Minor", po)
		self.assertEqual(frappe.db.get_value("Heat Number", heat, "status"), "Active")
		self.assertEqual(
			str(minor.pvfss_response_due), add_days(nowdate(), settings.get_int("ncr_response_days", 7))
		)
		ncr = self.make_ncr(heat, "Major", po)
		self.assertEqual(frappe.db.get_value("Heat Number", heat, "status"), "On hold")
		self.assertEqual(traceability.heat_summary(heat)["open_ncrs"], 2)
		ncr = apply_workflow(ncr.as_dict(), "Send to Supplier")
		ncr = apply_workflow(ncr.as_dict(), "Submit for Verification")
		with self.assertRaises(frappe.ValidationError):
			apply_workflow(ncr.as_dict(), "Close")
		ncr = frappe.get_doc("Non Conformance", ncr.name)
		ncr.pvfss_verified_by = "Administrator"
		ncr.pvfss_verification_date = nowdate()
		ncr.save()
		ncr = apply_workflow(ncr.as_dict(), "Close")
		self.assertEqual((ncr.workflow_state, ncr.status), ("Closed", "Resolved"))
		self.assertEqual(frappe.db.get_value("Heat Number", heat, "status"), "Active")

	def test_qa31_overdue_supplier_response_alert(self):
		po = make_po()
		heat = draft_mtc(po, [("Q8", 10)]).heats[0].heat_number
		ncr = self.make_ncr(heat, "Minor", po)
		frappe.db.set_value("Non Conformance", ncr.name, "pvfss_response_due", add_days(nowdate(), -1))
		make_user("pvfss.qu@example.com", "Quality User")
		self.assertEqual(ncr_module.overdue_alerts(), 1)
		self.assertEqual(ncr_module.overdue_alerts(), 0)
		self.assertTrue(
			frappe.db.exists(
				"Notification Log", {"for_user": "pvfss.qu@example.com", "document_name": ncr.name}
			)
		)

	# ------------------------------------------------------------------ QA-32 to QA-35 / G5
	def make_irn(self, po, heat, qty=10):
		return frappe.get_doc(
			{
				"doctype": "IRN",
				"supplier_po": po.name,
				"lines": [{"line_ref": "1", "heat_number": heat, "qty_released": qty}],
			}
		).insert()

	def test_qa33_irn_gate_lists_every_failure(self):
		po = make_po(qty=20)
		mtc = draft_mtc(po, [("Q9", 20)])
		heat = mtc.heats[0].heat_number
		itp = make_itp(po, points=[(10, "Final visual", "W", "", "")])
		ncr = self.make_ncr(heat, "Minor", po)
		irn = self.make_irn(po, heat, qty=25)
		with self.assertRaises(GateFailedError) as ctx:
			irn = apply_workflow(irn.as_dict(), "Send for Approval")
			apply_workflow(irn.as_dict(), "Issue")
		text = str(ctx.exception)
		self.assertIn(f"{itp.name} point 10 (Final visual) is Open.", text)
		self.assertIn(f"{ncr.name} (Minor) on heat {heat} is still open.", text)
		self.assertIn(f"Heat {heat} has no accepted MTC", text)
		self.assertIn("Line 1: releasing 25, remaining 20.", text)
		self.assertFalse(irn_module.check_gate(irn.name)["ok"])

		inspect(
			make_rfi(po, itp, [10], heats=[heat]),
			tests=[{"test_type": "Visual", "heat_number": heat, "sample_id": "V1"}],
		)
		ncr = frappe.get_doc("Non Conformance", ncr.name)
		ncr.pvfss_verified_by, ncr.pvfss_verification_date = "Administrator", nowdate()
		ncr.save()
		ncr = apply_workflow(ncr.as_dict(), "Send to Supplier")
		ncr = apply_workflow(ncr.as_dict(), "Submit for Verification")
		apply_workflow(ncr.as_dict(), "Close")
		accept_mtc(mtc)
		irn = frappe.get_doc("IRN", irn.name)
		irn.lines[0].qty_released = 12
		irn.save()
		self.assertEqual(irn.lines[0].gate_status, "✓")
		self.assertEqual(irn.lines[0].mtc, mtc.name)
		if irn.workflow_state == "Draft":
			irn = apply_workflow(irn.as_dict(), "Send for Approval")
		irn = apply_workflow(irn.as_dict(), "Issue")
		self.assertEqual((irn.docstatus, irn.issued_by), (1, "Administrator"))

		second = self.make_irn(po, heat, qty=8)
		self.assertEqual((flt(second.lines[0].previously_released), flt(second.lines[0].remaining)), (12, 8))
		nodes = {
			c["stage"]: {n["name"] for n in c["nodes"]}
			for c in traceability.trace("Heat Number", heat)["columns"]
		}
		self.assertIn(irn.name, nodes["IRN"])
		self.assertTrue(nodes["Inspection"])

		_cols, rows = inspection_release_tracker.execute({"supplier_po": po.name})
		self.assertEqual((rows[0]["points_closed"], rows[0]["irn_qty"], rows[0]["rfi_closed"]), (1, 12, 1))

	def test_qa33_on_hold_heat_blocks_irn(self):
		po = make_po()
		mtc = draft_mtc(po, [("Q10", 10)])
		heat = mtc.heats[0].heat_number
		accept_mtc(mtc)
		self.make_ncr(heat, "Critical", po)
		irn = self.make_irn(po, heat)
		self.assertTrue(irn.lines[0].gate_status.startswith("✗"))
		messages = [f["message"] for f in irn_module.check_gate(irn.name)["failures"]]
		self.assertIn(f"Heat {heat} is On hold.", messages)
		self.assertEqual(ITEM, irn.lines[0].item_code)
