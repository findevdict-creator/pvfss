# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, add_months, cint, getdate, nowdate

from pvfss.utils import settings


def training_status(expiry_date, today=None):
	if not expiry_date:
		return "Valid"
	today = getdate(today or nowdate())
	if getdate(expiry_date) < today:
		return "Expired"
	if getdate(expiry_date) <= getdate(add_days(today, settings.get_int("hse_expiry_alert_days", 30))):
		return "Expiring"
	return "Valid"


class HSETrainingRecord(Document):
	"""Training attended with certificate and expiry (HSE-20)."""

	def validate(self):
		months = cint(frappe.db.get_value("HSE Course", self.course, "validity_months"))
		if months and not self.expiry_date:
			self.expiry_date = add_months(self.training_date, months)
		self.status = training_status(self.expiry_date)
		if self.has_value_changed("expiry_date"):
			self.alerted_on = None
