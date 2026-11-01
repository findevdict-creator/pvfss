# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

ALERT_TABLES = ("lc_expiry_alert_days", "icv_expiry_alert_days")


class PVFSSSettings(Document):
	"""Single DocType holding every configurable rule value (GEN-06, GEN-30, SCR-GEN-04)."""

	def validate(self):
		self.validate_non_negative()
		self.validate_evaluation_weights()
		self.normalise_alert_tables()

	def validate_non_negative(self):
		"""All day counts and thresholds must be zero or more (SCR-GEN-04)."""
		for df in self.meta.fields:
			if df.fieldtype in ("Int", "Currency", "Percent", "Float") and flt(self.get(df.fieldname)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(df.label)), title=_("PVFSS Settings"))

	def validate_evaluation_weights(self):
		"""Supplier evaluation weights must total 100% (SUP-05)."""
		rows = self.supplier_evaluation_criteria or []
		if not rows:
			return
		seen = set()
		for row in rows:
			key = (row.criterion or "").strip().lower()
			if key in seen:
				frappe.throw(
					_("Row {0}: criterion {1} is listed twice.").format(row.idx, frappe.bold(row.criterion)),
					title=_("Supplier evaluation"),
				)
			seen.add(key)
		total = sum(flt(r.weight_pct) for r in rows)
		if abs(total - 100) > 0.001:
			frappe.throw(
				_("Supplier evaluation weights must total 100%. They currently total {0}%.").format(
					flt(total, 2)
				),
				title=_("Supplier evaluation"),
			)

	def normalise_alert_tables(self):
		"""Drop duplicate thresholds and keep them largest first (e.g. 30, 15, 7)."""
		for table in ALERT_TABLES:
			rows = self.get(table) or []
			days = sorted({cint(r.days_before) for r in rows}, reverse=True)
			if [cint(r.days_before) for r in rows] == days:
				continue
			self.set(table, [{"days_before": d} for d in days])

	def on_update(self):
		# Frappe clears the cached document on save; also drop any derived caches.
		frappe.cache.delete_keys("pvfss:")
