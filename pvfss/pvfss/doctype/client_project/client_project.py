# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ClientProject(Document):
	"""End-client project an inquiry belongs to (MD-02, SCR-MD-04)."""

	def validate(self):
		self.project_code = (self.project_code or "").strip()
		self.validate_unique_overrides()

	def validate_unique_overrides(self):
		"""One MTC age override row per (product category, material type)."""
		seen = {}
		for row in self.mtc_age_overrides or []:
			key = (row.product_category, row.material_type)
			if key in seen:
				frappe.throw(
					_(
						"MTC Age Overrides rows {0} and {1} both cover {2} / {3}. Keep one row per pair."
					).format(seen[key], row.idx, row.product_category, row.material_type),
					title=_("Duplicate MTC age override"),
				)
			seen[key] = row.idx

	def get_mtc_age_override(self, product_category, material_type):
		"""Return the override row for a line, or None (used by the MTC age lookup, SMR-20)."""
		for row in self.mtc_age_overrides or []:
			if row.product_category == product_category and row.material_type == material_type:
				return row
		return None
