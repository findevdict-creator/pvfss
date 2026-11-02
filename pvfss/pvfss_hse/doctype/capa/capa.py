# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

CLOSED = "Verified-Closed"
LINKED = {"HSE Incident": "capas", "Management Review": "actions"}


class CAPA(Document):
	"""Corrective / preventive action shared by incidents, audits, NCRs and reviews (HSE-32)."""

	def validate(self):
		if self.status in ("Completed", CLOSED):
			if not (self.evidence or self.evidence_note):
				frappe.throw(_("Add the completion evidence or a note."))
			self.completed_on = self.completed_on or getdate(nowdate())
		if self.status == CLOSED:
			if not self.verified_by:
				frappe.throw(_("Enter who verified the action."))
			if self.verified_by == self.action_owner:
				frappe.throw(_("The action owner cannot verify their own action."))
			self.verified_on = self.verified_on or getdate(nowdate())
		elif self.status != "Completed" and getdate(self.due_date) < getdate(nowdate()):
			self.status = "Overdue"
		elif self.status == "Overdue" and getdate(self.due_date) >= getdate(nowdate()):
			self.status = "Open"

	def after_insert(self):
		table = LINKED.get(self.source_doctype)
		if table:
			source = frappe.get_doc(self.source_doctype, self.source_name)
			if not any(r.capa == self.name for r in source.get(table)):
				source.append(table, {"capa": self.name})
				source.flags.ignore_permissions = True
				source.save()

	def on_update(self):
		sync_rows(self)


def sync_rows(capa):
	"""Refresh the read-only CAPA columns on every table that lists it."""
	values = {
		"action_type": capa.action_type,
		"action_owner": capa.action_owner,
		"due_date": capa.due_date,
		"status": capa.status,
	}
	for row in frappe.get_all("HSE CAPA Link", filters={"capa": capa.name}, pluck="name"):
		frappe.db.set_value("HSE CAPA Link", row, values, update_modified=False)


def open_capas(names):
	return [
		r.name
		for r in frappe.get_all("CAPA", filters={"name": ["in", list(names) or [""]]}, fields=["name", "status"])
		if r.status != CLOSED
	]
