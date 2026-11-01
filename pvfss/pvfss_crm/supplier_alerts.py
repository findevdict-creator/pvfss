"""Supplier document expiry alert (SUP-04, SCR-SUP-08)."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from pvfss.utils import alerts, settings


def document_expiry(today=None):
	"""To Pre-Bidding Managers N days before a supplier document expires (PVFSS Settings)."""
	today = getdate(today or nowdate())
	days = settings.get_int("supplier_doc_expiry_alert_days", 30)
	target = add_days(today, days)
	managers = alerts.users_with_role("Pre-Bidding Manager")
	rows = frappe.get_all(
		"Supplier Document",
		filters={"parenttype": "Supplier", "expiry_date": target},
		fields=["parent", "document_type", "expiry_date"],
	)
	for row in rows:
		subject = _("{0} for {1} expires on {2} ({3} days).").format(
			_(row.document_type), row.parent, frappe.utils.formatdate(row.expiry_date), days
		)
		alerts.send(managers, subject, "Supplier", row.parent)
	return len(rows)
