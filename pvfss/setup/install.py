"""Install and migrate hooks for the pvfss app.

Everything here is idempotent: it only fills values that are still empty, so re-running
``bench migrate`` never overwrites what Quantum-Electro or PVFSS changed on the site.
"""

import frappe
from frappe.utils import cint

from pvfss.setup import branding, defaults, masters


def after_install():
	apply_settings_defaults()
	apply_security_defaults()
	apply_operating_defaults()
	masters.seed_global()
	branding.apply()


def after_migrate():
	apply_settings_defaults()
	masters.seed_global()
	branding.apply()


def before_tests():
	"""Prepare a fresh test site: setup wizard (company), PVFSS defaults and masters."""
	from pvfss.tests.factories import ensure_test_company

	apply_settings_defaults()
	ensure_test_company()
	apply_operating_defaults()  # after the setup wizard, which resets Buying Settings
	frappe.db.commit()


# --------------------------------------------------------------------------- PVFSS Settings
def apply_settings_defaults():
	settings = frappe.get_single("PVFSS Settings")
	changed = False

	for table, rows in defaults.SETTINGS_TABLES.items():
		if settings.get(table):
			continue
		for row in rows:
			row = dict(row)
			# A template row may name a DocType that a later module adds (e.g. Technical Evaluation).
			if row.get("backed_by_doctype") and not frappe.db.exists("DocType", row["backed_by_doctype"]):
				row["backed_by_doctype"] = None
			settings.append(table, row)
		changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save()


# --------------------------------------------------------------------------- Security (GEN-63, NFR-04)
def apply_operating_defaults():
	"""ERPNext settings PVFSS relies on (PUR-12, FIN-20)."""
	for doctype, values in defaults.OPERATING_SETTINGS.items():
		meta = frappe.get_meta(doctype)
		for field, value in values.items():
			if meta.has_field(field):
				frappe.db.set_single_value(doctype, field, value)


def apply_security_defaults():
	"""2FA for all users, password policy and 8-hour session expiry.

	A local development site can opt out of 2FA with ``bench --site <site> set-config pvfss_skip_2fa 1``.
	"""
	ss = frappe.get_single("System Settings")
	values = dict(defaults.SYSTEM_SETTINGS)
	if cint(frappe.conf.get("pvfss_skip_2fa")):
		values.pop("enable_two_factor_auth", None)
	for field, value in values.items():
		ss.set(field, value)
	ss.flags.ignore_permissions = True
	ss.flags.ignore_mandatory = True
	ss.save()
