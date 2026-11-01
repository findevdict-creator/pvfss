"""Cached accessor for PVFSS Settings (GEN-06, NFR-10).

Business rules never hard-code a threshold. They read it through this module:

    from pvfss.utils import settings
    margin = settings.get_value("min_target_margin_pct")

The single document is served from Frappe's document cache, which Frappe clears
whenever PVFSS Settings is saved, so a change takes effect on the next request.
"""

import frappe
from frappe.utils import cint, flt

DOCTYPE = "PVFSS Settings"


def get():
	"""Return the cached PVFSS Settings document (read-only use)."""
	return frappe.get_cached_doc(DOCTYPE)


def get_value(fieldname, default=None):
	value = get().get(fieldname)
	if value in (None, "") and default is not None:
		return default
	return value


def get_int(fieldname, default=0):
	return cint(get_value(fieldname, default))


def get_float(fieldname, default=0.0):
	return flt(get_value(fieldname, default))


def get_flag(fieldname):
	return bool(cint(get().get(fieldname)))


def get_alert_days(table_fieldname):
	"""Return the distinct day thresholds of an alert table, largest first (e.g. [30, 15, 7])."""
	return sorted({cint(row.days_before) for row in get().get(table_fieldname) or []}, reverse=True)


def get_table(table_fieldname, **filters):
	"""Return template rows from a settings table, optionally filtered on field values."""
	rows = get().get(table_fieldname) or []
	return [row for row in rows if all(row.get(k) == v for k, v in filters.items())]


def clear_cache():
	frappe.clear_document_cache(DOCTYPE, DOCTYPE)
