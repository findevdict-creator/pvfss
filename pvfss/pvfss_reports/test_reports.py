"""Module 15 tests (RPT-01 to RPT-10). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from pvfss.pvfss_crm.report.win_loss_analysis import win_loss_analysis
from pvfss.pvfss_crm.test_crm import make_inquiry
from pvfss.pvfss_crm.test_quotation import make_user
from pvfss.pvfss_crm.test_rfq import make_rfq, make_sq
from pvfss.pvfss_quality import traceability
from pvfss.pvfss_quality.test_traceability import item, make_batch, make_po, mill, receive
from pvfss.pvfss_reports import actions, charts, kpi
from pvfss.pvfss_reports.report.management_kpi_summary import management_kpi_summary
from pvfss.pvfss_reports.report.supplier_performance import supplier_performance
from pvfss.setup import workspaces
from pvfss.tests import factories as f
from pvfss.utils import settings


def close_inquiry(name, stage, value, quoted_on=None):
	frappe.db.set_value(
		"Opportunity",
		name,
		{
			"pvfss_stage": stage,
			"pvfss_quoted_value": value,
			"pvfss_quoted_on": quoted_on or nowdate(),
			"pvfss_turnaround_days": 4,
		},
	)


class TestReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		settings.clear_cache()

	# ------------------------------------------------------------------ RPT-01
	def test_rpt01_workspaces_reference_existing_records(self):
		names = frappe.get_all("Workspace", filters={"module": "PVFSS Reports"}, pluck="name")
		self.assertEqual(len(names), 10)
		self.assertTrue(frappe.db.exists("Custom HTML Block", workspaces.ACTION_BLOCK))
		for name in names:
			ws = frappe.get_doc("Workspace", name)
			self.assertTrue(ws.roles, name)
			for row in ws.number_cards:
				self.assertTrue(frappe.db.exists("Number Card", row.number_card_name), row.number_card_name)
			for row in ws.charts:
				self.assertTrue(frappe.db.exists("Dashboard Chart", row.chart_name), row.chart_name)
			for row in ws.shortcuts:
				self.assertTrue(frappe.db.exists(row.type, row.link_to), f"{name}: {row.type} {row.link_to}")
			for row in ws.links:
				if row.type == "Link":
					self.assertTrue(frappe.db.exists(row.link_type, row.link_to), f"{name}: {row.link_to}")
			content = frappe.parse_json(ws.content)
			self.assertEqual(content[1]["data"]["custom_block_name"], ws.custom_blocks[0].label)
			labels = {r.label for r in ws.number_cards} | {r.label for r in ws.charts}
			for block in content:
				name = block["data"].get("number_card_name") or block["data"].get("chart_name")
				if name:
					self.assertIn(name, labels, f"{ws.name}: block {name}")

	def test_rpt01_users_land_on_their_team_workspace(self):
		qu = make_user("rpt.quality@pvfss.test", "Quality User")
		self.assertEqual(frappe.db.get_value("User", qu, "default_workspace"), "PVFSS Quality")
		user = frappe.get_doc("User", qu)
		user.add_roles("PVFSS Director")
		self.assertEqual(frappe.db.get_value("User", qu, "default_workspace"), "PVFSS Management")
		frappe.db.set_value("User", qu, "default_workspace", "Selling")  # the user's own choice
		user.reload()
		user.save()
		self.assertEqual(user.default_workspace, "Selling")

	def test_rpt01_every_card_and_chart_runs(self):
		for key in kpi.CARDS:
			result = kpi.card({"card": key})
			self.assertIn("value", result, key)
			self.assertIn("route", result, key)
		for key in charts.CHARTS:
			data = charts.get(filters=frappe.as_json({"chart": key}))
			self.assertEqual(len(data["labels"]), len(data["datasets"][0]["values"]), key)
		for name in frappe.get_all(
			"Number Card", filters={"module": "PVFSS Reports"}, fields=["filters_json"]
		):
			self.assertIn(frappe.parse_json(name.filters_json)["card"], kpi.CARDS)
		self.assertRaises(frappe.ValidationError, kpi.card, {"card": "nope"})
		self.assertEqual(set(charts.CHART_DOCTYPES), set(charts.CHARTS))

	def test_rpt01_icv_cards_read_the_active_certificate(self):
		from pvfss.pvfss_icv.test_icv import certificate

		certificate("ICV-RPT-1", nowdate(), score=38.5)
		self.assertEqual(kpi.card({"card": "icv_score"})["value"], 38.5)
		self.assertGreater(kpi.card({"card": "icv_days_left"})["value"], 300)

	def test_rpt01_figures_follow_permissions(self):
		hse = make_user("rpt.hseu@pvfss.test", "HSE User")
		frappe.set_user(hse)
		self.assertIn("value", kpi.card({"card": "hse_lti"}))
		self.assertRaises(frappe.PermissionError, kpi.card, {"card": "cash_position"})
		self.assertRaises(frappe.PermissionError, charts.get, filters={"chart": "revenue_by_month"})

	def test_rpt01_needs_your_action_strip(self):
		frappe.get_doc(
			{"doctype": "ToDo", "description": "Check MTC", "allocated_to": "Administrator", "status": "Open"}
		).insert()
		items = actions.get("pvfss-quality")
		todo = [i for i in items if i["route"] == ["List", "ToDo"]]
		self.assertTrue(todo and todo[0]["count"] >= 1)
		self.assertEqual(actions.workspace_name("Quality"), "PVFSS Quality")
		self.assertEqual(actions.workflow_items(()), [])

	def test_rpt01_strip_lists_workflow_states_for_the_role(self):
		incident = frappe.get_doc(
			{
				"doctype": "HSE Incident",
				"incident_type": "Near miss",
				"incident_datetime": frappe.utils.now_datetime(),
				"location": "Yard",
				"description": "Dropped load",
				"reported_by": "Administrator",
			}
		).insert()
		hsem = make_user("rpt.hsem@pvfss.test", "HSE Manager")
		frappe.set_user(hsem)
		items = actions.get("PVFSS HSE")
		state = frappe.db.get_value("HSE Incident", incident.name, "workflow_state")
		self.assertTrue(
			any(i["route_options"].get("workflow_state") == state and i["count"] >= 1 for i in items), items
		)

	# ------------------------------------------------------------------ RPT-02 / RPT-03
	def test_rpt02_pipeline_and_win_rate(self):
		before = kpi.pipeline_value()
		won, lost, quoted = (make_inquiry(f"RPT-{i}") for i in range(3))
		close_inquiry(won.name, "Won", 1000)
		close_inquiry(lost.name, "Lost", 3000)
		close_inquiry(quoted.name, "Quoted", 500)
		self.assertEqual(kpi.pipeline_value() - before, 500)
		rate = kpi.win_rate(add_days(nowdate(), -1))
		rows = frappe.get_all(
			"Opportunity",
			filters={
				"pvfss_stage": ["in", ("Won", "Lost")],
				"pvfss_quoted_on": [">=", add_days(nowdate(), -1)],
			},
			pluck="pvfss_stage",
		)
		self.assertAlmostEqual(rate, round(rows.count("Won") * 100 / len(rows), 1))

	def test_crm13_win_loss_by_contractor(self):
		customer = f.make_customer("_PVFSS RPT Contractor").name
		a, b, c = (make_inquiry(f"WL-{i}", customer=customer) for i in range(3))
		close_inquiry(a.name, "Won", 1000)
		close_inquiry(b.name, "Lost", 4000)
		close_inquiry(c.name, "Lost", 2000)
		_cols, data, _msg, chart, summary = win_loss_analysis.execute(
			{"party_name": customer, "group_by": "Contractor"}
		)
		row = data[0]
		self.assertEqual((row["group"], row["inquiries"], row["won"], row["lost"]), (customer, 3, 1, 2))
		self.assertEqual(
			(row["won_value"], row["lost_value"], row["win_rate"], row["turnaround"]), (1000, 6000, 33.3, 4)
		)
		self.assertEqual(summary[2]["value"], 33.3)
		self.assertEqual(chart["data"]["labels"], [customer])

	def test_rpt10_management_summary_and_weekly_email(self):
		_cols, data = management_kpi_summary.execute()
		self.assertEqual(len(data), len(management_kpi_summary.MANAGEMENT_CARDS))
		director = make_user("rpt.director@pvfss.test", "PVFSS Director")
		workspaces.setup_management_email()
		report = frappe.get_doc("Auto Email Report", {"report": workspaces.MANAGEMENT_EMAIL_REPORT})
		self.assertEqual((report.frequency, report.day_of_week, report.enabled), ("Weekly", "Sunday", 1))
		self.assertIn(director, report.email_to)

	# ------------------------------------------------------------------ RPT-07
	def test_rpt07_supplier_performance(self):
		frappe.db.set_value("Item", item(), "pvfss_irn_required", 0)
		heat = traceability.get_or_create_heat("RPT7", mill(), item(), grade="API 5L X52", mtc="MTC-RPT")
		po = make_po()
		pr = receive(po, make_batch(heat, "L1").name)
		pr.submit()
		rows = {r["supplier"]: r for r in supplier_performance.get_rows({"supplier": po.supplier})}
		row = rows[po.supplier]
		self.assertEqual((row["pos"] >= 1, row["lines_received"] >= 1), (True, True))
		self.assertEqual(row["on_time_pct"], 100)

		inquiry = make_inquiry("RPT-SQ")
		cheap, dear = f.make_supplier("_PVFSS RPT Cheap").name, f.make_supplier("_PVFSS RPT Dear").name
		rfq = make_rfq(inquiry.name, [cheap, dear])
		make_sq(rfq, cheap, [90])
		make_sq(rfq, dear, [120])
		rows = {r["supplier"]: r for r in supplier_performance.get_rows({})}
		self.assertEqual(rows[cheap]["lowest_share"], 100)
		self.assertEqual(rows[dear]["lowest_share"], 0)
		self.assertEqual((rows[cheap]["rfqs"], rows[cheap]["quotes"]), (1, 1))
		_cols, _data, _msg, _chart, summary = supplier_performance.execute({})
		self.assertEqual(len(summary), 4)
