# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality.doctype.itp import itp as itp_module
from pvfss.utils.mtc_age import group_chain

SAMPLED_TESTS = ("Mechanical", "Chemical")
REJECTED = "Rejected"


def auto_result(row):
	"""QA-24: Pass / Fail when a spec limit is given; the manual result otherwise."""
	value = row.get("actual") if row.doctype == "Test Result" else row.get("value")
	low, high = flt(row.spec_min), flt(row.spec_max)
	if not (low or high) or value in (None, ""):
		return row.result
	value = flt(value)
	return "Fail" if (low and value < low) or (high and value > high) else "Pass"


class InspectionReport(Document):
	"""Inspection results per ITP point and tests (QA-13, QA-14, SCR-QA-10)."""

	def before_validate(self):
		if self.rfi and not self.point_results:
			self.load_from_rfi()

	@frappe.whitelist()
	def load_from_rfi(self):
		rfi = frappe.get_doc("RFI", self.rfi)
		self.supplier_po = rfi.supplier_po
		self.itp = rfi.itp
		self.set("point_results", [{"seq": p.seq, "activity": p.activity} for p in rfi.points])
		if not self.inspectors:
			for party in rfi.parties:
				name = party.inspector_name or party.employee
				if name:
					self.append("inspectors", {"party": party.party, "inspector_name": name})

	def validate(self):
		for row in self.test_results:
			row.result = auto_result(row)
		self.tests_failed = sum(1 for r in self.test_results if r.result == "Fail")
		results = {r.result for r in self.point_results if r.result}
		if REJECTED in results:
			self.result_summary = _("Rejected")
		elif "Accepted with remarks" in results:
			self.result_summary = _("With remarks")
		elif results:
			self.result_summary = _("Accepted")
		missing, rule = self.sampling_gaps()
		if rule:
			self.sampling_check = (
				_("Heats without a {0} mm sample: {1}").format(
					rule.sample_length_mm or "", ", ".join(missing)
				)
				if missing
				else _("Every heat has a sample ID ({0}).").format(rule.rule_text or rule.product_category)
			)
		else:
			self.sampling_check = None

	def before_submit(self):
		result = GateResult(_("Inspection Report cannot be submitted"), doc=self)
		for row in self.point_results:
			result.check(row.result, _("Point {0} ({1}): enter the result").format(row.seq, row.activity))
		missing, rule = self.sampling_gaps()
		result.check(
			not missing,
			_("Pipe sampling: heats without a {0} mm sample ID: {1}").format(_mm(rule), ", ".join(missing)),
			rule="QA-14",
		)
		result.throw_if_failed()

	def on_submit(self):
		accepted = [r.seq for r in self.point_results if r.result in ("Accepted", "Accepted with remarks")]
		if self.itp and accepted:
			itp_module.set_points(self.itp, set(accepted), itp_module.CLOSED, self.name)
		self.update_rfi()

	def on_cancel(self):
		closed = [r.seq for r in self.point_results if r.result in ("Accepted", "Accepted with remarks")]
		if self.itp and closed:
			itp_module.set_points(self.itp, set(closed), itp_module.OPEN)
		frappe.db.set_value("RFI", self.rfi, "status", "Scheduled")

	def update_rfi(self):
		rfi = frappe.get_doc("RFI", self.rfi)
		all_accepted = all(r.result in ("Accepted", "Accepted with remarks") for r in self.point_results)
		frappe.db.set_value("RFI", rfi.name, "status", "Closed" if all_accepted else "Inspected")

	# ------------------------------------------------------------------ QA-14
	def lot_heats(self):
		rfi = frappe.get_doc("RFI", self.rfi) if self.rfi else None
		return [(m.item_code, m.heat_number) for m in (rfi.material if rfi else []) if m.heat_number]

	def sampling_gaps(self):
		"""Heats in the inspected lot without a sample ID, for categories with a Sampling Rule."""
		if not any(r.test_type in SAMPLED_TESTS for r in self.test_results):
			return [], None
		sampled = {r.heat_number for r in self.test_results if r.heat_number and r.sample_id}
		missing, used = [], None
		for item_code, heat in self.lot_heats():
			rule = sampling_rule(item_code)
			if not rule or not rule.samples_per_heat:
				continue
			used = rule
			if heat not in sampled and heat not in missing:
				missing.append(heat)
		return missing, used


def _mm(rule):
	return f"{flt(rule.sample_length_mm):g}" if rule and rule.sample_length_mm else ""


def sampling_rule(item_code):
	group = frappe.get_cached_value("Item", item_code, "item_group")
	for category in group_chain(group):
		name = frappe.db.get_value("Sampling Rule", {"product_category": category, "active": 1})
		if name:
			return frappe.get_cached_doc("Sampling Rule", name)
	return None


@frappe.whitelist()
def make_ncr(inspection_report: str):
	"""SCR-QA-10 "Raise NCR": prefilled from the rejected points and failed tests."""
	ir = frappe.get_doc("Inspection Report", inspection_report)
	ir.check_permission("read")
	failed = [r for r in ir.test_results if r.result == "Fail"]
	rejected = [r for r in ir.point_results if r.result == REJECTED]
	lines = [_("Point {0} ({1}) rejected: {2}").format(r.seq, r.activity, r.remarks or "") for r in rejected]
	lines += [
		_("{0} {1} on heat {2}: {3} (spec {4} to {5})").format(
			r.test_type,
			r.parameter or "",
			r.heat_number or "-",
			r.actual,
			r.spec_min or "-",
			r.spec_max or "-",
		)
		for r in failed
	]
	heats = {r.heat_number for r in failed if r.heat_number} or {h for _i, h in ir.lot_heats()}
	items = dict((h, i) for i, h in ir.lot_heats())
	ncr = frappe.get_doc(
		{
			"doctype": "Non Conformance",
			"subject": _("Inspection {0} findings").format(ir.name),
			"details": "<br>".join(frappe.utils.escape_html(x) for x in lines) or ir.name,
			"pvfss_source": "Inspection Report",
			"pvfss_source_doctype": "Inspection Report",
			"pvfss_source_document": ir.name,
			"pvfss_supplier_po": ir.supplier_po,
			"pvfss_severity": "Major",
			"pvfss_heats": [{"heat_number": h, "item_code": items.get(h)} for h in sorted(heats)],
		}
	)
	ncr.insert()
	return ncr.name
