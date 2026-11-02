# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from pvfss.pvfss_hse.doctype.capa.capa import open_capas
from pvfss.utils import alerts

INVESTIGATING = "Under investigation"
ACTIONS = "Actions open"
CLOSED = "Closed"
TYPES = ("Injury", "Near miss", "Property damage", "Environmental", "Dangerous occurrence")


class HSEIncident(Document):
	"""Incident report, investigation, CAPA and closure (HSE-30)."""

	def validate(self):
		self.reported_by = self.reported_by or self.owner or frappe.session.user
		self.reported_on = self.reported_on or now_datetime()
		self.is_lti = int(self.incident_type == "Injury" and cint(self.lost_days) > 0)
		for i, row in enumerate(self.five_whys, start=1):
			row.why_no = i
		before = self.get_doc_before_save()
		state = self.get("workflow_state")
		if before and state != before.get("workflow_state"):
			if state == ACTIONS and not (self.root_cause and self.investigator):
				frappe.throw(_("Record the root cause and the investigator before opening actions."))
			if state == ACTIONS and not self.capas:
				frappe.throw(_("Create at least one CAPA before opening actions."))
			if state == CLOSED:
				pending = open_capas(r.capa for r in self.capas)
				if pending:
					frappe.throw(_("CAPAs still open: {0}.").format(", ".join(pending)), title=_("Cannot close"))
				self.closed_by = frappe.session.user
				self.closure_date = now_datetime().date()
			if state == INVESTIGATING and not self.investigator:
				self.investigator = frappe.session.user

	def after_insert(self):
		alerts.send(
			alerts.users_with_role("HSE Manager"),
			_("{0} reported: {1} at {2}.").format(self.name, _(self.incident_type), self.location),
			"HSE Incident",
			self.name,
		)


@frappe.whitelist()
def report_incident(
	incident_type: str,
	location: str,
	description: str,
	incident_datetime: str | None = None,
	people: str | None = None,
	immediate_action: str | None = None,
	photo: str | None = None,
):
	"""SCR-HSE-09 quick report, open to every user."""
	if incident_type not in TYPES:
		frappe.throw(_("Choose the incident type."))
	doc = frappe.get_doc(
		{
			"doctype": "HSE Incident",
			"incident_type": incident_type,
			"incident_datetime": incident_datetime or now_datetime(),
			"location": location,
			"description": description,
			"immediate_action": immediate_action,
			"photo": photo,
			"people": [{"person": p.strip()} for p in (people or "").split(",") if p.strip()],
		}
	)
	doc.insert()
	return doc.name


@frappe.whitelist()
def make_capa(incident: str, action_type: str, description: str, action_owner: str, due_date: str):
	doc = frappe.get_doc("HSE Incident", incident)
	doc.check_permission("write")
	capa = frappe.get_doc(
		{
			"doctype": "CAPA",
			"source_doctype": "HSE Incident",
			"source_name": incident,
			"action_type": action_type,
			"description": description,
			"action_owner": action_owner,
			"due_date": due_date,
		}
	).insert()
	return capa.name
