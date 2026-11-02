"""HSE alerts (HSE-02, HSE-10, HSE-31, SCR-HSE-17)."""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, formatdate, getdate, now_datetime, nowdate

from pvfss.pvfss_hse.doctype.hse_training_record.hse_training_record import training_status
from pvfss.utils import alerts, settings

INVESTIGATION_HOURS = 48


def _hse(*extra):
	return alerts.users_with_role("HSE User", "HSE Manager") + list(extra)


def training_expiry():
	"""Training certificates expiring within N days (once per record); statuses refreshed."""
	days = settings.get_int("hse_expiry_alert_days", 30)
	sent = 0
	for row in frappe.get_all(
		"HSE Training Record",
		filters={"expiry_date": ["is", "set"]},
		fields=["name", "employee_name", "course", "expiry_date", "status", "alerted_on"],
	):
		status = training_status(row.expiry_date)
		if status != row.status:
			frappe.db.set_value("HSE Training Record", row.name, "status", status, update_modified=False)
		if not row.alerted_on and getdate(row.expiry_date) <= getdate(add_days(nowdate(), days)):
			alerts.send(
				_hse(),
				_("{0}: {1} expires on {2}.").format(row.employee_name, row.course, formatdate(row.expiry_date)),
				"HSE Training Record",
				row.name,
			)
			frappe.db.set_value("HSE Training Record", row.name, "alerted_on", nowdate(), update_modified=False)
			sent += 1
	return sent


def permit_expiry():
	"""Issued permits past their validity become Expired; permits ending within the alert window are flagged once."""
	now = now_datetime()
	sent = 0
	for row in frappe.get_all(
		"Permit to Work",
		filters={"docstatus": 1, "status": "Issued"},
		fields=["name", "permit_type", "location", "valid_to", "alerted_on", "owner"],
	):
		if row.valid_to <= now:
			frappe.db.set_value("Permit to Work", row.name, "status", "Expired", update_modified=False)
			alerts.send(
				_hse(row.owner), _("Permit {0} ({1}, {2}) has expired and is not closed.").format(row.name, _(row.permit_type), row.location),
				"Permit to Work", row.name,
			)
			sent += 1
		elif not row.alerted_on and row.valid_to <= add_to_date(now, hours=4):
			alerts.send(
				_hse(row.owner), _("Permit {0} ({1}) expires at {2}.").format(row.name, row.location, frappe.utils.format_datetime(row.valid_to)),
				"Permit to Work", row.name,
			)
			frappe.db.set_value("Permit to Work", row.name, "alerted_on", nowdate(), update_modified=False)
			sent += 1
	return sent


def capa_overdue():
	sent = 0
	for row in frappe.get_all(
		"CAPA",
		filters={
			"status": ["in", ("Open", "In progress", "Overdue")],
			"due_date": ["<", nowdate()],
			"overdue_alerted_on": ["is", "not set"],
		},
		fields=["name", "description", "action_owner", "due_date"],
	):
		frappe.db.set_value(
			"CAPA", row.name, {"status": "Overdue", "overdue_alerted_on": nowdate()}, update_modified=False
		)
		alerts.send(
			[row.action_owner, *alerts.users_with_role("HSE Manager")],
			_("CAPA {0} was due on {1}: {2}").format(row.name, formatdate(row.due_date), row.description),
			"CAPA",
			row.name,
		)
		sent += 1
	return sent


def investigation_overdue():
	"""Hourly: incident still Reported 48 hours after it was reported -> HSE Manager."""
	cutoff = add_to_date(now_datetime(), hours=-INVESTIGATION_HOURS)
	rows = frappe.get_all(
		"HSE Incident",
		filters={
			"workflow_state": "Reported",
			"reported_on": ["<=", cutoff],
			"investigation_alerted_on": ["is", "not set"],
		},
		fields=["name", "incident_type", "location"],
	)
	for row in rows:
		alerts.send(
			alerts.users_with_role("HSE Manager"),
			_("{0} ({1}, {2}) is not under investigation after 48 hours.").format(row.name, _(row.incident_type), row.location),
			"HSE Incident",
			row.name,
		)
		frappe.db.set_value("HSE Incident", row.name, "investigation_alerted_on", now_datetime(), update_modified=False)
	return len(rows)


def risk_review():
	sent = 0
	for doctype, owner_field, title in (
		("HSE Risk Register", "risk_owner", "hazard"),
		("Legal Register", "responsible", "law"),
	):
		for row in frappe.get_all(
			doctype,
			filters={"review_date": ["<=", nowdate()], "review_alerted_on": ["is", "not set"]},
			fields=["name", owner_field, title, "review_date"],
		):
			alerts.send(
				[row.get(owner_field), *alerts.users_with_role("HSE Manager")],
				_("{0} {1} is due for review ({2}).").format(_(doctype), row.get(title), formatdate(row.review_date)),
				doctype,
				row.name,
			)
			frappe.db.set_value(doctype, row.name, "review_alerted_on", nowdate(), update_modified=False)
			sent += 1
	return sent
