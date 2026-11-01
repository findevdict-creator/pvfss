# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate

from pvfss.utils import settings


def band_for(score):
	"""SCR-SUP-04 colour bands: >=4 Good, 3-4 Satisfactory, 2-3 Weak, <2 Poor."""
	if score >= 4:
		return "Good"
	if score >= 3:
		return "Satisfactory"
	if score >= 2:
		return "Weak"
	return "Poor"


class SupplierEvaluation(Document):
	"""Supplier performance evaluation (SUP-05, SCR-SUP-05)."""

	def onload(self):
		if self.is_new() and not self.scores:
			self.load_criteria()

	def before_validate(self):
		if not self.scores:
			self.load_criteria()

	def load_criteria(self):
		self.set(
			"scores",
			[
				{"criterion": row.criterion, "weight_pct": row.weight_pct}
				for row in settings.get().supplier_evaluation_criteria or []
			],
		)

	def validate(self):
		if self.evaluation_basis == "Period" and self.period_from and self.period_to:
			if getdate(self.period_to) < getdate(self.period_from):
				frappe.throw(_("Period To cannot be before Period From."))
		for row in self.scores:
			if row.score and not 1 <= cint(row.score) <= 5:
				frappe.throw(_("Row {0}: score must be between 1 and 5.").format(row.idx))
		self.calculate()
		self.set_reference_data()

	def before_submit(self):
		missing = [row.criterion for row in self.scores if not cint(row.score)]
		if missing:
			frappe.throw(
				_("Score every criterion before submitting. Missing: {0}").format(", ".join(missing)),
				title=_("Supplier evaluation"),
			)

	def calculate(self):
		weight = sum(flt(r.weight_pct) for r in self.scores if cint(r.score))
		total = sum(flt(r.weight_pct) * cint(r.score) for r in self.scores if cint(r.score))
		self.weighted_total = flt(total / weight, 2) if weight else 0
		self.band = band_for(self.weighted_total) if weight else None

	def set_reference_data(self):
		"""System facts for the period or PO (SCR-SUP-05 Reference data)."""
		filters = {"supplier": self.supplier, "docstatus": 1}
		if self.evaluation_basis == "Purchase Order" and self.purchase_order:
			filters["name"] = self.purchase_order
		elif self.period_from and self.period_to:
			filters["transaction_date"] = ["between", [self.period_from, self.period_to]]
		pos = frappe.get_all("Purchase Order", filters=filters, pluck="name")
		self.po_count = len(pos)
		self.on_time_pct = on_time_pct(pos)
		self.ncr_count = 0
		if pos and frappe.get_meta("Non Conformance").has_field("pvfss_purchase_order"):
			self.ncr_count = frappe.db.count("Non Conformance", {"pvfss_purchase_order": ["in", pos]})


def on_time_pct(purchase_orders):
	"""Share of received PO lines whose receipt date was on or before the PO line schedule date."""
	if not purchase_orders:
		return 0
	rows = frappe.db.sql(
		"""
		select poi.schedule_date, pr.posting_date
		from `tabPurchase Receipt Item` pri
		join `tabPurchase Receipt` pr on pr.name = pri.parent and pr.docstatus = 1
		join `tabPurchase Order Item` poi on poi.name = pri.purchase_order_item
		where pri.purchase_order in %(pos)s
		""",
		{"pos": purchase_orders},
		as_dict=True,
	)
	if not rows:
		return 0
	on_time = sum(1 for r in rows if r.schedule_date and getdate(r.posting_date) <= getdate(r.schedule_date))
	return flt(on_time * 100.0 / len(rows), 1)
