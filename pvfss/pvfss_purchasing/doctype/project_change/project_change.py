# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

APPROVED = "Approved"
REJECTED = "Rejected"
DIRECTOR_ROLES = ("PVFSS Director", "System Manager")


class ProjectChange(Document):
	"""Change register (PRJ-30). A change that reduces margin needs Director approval."""

	def validate(self):
		self.raised_on = self.raised_on or nowdate()
		sales_order = frappe.db.get_value("Project", self.project, "sales_order") if self.project else None
		revenue = flt(frappe.db.get_value("Sales Order", sales_order, "base_net_total")) if sales_order else 0
		self.margin_impact_pct = flt(self.margin_impact) * 100.0 / revenue if revenue else 0

	def before_submit(self):
		if self.get("workflow_state") not in (APPROVED, REJECTED):
			frappe.throw(_("Approve or reject the change through the workflow."))
		if (
			self.workflow_state == APPROVED
			and flt(self.margin_impact) < 0
			and not set(frappe.get_roles()) & set(DIRECTOR_ROLES)
		):
			frappe.throw(
				_("A change that reduces the margin needs Director approval."), frappe.PermissionError
			)
		self.approved_by = frappe.session.user
		self.approval_date = nowdate()
