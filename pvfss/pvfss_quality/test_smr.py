"""Module 7 tests (SMR-01 to SMR-31). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, nowdate

from pvfss.gates.base import GateFailedError
from pvfss.pvfss_crm.test_quotation import make_user
from pvfss.pvfss_quality.doctype.smr import smr as smr_module
from pvfss.pvfss_quality.report.heat_stock_balance import heat_stock_balance
from pvfss.pvfss_quality.test_traceability import mill
from pvfss.tests import factories as f
from pvfss.utils import mtc_age, settings

ITEM = "_PVFSS SMR Pipe"
OTHER_ITEM = "_PVFSS SMR Pipe B"


def item(code=ITEM, **kw):
	return f.make_item(code, has_batch_no=1, pvfss_heat_traceable=1, **kw).name


def make_po(qty=20, project=None):
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"supplier": f.make_supplier("_PVFSS SMR Supplier").name,
			"company": f.TEST_COMPANY,
			"transaction_date": nowdate(),
			"schedule_date": add_days(nowdate(), 10),
			"project": project,
			"items": [
				{
					"item_code": item(),
					"qty": qty,
					"rate": 50,
					"schedule_date": add_days(nowdate(), 10),
					"warehouse": f.warehouse(),
				}
			],
		}
	).insert()
	return f.submit_purchase_order(po)


def make_mtc(po, heats, issue_date=None, item_code=None, certificate_no="CERT-1"):
	doc = frappe.get_doc(
		{
			"doctype": "MTC",
			"certificate_no": certificate_no,
			"manufacturer": mill(),
			"issue_date": issue_date or add_months(nowdate(), -6),
			"certificate_type": "EN 10204 3.1",
			"product_standard": "ASTM A106",
			"grade": "B",
			"material_type": "CS",
			"supplier_po": po.name,
			"attachment": "/files/mtc.pdf",
			"items": [{"item_code": item_code or item()}],
			"heats": [{"heat_no": h, "qty": q} for h, q in heats],
		}
	).insert()
	doc.submit()
	return doc


def make_tally(po, lines, smr=None):
	"""lines: [(heat_no, lot, pieces, length_per_piece)] all on PO line 1."""
	return frappe.get_doc(
		{
			"doctype": "Tally Sheet",
			"source_type": "SMR",
			"source_document": smr,
			"supplier_po": po.name,
			"lines": [
				{
					"po_line_ref": "1",
					"item_code": item(),
					"heat_no": h,
					"lot_no": lot,
					"pieces": p,
					"length_per_piece": lpp,
				}
				for h, lot, p, lpp in lines
			],
		}
	).insert()


def make_smr(po, mtc=None, tally=None, offered=20):
	doc = frappe.get_doc(
		{
			"doctype": "SMR",
			"supplier_po": po.name,
			"stock_location": f.warehouse(),
			"date_declared": nowdate(),
			"tally_sheet": tally and tally.name,
			"items": [{"line_ref": "1", "qty_offered": offered}],
			"annexures": [
				{
					"annexure_type": "MTC",
					"reference_doctype": "MTC",
					"reference_name": mtc.name,
					"received": 1,
				}
			]
			if mtc
			else [],
		}
	).insert()
	return doc


def decide(doc, result="Accepted", remark=None, action="Accept"):
	doc = frappe.get_doc("SMR", doc.name)
	for row in doc.items:
		row.line_result = result
		row.remark = remark
	for m in doc.matching:
		if m.result != "Match" and remark:
			m.remark = remark
	doc.save()
	return apply_workflow(doc.as_dict(), action)


class TestSMR(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	def ready(
		self, heats=(("7A1234", 20),), tally=(("7A1234", "L1", 2, 10.0),), issue_date=None, project=None
	):
		po = make_po(project=project)
		mtc = make_mtc(po, heats, issue_date)
		ts = make_tally(po, tally)
		doc = make_smr(po, mtc, ts)
		return po, mtc, ts, doc

	# ------------------------------------------------------------------ SMR-01
	def test_smr01_pulls_open_po_lines(self):
		po = make_po(qty=15)
		doc = frappe.get_doc(
			{
				"doctype": "SMR",
				"supplier_po": po.name,
				"stock_location": f.warehouse(),
				"date_declared": nowdate(),
			}
		).insert()
		self.assertEqual(
			[(r.line_ref, r.item_code, flt(r.qty_offered)) for r in doc.items], [("1", ITEM, 15)]
		)
		self.assertEqual(doc.workflow_state, "Received")
		doc.items[0].qty_offered = 16
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	# ------------------------------------------------------------------ SMR-02
	def test_smr02_requires_mtc_and_tally(self):
		po = make_po()
		doc = make_smr(po)
		with self.assertRaises(GateFailedError) as ctx:
			apply_workflow(doc.as_dict(), "Start Review")
		self.assertIn("MTC annexure not received", str(ctx.exception))
		self.assertIn("Tally Sheet annexure not received", str(ctx.exception))
		mtc = make_mtc(po, [("7A1234", 20)])
		doc = frappe.get_doc("SMR", doc.name)
		doc.tally_sheet = make_tally(po, [("7A1234", "L1", 2, 10.0)]).name
		doc.append(
			"annexures",
			{"annexure_type": "MTC", "reference_doctype": "MTC", "reference_name": mtc.name, "received": 1},
		)
		doc.save()
		self.assertEqual(doc.annexure_progress, "2/2")
		doc = apply_workflow(doc.as_dict(), "Start Review")
		self.assertEqual(doc.workflow_state, "Under Review")
		self.assertEqual(str(doc.review_date), nowdate())

	# ------------------------------------------------------------------ SMR-03 / TRC-01
	def test_smr03_tally_totals_and_heat_link(self):
		po = make_po()
		mtc = make_mtc(po, [("7a1234", 20)])
		ts = make_tally(po, [("7a 1234", "L1", 2, 6.0), ("7A1234", "L2", 1, 8.0)])
		self.assertEqual(ts.lines[0].heat_no, "7A 1234")
		ts = make_tally(po, [("7a1234", "L1", 2, 6.0), ("7A1234", "L2", 1, 8.0)])
		self.assertEqual({r.heat_number for r in ts.lines}, {mtc.heats[0].heat_number})
		self.assertEqual((ts.heat_count, flt(ts.total_length)), (1, 20))
		self.assertEqual([flt(r.qty) for r in ts.lines], [12, 8])

	def test_smr03_import_with_supplier_template(self):
		from pvfss.pvfss_quality import tally_import

		po = make_po()
		ts = frappe.get_doc(
			{"doctype": "Tally Sheet", "source_type": "SMR", "supplier_po": po.name, "lines": []}
		)
		ts.flags.ignore_mandatory = True
		ts.insert()
		template = tally_import.save_template(
			"_PVFSS Mill Tally",
			mapping={"heat_no": "Cast", "lot_no": "Bdl", "pieces": "Nos", "length_per_piece": "Mtr"},
		)
		content = "Line,Cast,Bdl,Nos,Mtr\n1,H900,B1,3,6\n1,,B2,2,6\n1,H901,B3,x,6\n"
		file_doc = frappe.get_doc(
			{"doctype": "File", "file_name": "tally.csv", "content": content, "is_private": 1}
		).insert()
		preview = tally_import.preview(ts.name, file_doc.file_url, template)
		self.assertEqual((preview["ok"], preview["errors"]), (1, 2))
		self.assertIn("Heat number missing", preview["rows"][1]["message"])
		self.assertIn("Pieces is not a number", preview["rows"][2]["message"])
		self.assertEqual(tally_import.import_lines(ts.name, file_doc.file_url, template), 1)
		ts.reload()
		self.assertEqual(
			(ts.lines[0].heat_no, ts.lines[0].lot_no, flt(ts.lines[0].total_length)), ("H900", "B1", 18)
		)

	# ------------------------------------------------------------------ SMR-04
	def test_smr04_detects_heat_not_on_mtc(self):
		_po, _mtc, _ts, doc = self.ready(tally=(("7A1234", "L1", 1, 10.0), ("9Z999", "L2", 1, 10.0)))
		results = {m.key: m.result for m in doc.matching}
		self.assertEqual(results["1|7A1234"], "Match")
		self.assertEqual(results["1|9Z999"], "Heat not on MTC")
		self.assertEqual(doc.match_issues, 1)
		doc = apply_workflow(doc.as_dict(), "Start Review")
		with self.assertRaises(GateFailedError) as ctx:
			decide(doc)
		self.assertIn("Heat not on MTC must be resolved", str(ctx.exception))
		doc = decide(doc, "Accepted with remark", remark="Second heat certified by mill letter")
		self.assertEqual((doc.docstatus, doc.workflow_state), (1, "Accepted"))
		self.assertEqual(frappe.db.get_value("Tally Sheet", doc.tally_sheet, "match_summary"), "All match")

	def test_smr04_qty_and_grade_mismatch(self):
		item(OTHER_ITEM)
		po = make_po()
		mtc = make_mtc(po, [("7A1234", 15)])
		ts = make_tally(po, [("7A1234", "L1", 2, 10.0)])  # 20 m on a heat certified for 15
		doc = make_smr(po, mtc, ts, offered=18)
		results = {m.key: m.result for m in doc.matching}
		self.assertEqual(results["1|7A1234"], "Qty mismatch")
		self.assertEqual(results["1|total"], "Qty mismatch")  # tally 20 vs offered 18
		other = make_mtc(po, [("8B1", 20)], item_code=OTHER_ITEM, certificate_no="CERT-2")
		ts2 = make_tally(po, [("8B1", "L1", 2, 10.0)])
		doc2 = make_smr(po, other, ts2)
		self.assertEqual(doc2.matching[0].result, "Grade mismatch")

	def test_smr04_rejected_mtc_is_ignored(self):
		_po, mtc, _ts, doc = self.ready()
		frappe.db.set_value("MTC", mtc.name, "review_result", "Rejected")
		doc = frappe.get_doc("SMR", doc.name)
		doc.save()
		self.assertEqual(doc.matching[0].result, "Heat not on MTC")

	# ------------------------------------------------------------------ SMR-20
	def test_smr20_over_age_blocks_acceptance_until_director_waiver(self):
		_po, _mtc, _ts, doc = self.ready(issue_date=add_months(nowdate(), -25))
		self.assertTrue(doc.items[0].over_age)
		self.assertTrue(doc.items[0].mtc_age.startswith("25 / 24"))
		doc = apply_workflow(doc.as_dict(), "Start Review")
		with self.assertRaises(GateFailedError) as ctx:
			decide(doc)
		self.assertIn("is 25 months old", str(ctx.exception))
		self.assertIn("Limit 24 months (rule: Pipes + CS, company default)", str(ctx.exception))

		qu = make_user("pvfss.qu@example.com", "Quality User")
		frappe.set_user(qu)
		with self.assertRaises(frappe.PermissionError):
			smr_module.waive_age(doc.name, "1", "CUST-APPROVAL-1")
		frappe.set_user("Administrator")
		smr_module.waive_age(doc.name, "1", "CUST-APPROVAL-1")
		doc = decide(doc)
		self.assertEqual(doc.workflow_state, "Accepted")

	def test_smr20_retest_report_allows_acceptance(self):
		_po, _mtc, _ts, doc = self.ready(issue_date=add_months(nowdate(), -25))
		doc = apply_workflow(doc.as_dict(), "Start Review")
		doc = frappe.get_doc("SMR", doc.name)
		doc.items[0].retest_report = "IR-RETEST-1"
		doc.save()
		self.assertEqual(decide(doc).docstatus, 1)

	def test_smr20_client_project_override_allows_30_months(self):
		cp = f.make_client_project("_PVFSS-CP-SMR")
		cp.set(
			"mtc_age_overrides", [{"product_category": "Pipes", "material_type": "CS", "max_age_months": 30}]
		)
		cp.save()
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "_PVFSS SMR Project",
				"company": f.TEST_COMPANY,
				"pvfss_client_project": cp.name,
			}
		).insert(ignore_permissions=True)
		rule = mtc_age.find_rule(item(), project.name)
		self.assertEqual((rule["months"], rule["label"]), (30, "Pipes + CS"))
		self.assertIn("client project", rule["source"])
		_po, _mtc, _ts, doc = self.ready(issue_date=add_months(nowdate(), -27), project=project.name)
		self.assertFalse(doc.items[0].over_age)
		self.assertEqual(mtc_age.find_rule(item())["months"], 24)

	def test_smr20_no_rule_means_warning_only(self):
		code = f.make_item("_PVFSS SMR Alloy Pipe", pvfss_material_type="Alloy").name
		self.assertIsNone(mtc_age.find_rule(code))
		self.assertEqual(mtc_age.age_months("2024-10-03", "2026-11-05"), 25)
		self.assertEqual(mtc_age.age_months("2024-10-06", "2026-11-05"), 24)

	# ------------------------------------------------------------------ SMR-30 / TRC-02
	def receive(self):
		po, mtc, ts, doc = self.ready(
			heats=(("7A1234", 12), ("7A5678", 8)),
			tally=(("7A1234", "L1", 1, 12.0), ("7A5678", "L2", 1, 8.0)),
		)
		doc = apply_workflow(doc.as_dict(), "Start Review")
		doc = decide(doc)
		pr = frappe.get_doc("Purchase Receipt", smr_module.make_purchase_receipt(doc.name))
		return po, mtc, ts, doc, pr

	def test_smr30_receipt_with_one_batch_per_lot(self):
		po, mtc, ts, doc, pr = self.receive()
		self.assertEqual(pr.pvfss_smr, doc.name)
		self.assertEqual([flt(r.qty) for r in pr.items], [12, 8])
		heats = {r.heat_no: r.heat_number for r in mtc.heats}
		batches = [frappe.get_doc("Batch", r.batch_no) for r in pr.items]
		self.assertEqual([b.pvfss_heat_number for b in batches], [heats["7A1234"], heats["7A5678"]])
		self.assertEqual({b.pvfss_tally_sheet for b in batches}, {ts.name})
		self.assertEqual(batches[0].name, f"{heats['7A1234']}-L1")
		self.assertEqual({r.warehouse for r in pr.items}, {f.warehouse()})
		self.assertEqual(smr_module.make_purchase_receipt(doc.name), pr.name)
		pr.submit()
		self.assertEqual(flt(frappe.db.get_value("Heat Number", heats["7A1234"], "balance_qty")), 12)
		from pvfss.pvfss_quality import traceability

		nodes = {
			c["stage"]: {n["name"] for n in c["nodes"]}
			for c in traceability.trace("Heat Number", heats["7A1234"])["columns"]
		}
		self.assertEqual(nodes["MTC"], {mtc.name})
		back = traceability.trace("Supplier PO", po.name, "backward")
		self.assertIn(
			ts.name, {n["name"] for c in back["columns"] if c["stage"] == "Tally Sheet" for n in c["nodes"]}
		)

	def test_smr30_receipt_needs_acceptance(self):
		_po, _mtc, _ts, doc = self.ready()
		with self.assertRaises(frappe.ValidationError):
			smr_module.make_purchase_receipt(doc.name)

	# ------------------------------------------------------------------ SMR-31
	def test_smr31_heat_stock_balance(self):
		po, mtc, _ts, _doc, pr = self.receive()
		pr.submit()
		_cols, rows = heat_stock_balance.execute({"supplier_po": po.name})
		self.assertEqual(
			sorted((r["heat"], flt(r["balance"]), r["mtc_no"]) for r in rows),
			sorted((h.heat_number, flt(h.qty), mtc.certificate_no) for h in mtc.heats),
		)

	# ------------------------------------------------------------------ SMR-21
	def test_smr21_age_alert_before_limit(self):
		po = make_po()
		mtc = make_mtc(po, [("7A1234", 20)], issue_date=add_days(add_months(nowdate(), -24), 30))
		ts = make_tally(po, [("7A1234", "L1", 2, 10.0)])
		doc = make_smr(po, mtc, ts)
		doc = apply_workflow(doc.as_dict(), "Start Review")
		doc = decide(doc)
		frappe.get_doc("Purchase Receipt", smr_module.make_purchase_receipt(doc.name)).submit()
		make_user("pvfss.qm@example.com", "Quality Manager")
		self.assertEqual(mtc_age.age_alerts(), 1)
		self.assertEqual(str(frappe.db.get_value("MTC Heat", mtc.heats[0].name, "age_alerted_on")), nowdate())
		self.assertEqual(mtc_age.age_alerts(), 0)  # once per heat
		self.assertTrue(
			frappe.db.exists(
				"Notification Log",
				{"for_user": "pvfss.qm@example.com", "subject": ["like", "%reaches its 24-month limit%"]},
			)
		)
