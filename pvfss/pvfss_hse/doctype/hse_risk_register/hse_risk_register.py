# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from pvfss.pvfss_hse.risk import rate


class HSERiskRegister(Document):
	"""Hazard / aspect with initial and residual rating from the Risk Matrix (HSE-02)."""

	def validate(self):
		self.risk_score, self.rating = rate(self.likelihood, self.severity)
		self.residual_score, self.residual_rating = rate(self.residual_likelihood, self.residual_severity)
		if self.has_value_changed("review_date"):
			self.review_alerted_on = None
