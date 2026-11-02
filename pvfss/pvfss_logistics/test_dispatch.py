"""Module 10 tests (DSP-02, DSP-03, DSP-07, DSP-09, DSP-10, G7). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from pvfss.gates.base import GateFailedError
from pvfss.pvfss_logistics import dispatch
from pvfss.pvfss_quality import traceability
from pvfss.pvfss_quality.test_traceability import deliver, item, make_batch, make_po, mill, receive
from pvfss.tests import factories as f
from pvfss.utils import settings


def stocked_batch(heat_no="D100", qty=10):
	heat = traceability.get_or_create_heat(heat_no, mill(), item(), grade="API 5L X52")
	batch = make_batch(heat, "L1").name
	po = make_po(qty=qty)
	receive(po, batch).submit()
	return heat, batch, po


def issue_irn(po, heat, batch, qty, name="IRN-DSP-TEST-1"):
	"""An issued IRN for one batch (the G5 gate itself is covered in test_quality)."""
	irn = frappe.get_doc(
		{
			"doctype": "IRN",
			"name": name,
			"supplier_po": po.name,
			"issue_date": nowdate(),
			"docstatus": 1,
			"lines": [{"line_ref": "1", "heat_number": heat, "batch": batch, "qty_released": qty}],
		}
	)
	irn.db_insert()
	for row in irn.lines:
		row.docstatus = 1
		row.db_insert()
	return irn.name


class TestDispatch(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def setUp(self):
		frappe.db.set_value("Item", item(), "pvfss_irn_required", 1)
		settings.clear_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	# ------------------------------------------------------------------ DSP-02 / G7
	def test_dsp02_batch_must_be_on_issued_irn(self):
		heat, batch, po = stocked_batch()
		dn = deliver(batch, qty=4)
		self.assertEqual(dn.items[0].pvfss_gate_status, "✗ no IRN")
		with self.assertRaises(GateFailedError) as ctx:
			dn.submit()
		self.assertIn(f"batch {batch}: not on any issued IRN", str(ctx.exception))

		irn = issue_irn(po, heat, batch, qty=6)
		dn = frappe.get_doc("Delivery Note", dn.name)
		dn.save()
		self.assertEqual((dn.items[0].pvfss_irn, dn.items[0].pvfss_gate_status), (irn, "✓"))
		self.assertEqual(dn.pvfss_dispatch_gate, "OK")
		dn.submit()

		second = deliver(batch, qty=3)
		self.assertEqual(second.items[0].pvfss_shipped_before, 4)
		with self.assertRaises(GateFailedError) as ctx:
			second.submit()
		self.assertIn(f"shipping 3, {irn} released 6, already shipped 4", str(ctx.exception))

	def test_dsp02_setting_allows_dispatch_without_irn_when_item_does_not_need_one(self):
		_heat, batch, _po = stocked_batch()
		frappe.db.set_value("Item", item(), "pvfss_irn_required", 0)
		frappe.db.set_single_value("PVFSS Settings", "allow_dispatch_without_irn", 1)
		settings.clear_cache()
		dn = deliver(batch, qty=2)
		dn.submit()
		self.assertEqual(dn.docstatus, 1)

	# ------------------------------------------------------------------ DSP-03
	def test_dsp03_documents_prefilled_and_required_before_complete(self):
		heat, batch, po = stocked_batch()
		irn = issue_irn(po, heat, batch, qty=10)
		dn = deliver(batch, qty=4)
		docs = {r.document: r for r in dn.pvfss_dispatch_documents}
		self.assertIn("Delivery Note (signed)", docs)  # Road template
		self.assertNotIn("Bill of Lading", docs)
		self.assertEqual(
			(docs["IRN / MPQT documentation"].status, docs["IRN / MPQT documentation"].remarks),
			("Ready", irn),
		)
		self.assertEqual(docs["MTCs"].status, "Pending")
		self.assertEqual(dn.pvfss_documents_ready, f"1/{len(docs)}")

		with self.assertRaises(frappe.ValidationError) as ctx:
			apply_workflow(dn.as_dict(), "Mark Documents Complete")
		self.assertIn("Packing List", str(ctx.exception))

		dn = frappe.get_doc("Delivery Note", dn.name)
		for row in dn.pvfss_dispatch_documents:
			row.status = "Ready"
		dn.save()
		dn = apply_workflow(dn.as_dict(), "Mark Documents Complete")
		self.assertEqual(dn.workflow_state, dispatch.DOCS_COMPLETE)
		self.assertFalse(dispatch.check_gate(dn.name)["failures"])

	# ------------------------------------------------------------------ DSP-09
	def test_dsp09_pod_marks_delivered_and_drafts_invoice(self):
		heat, batch, po = stocked_batch()
		issue_irn(po, heat, batch, qty=10)
		dn = deliver(batch, qty=4)
		self.assertRaises(
			frappe.ValidationError, dispatch.record_pod, dn.name, nowdate(), "Site", "/files/pod.pdf"
		)
		dn.submit()
		si = dispatch.record_pod(dn.name, nowdate(), "Site store keeper", "/files/pod.pdf", "All received")
		self.assertTrue(si)
		self.assertEqual(frappe.db.get_value("Sales Invoice", si, "docstatus"), 0)
		self.assertEqual(frappe.db.get_value("Delivery Note", dn.name, "workflow_state"), dispatch.DELIVERED)

	# ------------------------------------------------------------------ DSP-10
	def test_dsp10_alert_when_eta_passed_without_pod(self):
		heat, batch, po = stocked_batch()
		issue_irn(po, heat, batch, qty=10)
		dn = deliver(batch, qty=4)
		dn.submit()
		dn.db_set("pvfss_eta", add_days(nowdate(), -5))
		self.assertGreaterEqual(dispatch.pod_alerts(), 1)
		self.assertTrue(frappe.db.get_value("Delivery Note", dn.name, "pvfss_pod_alerted_on"))
		self.assertEqual(dispatch.pod_alerts(), 0)  # once per DN
