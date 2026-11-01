"""Historical data import support (IMP-01).

Rules that would block historical data (PUR-04, QA-33, DSP-02 and other gates) are
skipped only while a PVFSS import is running, and every skipped check is written to
Import Exception Log for review.

A PVFSS import is either:

* code that runs inside ``with pvfss_import():`` (custom importers, seed and load scripts), or
* a standard Data Import whose "Historical load" box (``pvfss_skip_rules``) is ticked.
"""

from contextlib import contextmanager

import frappe
from frappe.utils import cint


@contextmanager
def pvfss_import(data_import=None):
	previous = (frappe.flags.pvfss_import, frappe.flags.pvfss_data_import)
	frappe.flags.pvfss_import = True
	frappe.flags.pvfss_data_import = data_import
	try:
		yield
	finally:
		frappe.flags.pvfss_import, frappe.flags.pvfss_data_import = previous


def get_data_import(doc=None):
	"""Name of the Data Import that is loading ``doc``, if any."""
	if frappe.flags.pvfss_data_import:
		return frappe.flags.pvfss_data_import
	ref = doc and doc.flags.get("updater_reference")
	if ref and ref.get("doctype") == "Data Import":
		return ref.get("docname")
	return None


def is_import(doc=None):
	"""True when PVFSS rules must log instead of block for ``doc``."""
	if frappe.flags.pvfss_import:
		return True
	if not frappe.flags.in_import:
		return False
	data_import = get_data_import(doc)
	if not data_import:
		return False
	return bool(cint(frappe.db.get_value("Data Import", data_import, "pvfss_skip_rules")))


def log_exception(doc=None, rule=None, message=None, gate=None):
	"""Record one skipped rule in Import Exception Log and return the log name."""
	log = frappe.get_doc(
		{
			"doctype": "Import Exception Log",
			"data_import": get_data_import(doc),
			"reference_doctype": doc.doctype if doc else None,
			"reference_name": doc.name if doc and not doc.is_new() else None,
			"rule": rule,
			"gate": gate,
			"message": message,
		}
	)
	log.flags.ignore_permissions = True
	log.flags.ignore_links = bool(doc and doc.is_new())
	log.insert()
	return log.name
