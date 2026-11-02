# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality import traceability
from pvfss.pvfss_quality.doctype.heat_number.heat_number import clean_heat_no

UNDER_REVIEW = "Under Review"
DECISIONS = ("Accepted", "Rejected", "Accepted with re-test")
ACCEPTED_RESULTS = ("Accepted", "Accepted with re-test")


class MTC(Document):
	"""Material Test Certificate with review, authenticity and approval (QA-20 to QA-24, SCR-QA-14)."""

	def validate(self):
		self.validate_heats()
		self.link_heats()
		self.refresh_review()
		before = self.get_doc_before_save()
		state = self.get("workflow_state")
		if state == UNDER_REVIEW and (before.get("workflow_state") if before else None) != UNDER_REVIEW:
			self.reviewer = frappe.session.user
			self.review_date = self.review_date or nowdate()

	def refresh_review(self):
		from pvfss.pvfss_quality.doctype.inspection_report.inspection_report import auto_result

		for row in list(self.chemical) + list(self.mechanical):
			row.result = auto_result(row)
		verified = any(v.result == "Verified" for v in self.verifications)
		self.authenticity = _("Verified") if verified else _("Not verified")
		checks = self.age_checks()
		over = [c for c in checks if c["over"]]
		self.age_over = int(bool(over))
		if over:
			self.age_check = over[0]["message"]
		elif checks:
			c = checks[0]
			rule = c["rule"]
			self.age_check = (
				_("Age {0} / {1} months ({2}, {3}), reference {4}").format(
					c["age"], rule["months"], rule["label"], rule["source"], self.review_date or nowdate()
				)
				if rule and rule["months"]
				else c["message"]
			)

	def age_checks(self):
		from pvfss.utils import mtc_age

		if not self.issue_date or self.is_new():
			return []
		project = self.supplier_po and frappe.db.get_value("Purchase Order", self.supplier_po, "project")
		ref = mtc_age.reference_date(self.review_date)
		seen, out = set(), []
		for row in self.heats:
			if row.item_code in seen or not row.item_code:
				continue
			seen.add(row.item_code)
			out.append(mtc_age.check(self.name, row.heat_no, row.item_code, ref, project=project))
		return out

	def decision_checks(self, state):
		result = GateResult(_("MTC cannot be {0}").format(_(state)), doc=self)
		if state == "Accepted":
			result.check(
				any(v.result == "Verified" for v in self.verifications),
				_("Add at least one verified authenticity check"),
				rule="QA-22",
			)
			result.check(
				not self.age_over,
				(self.age_check or "") + " " + _("Use Accepted with re-test and link the re-test report."),
				rule="SMR-20",
			)
		if state == "Accepted with re-test":
			result.check(self.retest_report, _("Link the re-test Inspection Report"), rule="QA-21")
		return result

	def validate_heats(self):
		if not self.heats:
			frappe.throw(_("List the heat numbers this certificate covers."))
		default_item = self.items[0].item_code if len(self.items or []) == 1 else None
		seen = set()
		for row in self.heats:
			row.heat_no = clean_heat_no(row.heat_no)
			row.item_code = row.item_code or default_item
			key = (row.heat_no, row.item_code)
			if key in seen:
				frappe.throw(_("Row {0}: heat {1} is listed twice.").format(row.idx, row.heat_no))
			seen.add(key)
			if not row.item_code:
				frappe.throw(_("Row {0}: enter the item for heat {1}.").format(row.idx, row.heat_no))
			if self.items and row.item_code not in {i.item_code for i in self.items}:
				frappe.throw(
					_("Row {0}: item {1} is not one of this certificate's items.").format(
						row.idx, row.item_code
					)
				)

	def link_heats(self):
		"""TRC-01: every heat on the certificate becomes (or links to) a Heat Number."""
		for row in self.heats:
			if row.heat_no and row.item_code and self.manufacturer:
				row.heat_number = traceability.get_or_create_heat(
					row.heat_no, self.manufacturer, row.item_code, grade=self.grade, mtc=self.certificate_no
				)

	def before_submit(self):
		self.link_heats()
		state = self.get("workflow_state")
		if state in DECISIONS:
			self.decision_checks(state).throw_if_failed()
			self.review_result = state
			self.reviewer = self.reviewer or frappe.session.user
			self.review_date = self.review_date or nowdate()

	def on_submit(self):
		for row in self.heats:
			heat = frappe.db.get_value("Heat Number", row.heat_number, ["primary_mtc", "grade"], as_dict=True)
			values = {}
			if not heat.primary_mtc:
				values.update(primary_mtc=self.certificate_no, mtc_date=self.issue_date)
			if not heat.grade:
				values["grade"] = self.grade
			if values:
				frappe.db.set_value("Heat Number", row.heat_number, values)


def heats_for(heat_nos, supplier_po=None):
	"""Submitted MTC heat rows for the given heat numbers: {heat_no: [rows]}."""
	if not heat_nos:
		return {}
	filters = {"heat_no": ["in", list(heat_nos)]}
	rows = frappe.get_all(
		"MTC Heat",
		filters={**filters, "parenttype": "MTC"},
		fields=["parent as mtc", "heat_no", "heat_number", "item_code", "qty", "uom"],
	)
	mtcs = {
		m.name: m
		for m in frappe.get_all(
			"MTC",
			filters={"name": ["in", list({r.mtc for r in rows}) or [""]], "docstatus": ["<", 2]},
			fields=[
				"name",
				"certificate_no",
				"grade",
				"manufacturer",
				"issue_date",
				"supplier_po",
				"review_result",
			],
		)
	}
	out = {}
	for row in rows:
		mtc = mtcs.get(row.mtc)
		if not mtc or mtc.review_result == "Rejected":
			continue
		row.update(
			grade=mtc.grade,
			manufacturer=mtc.manufacturer,
			issue_date=mtc.issue_date,
			certificate_no=mtc.certificate_no,
			same_po=not supplier_po or not mtc.supplier_po or mtc.supplier_po == supplier_po,
		)
		out.setdefault(row.heat_no, []).append(row)
	return out


def trace_nodes(heats, batches):
	"""Heat Trace stages (TRC-10): the MTC documents for the heats and the tally sheets of the lots."""
	nodes = []
	for row in frappe.get_all(
		"MTC Heat",
		filters={"heat_number": ["in", heats or [""]], "parenttype": "MTC", "docstatus": 1},
		fields=["parent", "heat_number", "qty"],
	):
		mtc = frappe.db.get_value(
			"MTC",
			row.parent,
			["certificate_no", "issue_date", "certificate_type", "review_result"],
			as_dict=True,
		)
		nodes.append(
			{
				"stage": "MTC",
				"doctype": "MTC",
				"name": row.parent,
				"status": mtc.review_result,
				"facts": {
					"Certificate": mtc.certificate_no,
					"Date": mtc.issue_date,
					"Type": mtc.certificate_type,
				},
				"heat": row.heat_number,
				"label": mtc.certificate_no,
			}
		)
	for b in frappe.get_all(
		"Batch",
		filters={"name": ["in", batches or [""]], "pvfss_tally_sheet": ["is", "set"]},
		fields=["name", "pvfss_tally_sheet", "pvfss_heat_number"],
	):
		nodes.append(
			{
				"stage": "Tally Sheet",
				"doctype": "Tally Sheet",
				"name": b.pvfss_tally_sheet,
				"facts": {},
				"heat": b.pvfss_heat_number,
				"batch": b.name,
			}
		)
	return nodes
