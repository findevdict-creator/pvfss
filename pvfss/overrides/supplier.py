"""Supplier doc events (SUP-01, SUP-04, SUP-07)."""

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, nowdate, today

from pvfss.utils import settings

RESTRICTED = ("Suspended", "Blacklisted")
STATUS_ROLES = ("Pre-Bidding Manager", "Post-Bidding Manager", "System Manager")


def validate(doc, method=None):
	validate_approval(doc)
	set_document_status(doc)


def validate_approval(doc):
	"""Suspending / blacklisting needs a remark and a PBM / POM (SCR-SUP-02 Approval tab)."""
	if not doc.pvfss_approval_status:
		doc.pvfss_approval_status = "Prospect"
	if not doc.has_value_changed("pvfss_approval_status"):
		return
	if doc.pvfss_approval_status in RESTRICTED:
		if not set(frappe.get_roles()) & set(STATUS_ROLES):
			frappe.throw(
				_("Only a Pre-Bidding or Post-Bidding Manager can set a supplier to {0}.").format(
					_(doc.pvfss_approval_status)
				),
				frappe.PermissionError,
			)
		if not (doc.pvfss_approval_remarks or "").strip():
			frappe.throw(
				_("Enter an approval remark when setting a supplier to {0}.").format(
					_(doc.pvfss_approval_status)
				)
			)
	if doc.pvfss_approval_status in ("Approved", "Conditionally approved"):
		doc.pvfss_approval_date = doc.pvfss_approval_date or today()
		doc.pvfss_approved_by = doc.pvfss_approved_by or frappe.session.user


def document_status(expiry_date, alert_days=None):
	if not expiry_date:
		return "Valid"
	alert_days = settings.get_int("supplier_doc_expiry_alert_days", 30) if alert_days is None else alert_days
	days = date_diff(getdate(expiry_date), getdate(nowdate()))
	if days < 0:
		return "Expired"
	if days <= alert_days:
		return "Expiring"
	return "Valid"


def set_document_status(doc):
	alert_days = settings.get_int("supplier_doc_expiry_alert_days", 30)
	for row in doc.get("pvfss_documents") or []:
		row.status = document_status(row.expiry_date, alert_days)
