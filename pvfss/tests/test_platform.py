"""Platform tests for step 01 (GEN-06, GEN-20, GEN-30, GEN-60, GEN-63, IMP-01, gate framework).

Test names carry the requirement ID they prove (GEN-07).
"""

import frappe
from frappe.tests import IntegrationTestCase

from pvfss.gates.base import GateFailedError, GateResult
from pvfss.hooks import PVFSS_ROLES
from pvfss.utils import settings
from pvfss.utils.importing import is_import, pvfss_import


def _settings_value(fieldname, value):
	doc = frappe.get_single("PVFSS Settings")
	doc.set(fieldname, value)
	doc.save()
	return doc


class TestPVFSSSettings(IntegrationTestCase):
	def tearDown(self):
		# Each test edits the single; undo so the next test sees the install defaults.
		frappe.db.rollback()
		settings.clear_cache()

	def test_GEN_30_defaults_seeded_on_install(self):
		doc = frappe.get_single("PVFSS Settings")
		self.assertEqual(doc.min_target_margin_pct, 10)
		self.assertEqual(doc.inquiry_due_alert_days, 2)
		self.assertEqual(doc.qa02_mode, "Block")
		self.assertFalse(doc.allow_dispatch_without_irn)
		self.assertEqual([r.days_before for r in doc.lc_expiry_alert_days], [30, 15, 7])
		self.assertEqual([r.days_before for r in doc.icv_expiry_alert_days], [90, 30])
		self.assertTrue(doc.handover_item_template)
		self.assertTrue(doc.po_review_template)
		self.assertTrue(doc.dispatch_document_template)
		self.assertTrue(doc.expediting_milestone_template)
		self.assertTrue(doc.project_closure_template)

	def test_GEN_06_accessor_reads_saved_value_without_restart(self):
		before = settings.get_int("expediting_delay_alert_days")
		_settings_value("expediting_delay_alert_days", before + 3)
		self.assertEqual(settings.get_int("expediting_delay_alert_days"), before + 3)

	def test_GEN_06_alert_days_largest_first_and_unique(self):
		doc = frappe.get_single("PVFSS Settings")
		doc.set("lc_expiry_alert_days", [{"days_before": 7}, {"days_before": 30}, {"days_before": 7}])
		doc.save()
		self.assertEqual(settings.get_alert_days("lc_expiry_alert_days"), [30, 7])

	def test_GEN_30_rejects_negative_day_count(self):
		doc = frappe.get_single("PVFSS Settings")
		doc.pdc_maturity_alert_days = -1
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_SUP_05_evaluation_weights_must_total_100(self):
		doc = frappe.get_single("PVFSS Settings")
		doc.set("supplier_evaluation_criteria", [{"criterion": "Price", "weight_pct": 60}])
		self.assertRaises(frappe.ValidationError, doc.save)

		doc = frappe.get_single("PVFSS Settings")
		doc.set(
			"supplier_evaluation_criteria",
			[{"criterion": "Price", "weight_pct": 60}, {"criterion": "Quality", "weight_pct": 40}],
		)
		doc.save()
		self.assertEqual(len(settings.get().supplier_evaluation_criteria), 2)

	def test_get_table_filters_rows(self):
		rows = settings.get_table("expediting_milestone_template", supply_route="Manufacturing")
		self.assertTrue(rows)
		self.assertTrue(all(r.supply_route == "Manufacturing" for r in rows))


class TestGateFramework(IntegrationTestCase):
	def _doc(self):
		return frappe.get_doc({"doctype": "ToDo", "description": "pvfss gate test"}).insert()

	def test_GATE_collects_every_failure_before_throwing(self):
		result = GateResult("Test gate failed", gate="GT")
		result.check(False, "first condition", rule="R-1")
		result.check(True, "passing condition", rule="R-2")
		result.check(False, "second condition", doctype="ToDo", name=self._doc().name, rule="R-3")

		self.assertEqual(len(result.failures), 2)
		self.assertEqual(len(result.passes), 1)
		with self.assertRaises(GateFailedError) as ctx:
			result.throw_if_failed()
		message = str(ctx.exception)
		self.assertIn("first condition", message)
		self.assertIn("second condition", message)

	def test_GATE_passes_silently_when_ok(self):
		result = GateResult("Test gate failed")
		result.check(True, "fine")
		result.throw_if_failed()  # no exception
		self.assertTrue(result.as_dict()["ok"])

	def test_GATE_escapes_user_text(self):
		result = GateResult("Test gate failed")
		result.fail("<script>alert(1)</script>")
		self.assertNotIn("<script>", result.as_html())

	def test_GATE_warn_only_does_not_block(self):
		result = GateResult("Test gate warning")
		result.fail("soft rule")
		result.throw_if_failed(warn_only=True)

	def test_GATE_as_dict_links_failing_record(self):
		name = self._doc().name
		payload = GateResult("Test").fail("needs fixing", doctype="ToDo", name=name).as_dict()
		self.assertFalse(payload["ok"])
		self.assertIn(name, payload["failures"][0]["url"])


