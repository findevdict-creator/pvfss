# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from pvfss.pvfss_icv.icv import certificate_expiry_date


class ICVCertificate(Document):
	"""PVFSS ICV certificate; one Active at a time (ICV-02)."""

	def validate(self):
		self.expiry_date = certificate_expiry_date(self.issue_date)
		if self.status == "Active" and getdate(self.expiry_date) < getdate(nowdate()):
			self.status = "Expired"
		if self.has_value_changed("issue_date"):
			self.expiry_alerts_sent = ""

	def on_update(self):
		if self.status != "Active":
			return
		for name in frappe.get_all(
			"ICV Certificate", filters={"status": "Active", "name": ["!=", self.name]}, pluck="name"
		):
			frappe.db.set_value("ICV Certificate", name, "status", "Superseded")
			frappe.msgprint(_("Certificate {0} is now Superseded.").format(name), alert=True)
