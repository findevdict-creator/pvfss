"""CRM scheduled alerts (CRM-12, SCR-CRM-08)."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from pvfss.pvfss_crm import inquiry as inq
from pvfss.utils import alerts

SILENT_STAGES = (inq.QUOTED, *inq.CLOSED)


def inquiry_due_date(today=None):
	"""Alert owner and Pre-Bidding Managers N days before the bid due date and on the day."""
	today = getdate(today or nowdate())
	n = inq.due_alert_days()
	targets = {today: 0}
	if n > 0:
		targets[add_days(today, n)] = n
	sent = 0
	managers = alerts.users_with_role("Pre-Bidding Manager")
	for due, days in targets.items():
		for row in frappe.get_all(
			"Opportunity",
			filters={
				"pvfss_stage": ["not in", SILENT_STAGES],
				"pvfss_bid_due_date": ["between", [f"{due} 00:00:00", f"{due} 23:59:59"]],
			},
			fields=[
				"name",
				"customer_name",
				"party_name",
				"pvfss_client_project",
				"pvfss_stage",
				"pvfss_owner",
			],
		):
			when = _("today") if days == 0 else _("in {0} days").format(days)
			subject = _("Bid due {0}: {1} - {2} - {3}. Stage: {4}.").format(
				when,
				row.name,
				row.customer_name or row.party_name,
				row.pvfss_client_project or _("no client project"),
				_(row.pvfss_stage),
			)
			alerts.send([row.pvfss_owner, *managers], subject, "Opportunity", row.name)
			sent += 1
	return sent
