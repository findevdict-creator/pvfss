"""Finance alert set (FIN-41, FIN-45, FIN-52, SCR-FIN-22). Daily jobs registered in pvfss/tasks.py."""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, formatdate, getdate, nowdate

from pvfss.utils import alerts, settings

LIVE_LC = ("Issued", "Amended", "Documents presented")


def _finance():
	return alerts.users_with_role("Finance User", "Finance Manager")


def lc_alerts():
	"""Expiry at 30 / 15 / 7 days, latest shipment vs open delivery dates, presentation deadline."""
	today = getdate(nowdate())
	levels = settings.get_alert_days("lc_expiry_alert_days")
	sent = 0
	for lc in frappe.get_all(
		"Letter of Credit",
		filters={"docstatus": 1, "status": ["in", LIVE_LC]},
		fields=[
			"name", "lc_no", "expiry_date", "latest_shipment_date", "presentation_deadline", "sales_order",
			"purchase_order", "expiry_alerts_sent", "shipment_alerted_on", "presentation_alerted_on",
		],
	):
		done = {int(x) for x in (lc.expiry_alerts_sent or "").split(",") if x.strip().isdigit()}
		days = date_diff(lc.expiry_date, today)
		due = [d for d in levels if days <= d and d not in done]
		if due and days >= 0:
			alerts.send(
				_finance(),
				_("LC {0} expires on {1} ({2} days).").format(lc.lc_no, formatdate(lc.expiry_date), days),
				"Letter of Credit",
				lc.name,
			)
			done.update(due)
			frappe.db.set_value(
				"Letter of Credit", lc.name, "expiry_alerts_sent", ",".join(str(d) for d in sorted(done, reverse=True)),
				update_modified=False,
			)
			sent += 1
		if lc.latest_shipment_date and not lc.shipment_alerted_on:
			late = shipment_conflicts(lc)
			if late:
				alerts.send(
					_finance(),
					_("LC {0}: latest shipment date {1} is before the planned delivery of {2}.").format(
						lc.lc_no, formatdate(lc.latest_shipment_date), ", ".join(late)
					),
					"Letter of Credit",
					lc.name,
				)
				frappe.db.set_value("Letter of Credit", lc.name, "shipment_alerted_on", today, update_modified=False)
				sent += 1
		window = settings.get_int("lc_presentation_alert_days", 5)
		if (
			lc.presentation_deadline
			and not lc.presentation_alerted_on
			and 0 <= date_diff(lc.presentation_deadline, today) <= window
		):
			alerts.send(
				_finance(),
				_("LC {0}: present the documents by {1}.").format(lc.lc_no, formatdate(lc.presentation_deadline)),
				"Letter of Credit",
				lc.name,
			)
			frappe.db.set_value("Letter of Credit", lc.name, "presentation_alerted_on", today, update_modified=False)
			sent += 1
	return sent


def shipment_conflicts(lc):
	"""Open Customer PO / Supplier PO lines planned after the LC's latest shipment date."""
	out = []
	if lc.sales_order:
		date = frappe.db.get_value("Sales Order", lc.sales_order, "delivery_date")
		if date and getdate(date) > getdate(lc.latest_shipment_date):
			out.append(lc.sales_order)
	if lc.purchase_order:
		date = frappe.db.get_value("Purchase Order", lc.purchase_order, "schedule_date")
		if date and getdate(date) > getdate(lc.latest_shipment_date):
			out.append(lc.purchase_order)
	return out


def pdc_alerts():
	"""PDCs maturing within N days."""
	days = settings.get_int("pdc_maturity_alert_days", 3)
	rows = frappe.get_all(
		"Post-Dated Cheque",
		filters={
			"docstatus": 1,
			"status": ["in", ("In hand", "Issued")],
			"cheque_date": ["<=", add_days(nowdate(), days)],
			"alerted_on": ["is", "not set"],
		},
		fields=["name", "cheque_no", "party", "cheque_date", "amount", "currency", "direction"],
	)
	for row in rows:
		alerts.send(
			_finance(),
			_("{0} cheque {1} ({2}, {3} {4}) is dated {5}.").format(
				_(row.direction), row.cheque_no, row.party, row.currency, row.amount, formatdate(row.cheque_date)
			),
			"Post-Dated Cheque",
			row.name,
		)
		frappe.db.set_value("Post-Dated Cheque", row.name, "alerted_on", nowdate(), update_modified=False)
	return len(rows)


def retention_alerts():
	"""Retention release due within N days (once), and overdue."""
	days = settings.get_int("retention_release_alert_days", 30)
	rows = frappe.get_all(
		"Retention",
		filters={
			"status": ["in", ("Held", "Release requested")],
			"release_due_date": ["<=", add_days(nowdate(), days)],
			"alerted_on": ["is", "not set"],
		},
		fields=["name", "party", "project", "amount", "currency", "release_due_date"],
	)
	for row in rows:
		overdue = getdate(row.release_due_date) < getdate(nowdate())
		subject = (
			_("Retention {0} ({1}) was due for release on {2}.")
			if overdue
			else _("Retention {0} ({1}) is due for release on {2}.")
		).format(row.name, row.party, formatdate(row.release_due_date))
		alerts.send(_finance(), subject, "Retention", row.name)
		frappe.db.set_value("Retention", row.name, "alerted_on", nowdate(), update_modified=False)
	return len(rows)
