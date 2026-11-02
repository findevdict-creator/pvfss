# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as assign
from frappe.model.document import Document

from pvfss.pvfss_finance import accounts
from pvfss.pvfss_finance.retention import release_entry
from pvfss.utils import alerts


class Retention(Document):
	"""Retention held on an invoice (FIN-50 to FIN-52, SCR-FIN-13)."""


def _retention(name):
	doc = frappe.get_doc("Retention", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def request_release(retention: str):
	doc = _retention(retention)
	if doc.status != "Held":
		frappe.throw(_("Only held retention can be requested for release."))
	doc.status = "Release requested"
	doc.save()
	for user in alerts.users_with_role("Finance Manager")[:1]:
		assign(
			{
				"assign_to": [user],
				"doctype": "Retention",
				"name": doc.name,
				"description": _("Release retention"),
			}
		)
	return doc.status


@frappe.whitelist()
def release(retention: str):
	"""FIN-52: reverse JE so the amount can be collected or paid normally."""
	accounts.require_finance_manager()
	doc = _retention(retention)
	if doc.status not in ("Held", "Release requested"):
		frappe.throw(_("Retention {0} is {1}.").format(doc.name, _(doc.status)))
	doc.release_journal_entry = release_entry(doc)
	doc.status = "Released"
	doc.save()
	return doc.release_journal_entry


@frappe.whitelist()
def forfeit(retention: str, reason: str):
	accounts.require_finance_manager()
	if not (reason or "").strip():
		frappe.throw(_("Enter the reason."))
	doc = _retention(retention)
	if doc.status in ("Released", "Forfeited"):
		frappe.throw(_("Retention {0} is {1}.").format(doc.name, _(doc.status)))
	doc.forfeit_reason = reason
	doc.status = "Forfeited"
	doc.save()
	return doc.status