class TestImportExceptions(IntegrationTestCase):
	def test_IMP_01_rules_enforced_outside_import(self):
		self.assertFalse(is_import())
		result = GateResult("Import gate failed", gate="G3").fail("PO line not compliant", rule="PUR-04")
		self.assertRaises(GateFailedError, result.throw_if_failed)

	def test_IMP_01_import_logs_instead_of_blocking(self):
		doc = frappe.get_doc({"doctype": "ToDo", "description": "historical"}).insert()
		before = frappe.db.count("Import Exception Log")
		with pvfss_import():
			self.assertTrue(is_import(doc))
			result = GateResult("Dispatch gate failed", doc=doc, gate="G7")
			result.fail("Batch B-1 has no IRN", rule="DSP-02")
			result.fail("Batch B-2 has no IRN", rule="DSP-02")
			result.throw_if_failed()  # must not raise
		self.assertFalse(is_import(doc))
		self.assertEqual(frappe.db.count("Import Exception Log"), before + 2)

		log = frappe.get_last_doc("Import Exception Log")
		self.assertEqual(log.rule, "DSP-02")
		self.assertEqual(log.gate, "G7")
		self.assertEqual(log.reference_doctype, "ToDo")
		self.assertEqual(log.reference_name, doc.name)
		self.assertFalse(log.reviewed)

	def test_IMP_01_data_import_flag_respected(self):
		doc = frappe.get_doc({"doctype": "ToDo", "description": "via data import"})
		doc.flags.updater_reference = {"doctype": "Data Import", "docname": "does-not-exist"}
		frappe.flags.in_import = True
		try:
			self.assertFalse(is_import(doc))  # box not ticked / unknown import
		finally:
			frappe.flags.in_import = False

	def test_IMP_01_log_only_review_fields_editable(self):
		with pvfss_import():
			GateResult("x", gate="G5").fail("skipped", rule="QA-33").throw_if_failed()
		log = frappe.get_last_doc("Import Exception Log")
		log.reviewed = 1
		log.remark = "Accepted: historical delivery"
		log.save()
		self.assertEqual(log.reviewed_by, frappe.session.user)
		self.assertIsNotNone(log.reviewed_on)

		log.rule = "changed"
		self.assertRaises(frappe.ValidationError, log.save)


class TestRolesAndAudit(IntegrationTestCase):
	def test_GEN_20_roles_exist(self):
		for role in PVFSS_ROLES:
			self.assertTrue(frappe.db.exists("Role", role), role)

	def test_GEN_60_track_changes_on_standard_doctypes(self):
		for dt in (
			"Opportunity",
			"Quotation",
			"Sales Order",
			"Purchase Order",
			"Delivery Note",
			"Sales Invoice",
			"Purchase Invoice",
			"Payment Entry",
			"Journal Entry",
		):
			self.assertTrue(frappe.get_meta(dt).track_changes, dt)

	def test_GEN_60_track_changes_on_custom_doctypes(self):
		for dt in frappe.get_all(
			"DocType", filters={"module": ["like", "PVFSS%"], "istable": 0}, pluck="name"
		):
			self.assertTrue(frappe.get_meta(dt).track_changes, dt)

	def test_GEN_03_custom_fields_prefixed(self):
		for fieldname in frappe.get_all(
			"Custom Field", filters={"module": ["like", "PVFSS%"]}, pluck="fieldname"
		):
			self.assertTrue(fieldname.startswith("pvfss_"), fieldname)

	def test_NFR_04_short_password_rejected(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "pvfss-pw-test@example.com",
				"first_name": "PW",
				"new_password": "short",
				"send_welcome_email": 0,
			}
		)
		self.assertRaises(frappe.ValidationError, user.insert)
