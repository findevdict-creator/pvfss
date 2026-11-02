"""Module 12 tests (HSE-02 to HSE-41). Names carry the requirement ID (GEN-07)."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, add_to_date, get_first_day, now_datetime, nowdate

from pvfss.pvfss_hse import alerts, kpi
from pvfss.pvfss_hse.doctype.hse_incident import hse_incident as incident_module
from pvfss.pvfss_hse.doctype.permit_to_work import permit_to_work as ptw_module
from pvfss.pvfss_hse.report.hse_training_matrix import hse_training_matrix
from pvfss.tests import factories as f


def make_employee(name):
	if not frappe.db.exists("Gender", "Male"):
		frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert()
	return frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": name,
			"gender": "Male",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"company": f.TEST_COMPANY,
		}
	).insert()


def make_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}).insert()
	return email


class TestHSE(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ------------------------------------------------------------------ HSE-02
	def test_hse02_rating_from_matrix(self):
		risk = frappe.get_doc(
			{
				"doctype": "HSE Risk Register",
				"activity": "Yard - pipe stacking",
				"hazard": "Falling pipes",
				"aspect_type": "Safety",
				"likelihood": "4",
				"severity": "4",
				"residual_likelihood": "2",
				"residual_severity": "2",
				"risk_owner": "Administrator",
				"review_date": add_months(nowdate(), 6),
			}
		).insert()
		self.assertEqual((risk.risk_score, risk.rating), (16, "High"))
		self.assertEqual((risk.residual_score, risk.residual_rating), (4, "Low"))

		matrix = frappe.get_single("Risk Matrix")
		matrix.bands[0].to_score = 3  # leaves score 4 without a band
		self.assertRaises(frappe.ValidationError, matrix.save)

	# ------------------------------------------------------------------ HSE-30 / HSE-32
	def test_hse30_incident_investigation_capa_closure(self):
		name = incident_module.report_incident("Injury", "Yard", "Hand caught while slinging", people="A. Worker")
		doc = frappe.get_doc("HSE Incident", name)
		self.assertEqual((doc.workflow_state, doc.reported_by), ("Reported", "Administrator"))
		doc.lost_days = 2
		doc.save()
		doc = apply_workflow(doc.as_dict(), "Start Investigation")
		self.assertTrue(doc.is_lti)
		self.assertRaises(frappe.ValidationError, apply_workflow, doc.as_dict(), "Open Actions")

		doc = frappe.get_doc("HSE Incident", name)
		doc.root_cause = "No tag line used"
		doc.append("five_whys", {"answer": "Load swung"})
		doc.save()
		owner = make_user("_pvfss.capa.owner@example.com")
		capa = incident_module.make_capa(name, "Corrective", "Use tag lines on every lift", owner, add_days(nowdate(), 7))
		doc = apply_workflow(frappe.get_doc("HSE Incident", name).as_dict(), "Open Actions")
		self.assertEqual(doc.capas[0].capa, capa)
		with self.assertRaises(frappe.ValidationError) as ctx:
			apply_workflow(doc.as_dict(), "Close")
		self.assertIn(capa, str(ctx.exception))

		capa_doc = frappe.get_doc("CAPA", capa)
		capa_doc.update({"status": "Verified-Closed", "evidence_note": "Toolbox talk held", "verified_by": owner})
		self.assertRaises(frappe.ValidationError, capa_doc.save)  # owner cannot verify
		capa_doc.reload()
		capa_doc.update({"status": "Verified-Closed", "evidence_note": "Toolbox talk held", "verified_by": "Administrator"})
		capa_doc.save()
		doc = apply_workflow(frappe.get_doc("HSE Incident", name).as_dict(), "Close")
		self.assertEqual((doc.workflow_state, doc.capas[0].status), ("Closed", "Verified-Closed"))

	def test_hse31_incident_not_investigated_in_48_hours(self):
		name = incident_module.report_incident("Near miss", "Office", "Loose cable")
		frappe.db.set_value("HSE Incident", name, "reported_on", add_to_date(now_datetime(), hours=-50))
		self.assertEqual(alerts.investigation_overdue(), 1)
		self.assertEqual(alerts.investigation_overdue(), 0)

	# ------------------------------------------------------------------ HSE-10
	def test_hse10_permit_needs_precautions_and_safe_closure(self):
		ptw = frappe.get_doc(
			{
				"doctype": "Permit to Work",
				"permit_type": "Hot work",
				"location": "Yard bay 2",
				"work_description": "Cutting pipe ends",
				"valid_from": now_datetime(),
				"valid_to": add_to_date(now_datetime(), hours=8),
			}
		).insert()
		self.assertTrue(ptw.precautions)
		self.assertRaises(frappe.ValidationError, ptw.submit)
		ptw.reload()
		for row in ptw.precautions:
			row.confirmed = 1
		ptw.submit()
		self.assertEqual(ptw.status, "Issued")
		self.assertRaises(frappe.ValidationError, ptw_module.close, ptw.name)
		frappe.db.set_value("Permit to Work", ptw.name, "valid_to", add_to_date(now_datetime(), hours=-1))
		alerts.permit_expiry()
		self.assertEqual(frappe.db.get_value("Permit to Work", ptw.name, "status"), "Expired")
		frappe.db.set_value("Permit to Work", ptw.name, "area_safe", 1)
		self.assertEqual(ptw_module.close(ptw.name), "Closed")

	# ------------------------------------------------------------------ HSE-20
	def test_hse20_training_matrix_shows_expiring_and_missing(self):
		course = frappe.get_doc(
			{"doctype": "HSE Course", "course_name": "_PVFSS Forklift", "validity_months": 12, "required_for_all": 1}
		).insert()
		trained = make_employee("_PVFSS Trained")
		expired = make_employee("_PVFSS Lapsed")
		missing = make_employee("_PVFSS New")
		frappe.get_doc(
			{"doctype": "HSE Training Record", "employee": trained.name, "course": course.name, "training_date": add_days(add_months(nowdate(), -12), 10)}
		).insert()
		lapsed = frappe.get_doc(
			{"doctype": "HSE Training Record", "employee": expired.name, "course": course.name, "training_date": add_months(nowdate(), -14)}
		).insert()
		self.assertEqual(lapsed.status, "Expired")
		_cols, rows = hse_training_matrix.execute({"course": course.name})
		status = {r["employee"]: r.get("_pvfss_forklift_status") for r in rows}
		self.assertEqual(status[trained.name], "Expiring")
		self.assertEqual(status[expired.name], "Expired")
		self.assertEqual(status[missing.name], "Missing")
		self.assertGreaterEqual(alerts.training_expiry(), 2)

	# ------------------------------------------------------------------ HSE-41
	def test_hse41_ltifr_from_monthly_hours(self):
		frappe.get_doc({"doctype": "HSE Monthly Statistics", "month": nowdate(), "headcount": 60, "hours_worked": 100000}).insert()
		self.assertRaises(
			frappe.exceptions.DuplicateEntryError,
			frappe.get_doc({"doctype": "HSE Monthly Statistics", "month": add_days(get_first_day(nowdate()), 1), "hours_worked": 1}).insert,
		)
		name = incident_module.report_incident("Injury", "Yard", "Twisted ankle")
		frappe.db.set_value("HSE Incident", name, {"lost_days": 3, "is_lti": 1})
		incident_module.report_incident("Near miss", "Yard", "Dropped shackle")
		values = kpi.kpis(get_first_day(nowdate()), nowdate())
		self.assertEqual((values["lti_count"], values["near_misses"], values["ltifr"]), (1, 1, 10.0))
