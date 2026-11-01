"""Step 03 tests: branding and print styling (GEN-08, GEN-62)."""

import os

import frappe
from frappe.tests import IntegrationTestCase

from pvfss.setup import branding


class TestBranding(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		branding.apply()

	def test_GEN_08_product_name_is_not_erpnext(self):
		self.assertEqual(frappe.db.get_single_value("System Settings", "app_name"), branding.PRODUCT_NAME)
		self.assertEqual(frappe.get_hooks("app_title", app_name="pvfss")[0], "PVFSS ERP")

	def test_GEN_08_theme_assets_exist(self):
		for rel in ("public/css/pvfss_theme.css", "public/css/pvfss_web.css", "public/images/logo.svg"):
			self.assertTrue(os.path.exists(frappe.get_app_path("pvfss", rel)), rel)
		self.assertIn("/assets/pvfss/css/pvfss_theme.css", frappe.get_hooks("app_include_css"))

	def test_GEN_08_dark_theme_tokens_present(self):
		css = frappe.read_file(frappe.get_app_path("pvfss", "public", "css", "pvfss_theme.css"))
		self.assertIn('[data-theme="dark"]', css)
		self.assertIn("--desk-sidebar-bg", css)

	def test_GEN_62_letter_head_and_print_style(self):
		self.assertTrue(frappe.db.exists("Letter Head", branding.LETTER_HEAD))
		self.assertTrue(frappe.db.get_value("Letter Head", branding.LETTER_HEAD, "is_default"))
		self.assertTrue(frappe.db.exists("Print Style", branding.PRINT_STYLE))

	def test_GEN_62_letter_head_renders(self):
		html = frappe.render_template(
			frappe.db.get_value("Letter Head", branding.LETTER_HEAD, "content"), {"doc": None}
		)
		self.assertIn("pvfss-letterhead", html)

	def test_branding_keeps_manual_changes(self):
		frappe.db.set_single_value("Website Settings", "copyright", "Custom by PVFSS")
		branding.apply()
		self.assertEqual(frappe.db.get_single_value("Website Settings", "copyright"), "Custom by PVFSS")
		frappe.db.rollback()
