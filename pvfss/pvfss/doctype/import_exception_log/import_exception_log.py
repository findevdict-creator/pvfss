# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class ImportExceptionLog(Document):
	"""One business rule skipped during a historical data import (IMP-01, SCR-GEN-05).

	The log is written by the system; a reviewer may only tick Reviewed and add a remark.
	"""

	EDITABLE = ("reviewed", "remark", "reviewed_by", "reviewed_on")

	def validate(self):
		if not self.is_new():
			self.validate_only_review_fields_changed()
		if self.has_value_changed("reviewed"):
			if self.reviewed:
				self.reviewed_by = frappe.session.user
				self.reviewed_on = now_datetime()
			else:
				self.reviewed_by = None
				self.reviewed_on = None

	def validate_only_review_fields_changed(self):
		before = self.get_doc_before_save()
		if not before:
			return
		for df in self.meta.get_data_fields():
			if df.fieldname in self.EDITABLE:
				continue
			if before.get(df.fieldname) != self.get(df.fieldname):
				frappe.throw(_("Only Reviewed and Remark can be changed on an Import Exception Log."))


@frappe.whitelist()
def mark_reviewed(names, remark=None):
	"""List / form action "Mark reviewed"."""
	if isinstance(names, str):
		names = frappe.parse_json(names) if names.startswith("[") else [names]
	for name in names:
		doc = frappe.get_doc("Import Exception Log", name)
		doc.check_permission("write")
		doc.reviewed = 1
		if remark:
			doc.remark = remark
		doc.save()
	return len(names)
