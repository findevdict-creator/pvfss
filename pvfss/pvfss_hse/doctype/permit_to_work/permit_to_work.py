# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

HSE_MANAGERS = {"HSE Manager", "System Manager"}

# HSE-10: default precautions per permit type
PRECAUTIONS = {
	"Hot work": ["Fire extinguisher at the work point", "Combustibles removed or covered", "Fire watch assigned", "Gas test done"],
	"Work at height": ["Harness and lanyard inspected", "Scaffold tagged safe", "Area below barricaded"],
	"Confined space": ["Atmosphere tested", "Standby person assigned", "Rescue plan in place", "Ventilation running"],
	"Electrical": ["Isolation and lock-out applied", "Voltage absence tested", "Insulated tools"],
	"General": ["Toolbox talk held", "PPE checked"],
}


class PermittoWork(Document):
	"""Permit to work: Requested -> Issued (submit) -> Closed / Expired / Cancelled (HSE-10)."""

	def validate(self):
		if get_datetime(self.valid_to) <= get_datetime(self.valid_from):
			frappe.throw(_("Valid to must be after valid from."))
		if not self.precautions:
			for text in PRECAUTIONS.get(self.permit_type, []):
				self.append("precautions", {"precaution": text, "applicable": 1})
		if self.docstatus == 0:
			self.status = "Requested"

	def before_submit(self):
		if not HSE_MANAGERS & set(frappe.get_roles()):
			frappe.throw(_("Only the HSE Manager can issue a permit."), frappe.PermissionError)
		open_items = [r.precaution for r in self.precautions if r.applicable and not r.confirmed]
		if open_items:
			frappe.throw(_("Confirm the precautions before issuing: {0}.").format("; ".join(open_items)))
		self.status = "Issued"
		self.issued_by = frappe.session.user
		self.issued_on = now_datetime()

	def on_cancel(self):
		self.db_set("status", "Cancelled")


@frappe.whitelist()
def close(permit: str, remarks: str | None = None):
	doc = frappe.get_doc("Permit to Work", permit)
	doc.check_permission("submit")
	if doc.status not in ("Issued", "Expired"):
		frappe.throw(_("Permit {0} is {1}.").format(doc.name, _(doc.status)))
	if not doc.area_safe:
		frappe.throw(_("Confirm that the area is left safe before closing."))
	doc.status = "Closed"
	doc.closed_by = frappe.session.user
	doc.closed_on = now_datetime()
	doc.closure_remarks = remarks or doc.closure_remarks
	doc.save()
	return doc.status
