"""Shared alert sender (GEN-61, screens §2.8).

Every scheduled alert sends both a system notification (bell) and an email with the same
subject and an "Open in PVFSS ERP" link. Thresholded alerts (LC 30/15/7, ICV 90/30) call
``send`` once per threshold with the days remaining in the subject.
"""

import frappe
from frappe.utils import get_url_to_form


def send(recipients, subject, reference_doctype=None, reference_name=None, message=None, email=True):
	recipients = sorted({r for r in (recipients or []) if r and r not in ("Guest", "Administrator")})
	if not recipients:
		return []

	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	enqueue_create_notification(
		recipients,
		{
			"type": "Alert",
			"subject": subject,
			"email_content": message or subject,
			"document_type": reference_doctype,
			"document_name": reference_name,
			"from_user": "Administrator",
		},
	)

	if email:
		link = (
			get_url_to_form(reference_doctype, reference_name)
			if reference_doctype and reference_name
			else None
		)
		# The template is a file shipped with this app, never user input; values are escaped by Jinja.
		body = frappe.render_template(  # nosemgrep: frappe-ssti
			"pvfss/templates/emails/alert.html", {"subject": subject, "message": message, "link": link}
		)
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=body,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
		)
	return recipients


def users_with_role(*roles):
	"""Enabled system users holding any of ``roles``."""
	holders = frappe.get_all(
		"Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent", distinct=True
	)
	if not holders:
		return []
	return frappe.get_all(
		"User",
		filters={"name": ["in", holders], "enabled": 1, "user_type": "System User"},
		pluck="name",
	)
