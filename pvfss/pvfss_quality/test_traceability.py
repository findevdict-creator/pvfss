"""Module 9 tests (TRC-01 to TRC-13, G6). Names carry the requirement ID (GEN-07)."""

import frappe
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from pvfss.gates.base import GateFailedError
from pvfss.pvfss_quality import traceability
from pvfss.pvfss_quality.report.heat_number_register import heat_number_register
from pvfss.tests import factories as f

ITEM = "_PVFSS TRC Pipe"
MILL = "_PVFSS Test Mill"


def mill(name=MILL, abbr="TM"):
	if not frappe.db.exists("Manufacturer", name):
		frappe.get_doc({"doctype": "Manufacturer", "short_name": name, "pvfss_abbr": abbr}).insert()
	return name


def item():
	return f.make_item(ITEM, has_batch_no=1, pvfss_heat_traceable=1).name


def make_batch(heat, lot, item_code=None):
	return frappe.get_doc(
		{"doctype": "Batch", "item": item_code or item(), "pvfss_heat_number": heat, "pvfss_lot_no": lot}
	).insert()


def make_po(qty=10, rate=50):
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": f.make_supplier("_PVFSS TRC Supplier").name,
			"company": f.TEST_COMPANY,
			"transaction_date": nowdate(),
			"schedule_date": add_days(nowdate(), 10),
			"items": [
				{
					"item_code": item(),
					"qty": qty,
					"rate": rate,
					"schedule_date": add_days(nowdate(), 10),
					"warehouse": f.warehouse(),
				}
			],
		}
	).insert()
	return f.submit_purchase_order(po)


def receive(po, batch=None):
	pr = make_purchase_receipt(po.name)
	pr.posting_date = nowdate()
	for row in pr.items:
		row.warehouse = f.warehouse()
		if batch:
			row.use_serial_batch_fields = 1
			row.batch_no = batch
	pr.insert()
	return pr


def deliver(batch, qty=4):
	dn = frappe.get_doc(
		{
			"doctype": "Delivery Note",
			"customer": f.make_customer().name,
			"company": f.TEST_COMPANY,
			"posting_date": nowdate(),
			"selling_price_list": f.price_list(),
			"items": [
				{
					"item_code": item(),
					"qty": qty,
					"rate": 100,
					"warehouse": f.warehouse(),
					"use_serial_batch_fields": 1,
					"batch_no": batch,
				}
			],
		}
	).insert()
	return dn


