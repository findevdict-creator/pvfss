# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MTCAgeRule(Document):
	"""SMR-20 company default: one active rule per product category and material type."""

	def validate(self):
		if not self.active:
			return
		other = frappe.db.get_value(
			"MTC Age Rule",
			{
				"product_category": self.product_category,
				"material_type": self.material_type,
				"active": 1,
				"name": ["!=", self.name or ""],
			},
		)
		if other:
			frappe.throw(
				_("An active rule for {0} + {1} already exists: {2}.").format(
					self.product_category, self.material_type, other
				)
			)
