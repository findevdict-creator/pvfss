# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import get_first_day, getdate


class HSEMonthlyStatistics(Document):
	"""Headcount and hours worked per month (HSE-41)."""

	def before_naming(self):
		self.validate()

	def validate(self):
		self.month = get_first_day(self.month)
		self.month_label = getdate(self.month).strftime("%Y-%m")