class TestTraceability(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def stocked_heat(self):
		heat = traceability.get_or_create_heat("7a1234", mill(), item(), grade="API 5L X52", mtc="MTC-001")
		batch = make_batch(heat, "L1").name
		po = make_po()
		pr = receive(po, batch)
		pr.submit()
		return heat, batch, po, pr

	# ------------------------------------------------------------------ TRC-01
	def test_trc01_heat_id_and_uniqueness(self):
		heat = traceability.get_or_create_heat(" 7a1234 ", mill(), item())
		self.assertEqual(heat, "TM-7A1234")
		self.assertEqual(traceability.get_or_create_heat("7A1234", MILL, item()), heat)
		with self.assertRaises(frappe.ValidationError) as ctx:
			frappe.get_doc(
				{"doctype": "Heat Number", "heat_no": "7a1234", "manufacturer": MILL, "item_code": item()}
			).insert()
		self.assertIn("already exists", str(ctx.exception))

	# ------------------------------------------------------------------ TRC-02
	def test_trc02_batch_named_heat_lot_and_requires_heat(self):
		heat = traceability.get_or_create_heat("H100", mill(), item())
		self.assertEqual(make_batch(heat, "L 7").name, f"{heat}-L7")
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({"doctype": "Batch", "item": item(), "batch_id": "_PVFSS-NOHEAT"}).insert()

	# ------------------------------------------------------------------ TRC-03 / G6
	def test_trc03_g6_receipt_needs_batch_with_heat(self):
		po = make_po()
		pr = receive(po)
		with self.assertRaises(GateFailedError) as ctx:
			pr.submit()
		self.assertIn("no batch", str(ctx.exception))

	def test_trc03_receipt_links_batch_to_po_and_totals(self):
		heat, batch, po, _pr = self.stocked_heat()
		self.assertEqual(frappe.db.get_value("Batch", batch, "pvfss_supplier_po"), po.name)
		row = frappe.db.get_value(
			"Heat Number", heat, ["batch_count", "qty_received", "balance_qty"], as_dict=True
		)
		self.assertEqual((row.batch_count, flt(row.qty_received), flt(row.balance_qty)), (1, 10, 10))

	# ------------------------------------------------------------------ TRC-04
	def test_trc04_heat_on_hold_blocks_delivery(self):
		heat, batch, _po, _pr = self.stocked_heat()
		traceability.set_heat_status(heat, "On hold", "NCR-TEST Major")
		self.assertEqual(frappe.db.get_value("Batch", batch, "pvfss_heat_status"), "On hold")
		dn = deliver(batch)
		with self.assertRaises(GateFailedError) as ctx:
			dn.submit()
		self.assertIn("On hold", str(ctx.exception))
		traceability.set_heat_status(heat, "Active")
		dn.reload()
		dn.submit()
		self.assertEqual(flt(frappe.db.get_value("Heat Number", heat, "qty_shipped")), 4)

	# ------------------------------------------------------------------ TRC-10
	def test_trc10_forward_trace_reaches_customer_and_invoice(self):
		heat, batch, _po, pr = self.stocked_heat()
		dn = deliver(batch)
		dn.submit()
		si = make_sales_invoice(dn.name)
		si.insert()
		si.submit()
		r = traceability.trace("Heat Number", heat)
		nodes = {c["stage"]: {n["name"] for n in c["nodes"]} for c in r["columns"]}
		self.assertEqual(r["direction"], "forward")
		self.assertIn(batch, nodes["Lot"])
		self.assertIn(pr.name, nodes["Receipt"])
		self.assertIn(dn.name, nodes["Delivery Note"])
		self.assertIn(f.make_customer().name, nodes["Customer"])
		self.assertIn(si.name, nodes["Sales Invoice"])
		self.assertEqual(
			{n["facts"]["Balance"] for n in next(c for c in r["columns"] if c["stage"] == "Stock")["nodes"]},
			{6},
		)
		self.assertEqual([(t["lot"], t["delivery"], t["qty"]) for t in r["table"]], [(batch, dn.name, 4)])

	def test_trc10_backward_trace_from_invoice(self):
		heat, batch, po, _pr = self.stocked_heat()
		dn = deliver(batch)
		dn.submit()
		si = make_sales_invoice(dn.name)
		si.insert()
		si.submit()
		r = traceability.trace("Sales Invoice", si.name)
		nodes = {c["stage"]: {n["name"] for n in c["nodes"]} for c in r["columns"]}
		self.assertEqual(r["direction"], "backward")
		self.assertEqual(nodes["Heat"], {heat})
		self.assertIn(po.name, nodes["Supplier PO"])
		self.assertIn(MILL, nodes["Supplier / mill"])
		self.assertEqual(r["table"][0]["mtc"], "MTC-001")

	def test_trc10_search_by_supplier_po_and_mtc(self):
		_heat, batch, po, _pr = self.stocked_heat()
		self.assertEqual(traceability.trace("Supplier PO", po.name)["lots"], 1)
		self.assertEqual(traceability.trace("MTC No", "MTC-001")["heats"], 1)
		self.assertEqual(traceability.trace("Batch", batch)["heats"], 1)

	# ------------------------------------------------------------------ TRC-11
	def test_trc11_report_and_certificate_pack(self):
		import io
		import zipfile

		heat, _batch, _po, _pr = self.stocked_heat()
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "mtc-001.txt",
				"content": "MTC body",
				"attached_to_doctype": "Heat Number",
				"attached_to_name": heat,
				"is_private": 1,
			}
		).insert()
		r = traceability.trace("Heat Number", heat)
		html = traceability.report_html(r)
		self.assertIn("Traceability Report", html)
		self.assertIn("MTC-001", html)
		names = zipfile.ZipFile(io.BytesIO(traceability.build_zip(r, b"%PDF"))).namelist()
		self.assertIn("00-index.pdf", names)
		self.assertIn(f"{heat}/{heat}/mtc-001.txt", names)

	# ------------------------------------------------------------------ TRC-12
	def test_trc12_register(self):
		heat, _batch, po, _pr = self.stocked_heat()
		_cols, rows = heat_number_register.execute({"supplier_po": po.name})
		self.assertEqual([r["heat"] for r in rows], [heat])
		self.assertEqual(
			(rows[0]["qty_received"], rows[0]["balance"], rows[0]["mtc_no"]), (10, 10, "MTC-001")
		)

	# ------------------------------------------------------------------ TRC-13
	def test_trc13_heat_index_on_batch(self):
		indexes = frappe.db.sql("show index from `tabBatch` where Column_name = 'pvfss_heat_number'")
		self.assertTrue(indexes)
