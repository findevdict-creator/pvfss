# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class HSECourse(Document):
	"""Course and who needs it, for the training matrix (HSE-20)."""

	def required_for(self, employee):
		if self.required_for_all:
			return True
		return any(
			(not r.department or r.department == employee.get("department"))
			and (not r.designation or r.designation == employee.get("designation"))
			for r in self.requirements
		)
