# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from pvfss.pvfss_quality import traceability


def manufacturer_abbr(manufacturer):
	abbr = frappe.db.get_value("Manufacturer", manufacturer, "pvfss_abbr")
	if not abbr:
		words = re.findall(r"[A-Za-z0-9]+", manufacturer or "")
		abbr = "".join(w[0] for w in words).upper() if len(words) > 1 else (manufacturer or "")[:3].upper()
	return abbr


def clean_heat_no(heat_no):
	return " ".join(str(heat_no or "").split()).upper()


class HeatNumber(Document):
	"""TRC-01: one heat per (manufacturer, heat no); ID {manufacturer_abbr}-{heat_no}."""

	def autoname(self):
		self.heat_no = clean_heat_no(self.heat_no)
		self.check_unique()
		self.name = f"{manufacturer_abbr(self.manufacturer)}-{self.heat_no}"

	def validate(self):
		self.heat_no = clean_heat_no(self.heat_no)
		self.check_unique()
		if self.status == "Active":
			self.status_reason = None

	def check_unique(self):
		existing = frappe.db.get_value(
			"Heat Number",
			{"manufacturer": self.manufacturer, "heat_no": self.heat_no, "name": ["!=", self.name or ""]},
		)
		if existing:
			frappe.throw(
				_("Heat {0} already exists for {1} as {2}.").format(
					self.heat_no, self.manufacturer, existing
				),
				title=_("Duplicate heat"),
			)

	def onload(self):
		self.set_onload("summary", traceability.heat_summary(self.name))

	def on_update(self):
		before = self.get_doc_before_save()
		if before and before.status != self.status:
			frappe.db.set_value("Batch", {"pvfss_heat_number": self.name}, "pvfss_heat_status", self.status)
