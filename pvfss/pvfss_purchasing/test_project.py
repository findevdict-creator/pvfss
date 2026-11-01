"""Module 6 tests (PRJ-01 to PRJ-40, G4). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.model.workflow import WorkflowPermissionError, WorkflowTransitionError
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from pvfss.gates.base import GateFailedError
from pvfss.pvfss_crm.test_quotation import make_user
from pvfss.pvfss_purchasing import project as project_module
from pvfss.pvfss_purchasing import supplier_po
from pvfss.pvfss_purchasing.doctype.project_handover.project_handover import make_handover
from pvfss.pvfss_purchasing.report.project_cost_sheet import project_cost_sheet
from pvfss.pvfss_purchasing.test_purchasing import won_customer_po
from pvfss.tests import factories as f
from pvfss.utils import settings

WF_ERRORS = (WorkflowPermissionError, WorkflowTransitionError)
MANUAL_ROWS = ("Handover Checklist", "Inspection and quality requirements")


def ready_handover(delivery_days=60):
	so = won_customer_po({"_PVFSS PRJ Supplier A": [100, 50]}, delivery_days=delivery_days)
	po = f.submit_purchase_order(frappe.get_doc("Purchase Order", supplier_po.make_supplier_pos(so.name)[0]))
	handover = frappe.get_doc("Project Handover", make_handover(so.name))
	return so, po, handover


def receive_manual_rows(handover):
	for row in handover.items:
		if row.item in MANUAL_ROWS:
			row.status = "Received"
			row.remark = "Checked in test"
	handover.save()
	return handover


def accepted_project(**kw):
	so, po, handover = ready_handover(**kw)
	handover = receive_manual_rows(handover)
	handover = f.walk_workflow(handover, "Submit Handover", "Accept")
	return so, po, handover, frappe.get_doc("Project", handover.project)


class TestProject(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	# ------------------------------------------------------------------ PRJ-01 / PRJ-02
	def test_prj01_handover_pulls_customer_po(self):
		so, po, handover = ready_handover()
		self.assertEqual(handover.customer, so.customer)
		self.assertEqual(handover.po_no, so.po_no)
		self.assertEqual(handover.inquiry, so.pvfss_inquiry)
		self.assertEqual([r.purchase_order for r in handover.supplier_pos], [po.name])
		self.assertEqual(make_handover(so.name), handover.name)  # one per Customer PO

	def test_prj02_template_rows_and_system_ticks(self):
		_so, _po, handover = ready_handover()
		status = {r.item: r.status for r in handover.items}
		self.assertEqual(len(handover.items), len(settings.get_table("handover_item_template")))
		for item in (
			"Customer PO",
			"Supplier PO",
			"Original inquiry folder",
			"Commercial offer",
			"Supplier quotations and comparison",
			"Technical evaluation",
		):
			self.assertEqual(status[item], "Received", item)
		for item in MANUAL_ROWS:
			self.assertEqual(status[item], "Outstanding", item)
		self.assertEqual(handover.outstanding_count, 2)

	# ------------------------------------------------------------------ PRJ-03 / G4
	def test_prj03_g4_blocks_outstanding_mandatory_rows(self):
		_so, _po, handover = ready_handover()
		with self.assertRaises(GateFailedError) as ctx:
			f.walk_workflow(handover, "Submit Handover")
		self.assertIn("Handover Checklist", str(ctx.exception))
		self.assertIn("Inspection and quality requirements", str(ctx.exception))

	def test_prj03_not_applicable_rows_do_not_block(self):
		_so, _po, handover = ready_handover()
		for row in handover.items:
			if row.item in MANUAL_ROWS:
				row.applicable = 0
		handover.save()
		self.assertEqual(handover.outstanding_count, 0)
		handover = f.walk_workflow(handover, "Submit Handover")
		self.assertEqual(handover.workflow_state, "Pending Acceptance")

	def test_prj03_return_needs_reason_and_logs_it(self):
		_so, _po, handover = ready_handover()
		handover = f.walk_workflow(receive_manual_rows(handover), "Submit Handover")
		with self.assertRaises(frappe.ValidationError):
			f.walk_workflow(handover, "Return")
		handover.return_reason = "ITP missing"
		handover.save()
		handover = f.walk_workflow(handover, "Return")
		self.assertEqual(handover.workflow_state, "Returned")
		self.assertEqual([(r.reason, r.resolved) for r in handover.returns], [("ITP missing", 0)])
		handover = f.walk_workflow(handover, "Submit Handover")
		self.assertEqual(handover.returns[0].resolved, 1)

	def test_prj03_only_post_bidding_manager_accepts(self):
		_so, _po, handover = ready_handover()
		handover = f.walk_workflow(receive_manual_rows(handover), "Submit Handover")
		frappe.set_user(make_user("pvfss.pbm9@example.com", "Pre-Bidding Manager"))
		with self.assertRaises(WF_ERRORS):
			f.walk_workflow(handover, "Accept")

	def test_prj03_direct_submit_blocked(self):
		_so, _po, handover = ready_handover()
		handover = receive_manual_rows(handover)
		with self.assertRaises(GateFailedError):
			handover.submit()

	# ------------------------------------------------------------------ PRJ-04 / PRJ-05 / PRJ-10 / DMS-01
	def test_prj04_acceptance_creates_project(self):
		so, po, handover, project = accepted_project()
		self.assertEqual(project.sales_order, so.name)
		self.assertEqual(project.customer, so.customer)
		self.assertEqual(project.pvfss_handover, handover.name)
		self.assertEqual(project.pvfss_customer_po_no, so.po_no)
		self.assertEqual(getdate(project.pvfss_customer_delivery_date), getdate(so.delivery_date))
		self.assertEqual(frappe.db.get_value("Sales Order", so.name, "project"), project.name)
		self.assertEqual(frappe.db.get_value("Purchase Order", po.name, "project"), project.name)
		self.assertEqual([r.purchase_order for r in project.pvfss_supply_routes], [po.name])
		self.assertEqual(
			len(project.pvfss_closure_items), len(settings.get_table("project_closure_template"))
		)
		self.assertTrue(
			frappe.db.exists("Expediting Log", {"purchase_order": po.name, "project": project.name})
		)
		root = frappe.db.get_value("File", {"is_folder": 1, "file_name": f"{project.name} - {so.po_no}"})
		self.assertTrue(root)
		self.assertEqual(frappe.db.count("File", {"folder": root, "is_folder": 1}), 8)

	def test_prj05_technical_requirements_from_so_lines(self):
		_so, _po, _handover, project = accepted_project()
		materials = [r for r in project.pvfss_technical_requirements if r.category == "Material"]
		self.assertEqual([r.applies_to_lines for r in materials], ["1", "2"])
		self.assertIn("Spec line 1", materials[0].requirement)

	# ------------------------------------------------------------------ PRJ-20 / PRJ-21
	def test_prj20_milestones_from_template(self):
		_so, po, _handover, _project = accepted_project()
		log = frappe.get_doc("Expediting Log", {"purchase_order": po.name})
		self.assertEqual(log.supply_route, "Manufacturing")
		self.assertEqual(len(log.milestones), len(project_module.milestone_template("Manufacturing")))
		ready = next(r for r in log.milestones if r.milestone == "Ready for dispatch")
		self.assertEqual(getdate(ready.committed_date), getdate(po.schedule_date))
		log.supply_route = "Ready stock (SMR)"
		log.save()
		self.assertEqual(log.milestones[0].milestone, "Inspection")

	def test_prj21_forecast_after_committed_flags_risk(self):
		so, po, _handover, project = accepted_project()
		log = frappe.get_doc("Expediting Log", {"purchase_order": po.name})
		ready = next(r for r in log.milestones if r.milestone == "Ready for dispatch")
		ready.forecast_date = add_days(so.delivery_date, 10)
		log.save()
		self.assertEqual(ready.status, "At risk")
		self.assertEqual(log.status, "At risk")
		project.reload()
		self.assertEqual(project.pvfss_delivery_at_risk, 1)
		self.assertIn(po.name, project.pvfss_risk_reason)
		self.assertIn("1 at risk", project.pvfss_status_summary)

	def test_prj21_late_and_alert_once(self):
		_so, po, _handover, project = accepted_project()
		log = frappe.get_doc("Expediting Log", {"purchase_order": po.name})
		log.milestones[0].committed_date = add_days(nowdate(), -3)
		log.milestones[0].forecast_date = None
		log.save()
		self.assertEqual(log.status, "Late")
		sent = []
		original = project_module.alerts.send
		project_module.alerts.send = lambda *a, **k: sent.append(a)
		try:
			project_module.delay_alerts()
			log.reload()
			self.assertEqual(getdate(log.milestones[0].alerted_on), getdate(nowdate()))
			count = len(sent)
			self.assertGreaterEqual(count, 1)
			project_module.delay_alerts()  # once per milestone
			self.assertEqual(len(sent), count)
		finally:
			project_module.alerts.send = original
		self.assertTrue(project.pvfss_post_bidding_owner)

	def test_prj21_complete_when_all_actual(self):
		_so, po, _handover, _project = accepted_project()
		log = frappe.get_doc("Expediting Log", {"purchase_order": po.name})
		for row in log.milestones:
			row.actual_date = nowdate()
		log.save()
		self.assertEqual(log.status, "Complete")
		self.assertIsNone(log.next_milestone)

	# ------------------------------------------------------------------ PRJ-30
	def test_prj30_po_amendment_creates_change(self):
		_so, po, _handover, project = accepted_project()
		po = f.walk_workflow(frappe.get_doc("Purchase Order", po.name), "Cancel")
		amended = frappe.copy_doc(po)
		amended.amended_from = po.name
		amended.docstatus = 0
		amended.workflow_state = "Draft"
		amended.pvfss_amendment_reason = "Customer added quantity"
		amended.items[0].qty = flt(amended.items[0].qty) * 2  # cost goes up
		amended.insert()
		change = frappe.get_doc("Project Change", {"project": project.name, "auto_created": 1})
		self.assertEqual(change.description, "Customer added quantity")
		self.assertLess(change.margin_impact, 0)
		self.assertEqual(
			sorted(r.document_name for r in change.affected_documents), sorted([po.name, amended.name])
		)
		self.assertLess(change.margin_impact_pct, 0)

	def test_prj30_margin_reduction_needs_director(self):
		_so, _po, _handover, project = accepted_project()
		change = frappe.get_doc(
			{
				"doctype": "Project Change",
				"project": project.name,
				"change_type": "Price",
				"raised_by": "Supplier",
				"description": "Freight increase",
				"cost_impact": 500,
				"margin_impact": -500,
			}
		).insert()
		pom = make_user("pvfss.pom9@example.com", "Post-Bidding Manager")
		director = make_user("pvfss.dir9@example.com", "PVFSS Director")
		pou = make_user("pvfss.pou9@example.com", "Post-Bidding User")
		frappe.set_user(pom)
		with self.assertRaises(WF_ERRORS):
			f.walk_workflow(change, "Approve")
		change.reload()
		with self.assertRaises(frappe.ValidationError):
			change.submit()  # bypassing the workflow
		frappe.set_user(director)
		change = f.walk_workflow(frappe.get_doc("Project Change", change.name), "Approve")
		self.assertEqual(change.docstatus, 1)
		self.assertEqual(change.approved_by, "pvfss.dir9@example.com")
		frappe.set_user(pou)
		change = f.walk_workflow(change, "Implement")
		self.assertEqual(change.workflow_state, "Implemented")

	# ------------------------------------------------------------------ PRJ-31
	def test_prj31_cost_sheet_budget_and_committed(self):
		so, po, _handover, project = accepted_project()
		_columns, rows, _msg, _chart, summary = project_cost_sheet.execute({"project": project.name})
		material = next(r for r in rows if r["cost_type"] == "Material")
		self.assertAlmostEqual(material["committed"], flt(po.base_net_total), delta=0.01)
		self.assertGreater(material["budget"], 0)
		values = {s["label"]: s["value"] for s in summary}
		self.assertAlmostEqual(values["Customer PO value"], flt(so.base_net_total), delta=0.01)
		self.assertGreater(values["Budget margin"], 0)

	# ------------------------------------------------------------------ PRJ-40 / FIN-50 dates
	def test_prj40_completed_blocked_until_closure_done(self):
		_so, _po, _handover, project = accepted_project()
		project.status = "Completed"
		with self.assertRaises(frappe.ValidationError) as ctx:
			project.save()
		self.assertIn("All lines delivered", str(ctx.exception))
		project.reload()
		for row in project.pvfss_closure_items[1:]:
			row.done = 1
		project.save()
		director = make_user("pvfss.dir8@example.com", "PVFSS Director")
		frappe.set_user(make_user("pvfss.pom8@example.com", "Post-Bidding Manager"))
		project.reload()
		project.pvfss_closure_items[0].waived = 1
		project.pvfss_closure_items[0].waiver_reason = "Customer short-closed"
		with self.assertRaises(frappe.PermissionError):
			project.save()
		frappe.set_user(director)
		project.reload()
		project.pvfss_closure_items[0].waived = 1
		project.pvfss_closure_items[0].waiver_reason = "Customer short-closed"
		project.status = "Completed"
		project.save()
		self.assertEqual(project.pvfss_closure_items[0].by_user, "pvfss.dir8@example.com")

	def test_fin50_warranty_and_retention_dates(self):
		_so, _po, _handover, project = accepted_project()
		project.pvfss_warranty_months = 12
		project.pvfss_retention_pct = 10
		project.pvfss_final_acceptance_date = "2026-11-01"
		project.save()
		self.assertEqual(getdate(project.pvfss_warranty_end_date), getdate(add_months("2026-11-01", 12)))
		self.assertEqual(
			getdate(project.pvfss_retention_release_date), getdate(project.pvfss_warranty_end_date)
		)

	def test_prj11_dashboard_figures(self):
		_so, po, _handover, project = accepted_project()
		data = project_module.get_dashboard(project.name)
		self.assertEqual([r["purchase_order"] for r in data["purchase_orders"]], [po.name])
		self.assertEqual(data["purchase_orders"][0]["expediting_status"], "On track")
		self.assertEqual(data["closure_total"], len(project.pvfss_closure_items))
