# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from pvfss.gates.base import GateResult
from pvfss.pvfss_crm import inquiry as inq
from pvfss.pvfss_crm import selection

COMPLIANT = ("Compliant", "Compliant with deviation")
SUPPLIER_TO_TE = {
	"Compliant": "Compliant",
	"Deviation": "Compliant with deviation",
	"Not compliant": "Not compliant",
}


class TechnicalEvaluation(Document):
	"""Technical compliance per inquiry line x shortlisted supplier (RFQ-11, SCR-RFQ-12)."""

	def onload(self):
		if self.is_new() and self.inquiry and not self.items:
			self.load_shortlist()

	def validate(self):
		if not self.items and self.inquiry:
			self.load_shortlist()
		self.refresh_selected()
		for row in self.items:
			if (
				row.compliance
				and row.compliance != "Compliant"
				and not (row.deviation_description or "").strip()
			):
				frappe.throw(
					_("Line {0} ({1}): enter the deviation description.").format(row.line_ref, row.supplier)
				)
		self.lines_evaluated = len({r.line_ref for r in self.items if r.compliance})
		self.not_compliant_count = sum(1 for r in self.items if r.compliance == "Not compliant")

	def after_insert(self):
		inq.advance(self.inquiry, inq.UNDER_EVALUATION, source=self.name)

	@frappe.whitelist()
	def load_shortlist(self):
		"""One row per quoted line of every submitted Supplier Quotation of the inquiry.

		Rows already evaluated are kept; new supplier lines are appended.
		"""
		existing = {r.supplier_quotation_item for r in self.items}
		for line in selection.quotation_lines(self.inquiry):
			if line.docstatus != 1 or not selection.is_quoted(line) or line.sq_item in existing:
				continue
			self.append(
				"items",
				{
					"line_ref": line.line_ref,
					"supplier": line.supplier,
					"supplier_quotation": line.supplier_quotation,
					"supplier_quotation_item": line.sq_item,
					"item_code": line.item_code,
					"selected": cint(line.selected),
					"supplier_compliance": line.compliance,
					"evaluator": self.evaluator or frappe.session.user,
				},
			)
		self.items.sort(key=lambda r: (selection._ref_key(r.line_ref), r.supplier or ""))
		for idx, row in enumerate(self.items, start=1):
			row.idx = idx

	def refresh_selected(self):
		selected = {line.sq_item for line in selection.selected_lines(self.inquiry).values()}
		for row in self.items:
			row.selected = 1 if row.supplier_quotation_item in selected else 0

	def before_submit(self):
		"""RFQ-11 [RULE]: every selected line Compliant or Compliant with deviation."""
		self.refresh_selected()
		result = GateResult(_("Technical evaluation"), doc=self, gate="RFQ-11")
		rows = {r.supplier_quotation_item: r for r in self.items}
		for ref, line in sorted(
			selection.selected_lines(self.inquiry).items(), key=lambda kv: selection._ref_key(kv[0])
		):
			row = rows.get(line.sq_item)
			if not row or not row.compliance:
				result.fail(
					_("Line {0} ({1}) is selected but not evaluated.").format(ref, line.supplier),
					rule="RFQ-11",
				)
			elif row.compliance not in COMPLIANT:
				result.fail(
					_(
						"Line {0} ({1}) is selected but Not compliant. Re-select the supplier on the Competitive Statement."
					).format(ref, line.supplier),
					rule="RFQ-11",
				)
		result.throw_if_failed()


def latest_for(inquiry):
	"""The latest submitted Technical Evaluation of an inquiry (or None)."""
	name = frappe.db.get_value(
		"Technical Evaluation", {"inquiry": inquiry, "docstatus": 1}, "name", order_by="creation desc"
	)
	return frappe.get_doc("Technical Evaluation", name) if name else None


def status_by_sq_item(inquiry):
	te = latest_for(inquiry)
	if not te:
		return None, {}
	return te, {r.supplier_quotation_item: r.compliance for r in te.items}
