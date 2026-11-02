# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class HSEPolicyandObjective(Document):
	"""HSE policy with objectives (HSE-01). One Active policy at a time."""

	def validate(self):
		done = sum(1 for r in self.objectives if r.status == "Achieved")
		self.objectives_achieved = f"{done}/{len(self.objectives)}"
		if self.status == "Active" and not self.approved_by:
			frappe.throw(_("An active policy needs the approver."))

	def on_update(self):
		if self.status == "Active":
			for name in frappe.get_all(
				"HSE Policy and Objective", filters={"status": "Active", "name": ["!=", self.name]}, pluck="name"
			):
				frappe.db.set_value("HSE Policy and Objective", name, "status", "Superseded")
