# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality.doctype.mtc.mtc import heats_for
from pvfss.pvfss_quality.doctype.tally_sheet.tally_sheet import po_lines
from pvfss.utils import mtc_age

RECEIVED = "Received"
UNDER_REVIEW = "Under Review"
ACCEPTED = "Accepted"
PARTIAL = "Partially accepted"
REJECTED = "Rejected"
DECIDED = (ACCEPTED, PARTIAL, REJECTED)
REQUIRED_ANNEXURES = ("MTC", "Tally Sheet")
MATCH = "Match"
QTY_TOLERANCE = 0.001


class SMR(Document):
	"""Stock Material Requisition: a supplier's ready-stock offer (SMR-01 to SMR-30, SCR-SMR-02)."""

	def before_validate(self):
		if self.supplier_po and not self.items:
			self.pull_lines()
		for row in self.annexures:
			if not row.reference_doctype and row.annexure_type in REQUIRED_ANNEXURES and row.reference_name:
				row.reference_doctype = row.annexure_type

	def validate(self):
		before = self.get_doc_before_save()
		previous = before.get("workflow_state") if before else None
		state = self.get("workflow_state")
		if state == UNDER_REVIEW and previous != UNDER_REVIEW:
			self.start_review_checks().throw_if_failed()
			self.review_date = self.review_date or nowdate()
			self.reviewer = self.reviewer or frappe.session.user
		self.fill_lines()
		self.refresh_annexures()
		self.refresh_matching()
		self.refresh_mtc_age()
		if state in DECIDED and previous != state and self.docstatus == 0:
			self.decision_checks(state).throw_if_failed()

	def before_submit(self):
		self.decision_checks(self.get("workflow_state")).throw_if_failed()

	# ------------------------------------------------------------------ SMR-01 lines
	@frappe.whitelist()
	def pull_lines(self):
		self.set("items", [])
		for line in po_lines(self.supplier_po):
			open_qty = flt(line.qty) - flt(line.received_qty)
			if open_qty > 0:
				self.append(
					"items", {"po_item": line.name, "line_ref": line.line_ref, "qty_offered": open_qty}
				)

	def fill_lines(self):
		lines = {line.line_ref: line for line in po_lines(self.supplier_po)}
		for row in self.items:
			row.line_ref = str(row.line_ref or "").strip()
			line = lines.get(row.line_ref)
			if not line:
				frappe.throw(
					_("Row {0}: PO line {1} is not on {2}.").format(row.idx, row.line_ref, self.supplier_po)
				)
			row.po_item = line.name
			row.item_code = line.item_code
			row.specification = line.pvfss_specification
			if flt(row.qty_offered) > flt(line.qty) - flt(line.received_qty) + QTY_TOLERANCE:
				frappe.throw(
					_("Row {0}: offered qty {1} is more than the open PO qty {2}.").format(
						row.idx, row.qty_offered, flt(line.qty) - flt(line.received_qty)
					)
				)
			if row.line_result == REJECTED:
				row.accepted_qty = 0
			elif row.line_result in (ACCEPTED, "Accepted with remark") and not flt(row.accepted_qty):
				row.accepted_qty = row.qty_offered

	# ------------------------------------------------------------------ SMR-02 annexures
	def refresh_annexures(self):
		if self.tally_sheet and not any(
			a.annexure_type == "Tally Sheet" and a.reference_name == self.tally_sheet for a in self.annexures
		):
			self.append(
				"annexures",
				{
					"annexure_type": "Tally Sheet",
					"reference_doctype": "Tally Sheet",
					"reference_name": self.tally_sheet,
					"received": 1,
				},
			)
		received = sum(1 for a in self.annexures if a.received)
		self.annexure_progress = f"{received}/{len(self.annexures)}"

	def start_review_checks(self):
		result = GateResult(_("SMR cannot go Under Review"), doc=self)
		for kind in REQUIRED_ANNEXURES:
			result.check(
				any(a.annexure_type == kind and a.received for a in self.annexures),
				_("{0} annexure not received").format(_(kind)),
				rule="SMR-02",
			)
		return result

	# ------------------------------------------------------------------ SMR-04 matching
	def tally_lines(self):
		if not self.tally_sheet:
			return []
		return frappe.get_all(
			"Tally Line",
			filters={"parent": self.tally_sheet, "parenttype": "Tally Sheet"},
			fields=["po_line_ref", "item_code", "heat_no", "heat_number", "qty"],
			order_by="idx",
		)

	def linked_mtcs(self):
		return {a.reference_name for a in self.annexures if a.reference_doctype == "MTC" and a.reference_name}

	@frappe.whitelist()
	def run_matching(self):
		self.refresh_matching()
		self.refresh_mtc_age()
		return [m.as_dict() for m in self.matching]

	def refresh_matching(self):
		"""Tally <-> MTC: heat on an MTC for the item, MTC qty per heat, tally total = offered qty."""
		tally = self.tally_lines()
		kept = {m.key: m for m in self.matching}
		mtc_heats = heats_for({t.heat_no for t in tally}, self.supplier_po)
		linked = self.linked_mtcs()
		rows = []

		per_heat = {}
		for t in tally:
			key = (t.po_line_ref, t.heat_no)
			per_heat.setdefault(key, {"qty": 0.0, "item": t.item_code, "heat_number": t.heat_number})
			per_heat[key]["qty"] += flt(t.qty)
		heat_totals = {}
		for (_line, heat_no), v in per_heat.items():
			heat_totals[heat_no] = heat_totals.get(heat_no, 0) + v["qty"]

		for (line_ref, heat_no), v in per_heat.items():
			candidates = [
				r for r in mtc_heats.get(heat_no, []) if r.same_po and (not linked or r.mtc in linked)
			]
			for_item = [r for r in candidates if r.item_code == v["item"]]
			row = {
				"line_ref": line_ref,
				"heat_number": v["heat_number"],
				"tally_qty": v["qty"],
				"key": f"{line_ref}|{heat_no}",
			}
			if not candidates:
				row.update(result="Heat not on MTC", grade=None)
			elif not for_item:
				mtc = candidates[0]
				row.update(
					result="Grade mismatch",
					mtc=mtc.mtc,
					mtc_qty=mtc.qty,
					grade=_("{0} on tally, {1} on MTC {2}").format(
						v["item"], mtc.item_code, mtc.certificate_no
					),
				)
			else:
				mtc = for_item[0]
				mtc_qty = sum(flt(r.qty) for r in for_item)
				row.update(mtc=mtc.mtc, mtc_qty=mtc_qty, grade=mtc.grade)
				over = mtc_qty and heat_totals[heat_no] > mtc_qty + QTY_TOLERANCE
				row["result"] = "Qty mismatch" if over else MATCH
			rows.append(row)

		totals = {}
		for t in tally:
			totals[t.po_line_ref] = totals.get(t.po_line_ref, 0) + flt(t.qty)
		for item in self.items:
			item.tally_qty = totals.get(item.line_ref, 0)
			if tally and abs(flt(item.tally_qty) - flt(item.qty_offered)) > QTY_TOLERANCE:
				rows.append(
					{
						"line_ref": item.line_ref,
						"tally_qty": item.tally_qty,
						"result": "Qty mismatch",
						"grade": _("Tally total {0} vs offered {1}").format(item.tally_qty, item.qty_offered),
						"key": f"{item.line_ref}|total",
					}
				)

		self.set("matching", [])
		for row in rows:
			old = kept.get(row["key"])
			if old and old.remark:
				row["remark"] = old.remark
				row["accepted_by"] = old.accepted_by or frappe.session.user
			self.append("matching", row)
		self.match_issues = sum(1 for m in self.matching if m.result != MATCH and not m.remark)
		if self.tally_sheet:
			summary = _("{0} issues").format(self.match_issues) if self.match_issues else _("All match")
			frappe.db.set_value(
				"Tally Sheet", self.tally_sheet, "match_summary", summary, update_modified=False
			)

	# ------------------------------------------------------------------ SMR-20 MTC age
	def age_checks(self):
		"""{line_ref: [age check dicts]} for every heat on the tally."""
		ref_date = mtc_age.reference_date(self.review_date)
		lines = {line.line_ref: line for line in po_lines(self.supplier_po)}
		out = {}
		for m in self.matching:
			if not m.mtc or m.result == "Heat not on MTC":
				continue
			heat_label = m.heat_number or m.key.split("|", 1)[-1]
			item = lines.get(m.line_ref)
			out.setdefault(m.line_ref, []).append(
				mtc_age.check(
					m.mtc,
					heat_label,
					item.item_code if item else None,
					ref_date,
					project=self.project,
					po_item=item,
				)
			)
		return out

	def refresh_mtc_age(self):
		checks = self.age_checks()
		on_mtc = total = 0
		for item in self.items:
			rows = checks.get(item.line_ref, [])
			heats = [m for m in self.matching if m.line_ref == item.line_ref and not m.key.endswith("|total")]
			missing = sum(1 for m in heats if m.result == "Heat not on MTC")
			total += len(heats)
			on_mtc += len(heats) - missing
			item.mtc_status = (
				_("{0} heats without MTC").format(missing) if missing else (_("On MTC") if heats else None)
			)
			worst = max(rows, key=lambda r: (r["over"], r["age"]), default=None)
			item.mtc_age = worst and worst.get("display")
			item.over_age = int(bool(worst and worst["over"]))
		over = sum(1 for i in self.items if i.over_age)
		self.mtc_summary = _("{0}/{1} heats on MTC").format(on_mtc, total) + (
			_(", {0} lines over age").format(over) if over else ""
		)

	# ------------------------------------------------------------------ decision
	def outcome(self):
		results = {r.line_result for r in self.items}
		if results <= {REJECTED}:
			return REJECTED
		if results <= {ACCEPTED, "Accepted with remark"}:
			return ACCEPTED
		return PARTIAL

	def decision_checks(self, state):
		result = GateResult(_("SMR cannot be closed"), doc=self)
		pending = [r.line_ref for r in self.items if r.line_result in (None, "", "Pending")]
		result.check(
			not pending, _("Lines without a result: {0}").format(", ".join(pending)), rule="SCR-SMR-02"
		)
		accepted = {r.line_ref for r in self.items if r.line_result not in (REJECTED, "Pending", None, "")}
		for m in self.matching:
			if m.line_ref in accepted and m.result != MATCH:
				result.check(
					bool(m.remark),
					_("Line {0} heat {1}: {2} must be resolved or accepted with a remark").format(
						m.line_ref, m.heat_number or "-", _(m.result)
					),
					rule="SMR-04",
				)
		checks = self.age_checks()
		for row in self.items:
			if row.line_ref not in accepted:
				continue
			if row.line_result == "Accepted with remark":
				result.check(bool(row.remark), _("Line {0}: enter the remark").format(row.line_ref))
			for c in checks.get(row.line_ref, []):
				if not c["over"]:
					continue
				waived = row.waiver_by and row.waiver_customer_ref
				result.check(
					bool(row.retest_report or waived),
					c["message"] + " " + _("Link a re-test report or record a Director waiver."),
					doctype="MTC",
					name=c["mtc"],
					rule="SMR-20",
				)
		if not pending and state in DECIDED:
			expected = self.outcome()
			result.check(
				state == expected,
				_("The line results make this SMR {0}, not {1}.").format(_(expected), _(state)),
			)
		return result


# ----------------------------------------------------------------------------- actions
def _smr(name, perm="write"):
	doc = frappe.get_doc("SMR", name)
	doc.check_permission(perm)
	return doc


@frappe.whitelist()
def waive_age(smr: str, line_ref: str, customer_ref: str):
	"""SMR-20: a Director waives the age limit on one line, quoting the customer's approval."""
	if "PVFSS Director" not in frappe.get_roles():
		frappe.throw(_("Only the Director can waive the MTC age limit."), frappe.PermissionError)
	if not (customer_ref or "").strip():
		frappe.throw(_("Enter the customer approval reference."))
	doc = _smr(smr, "read")
	row = next((r for r in doc.items if r.line_ref == line_ref), None)
	if not row:
		frappe.throw(_("Line {0} is not on {1}.").format(line_ref, smr))
	row.waiver_by = frappe.session.user
	row.waiver_customer_ref = customer_ref.strip()
	doc.flags.ignore_permissions = True
	doc.save()
	doc.add_comment("Info", _("MTC age waived on line {0}: {1}").format(line_ref, customer_ref))
	return row.waiver_by


@frappe.whitelist()
def make_tally_sheet(smr: str):
	"""SCR-SMR-02 "Import Tally Sheet": a draft Tally Sheet for this SMR, linked as an annexure."""
	doc = _smr(smr)
	if doc.tally_sheet and frappe.db.exists("Tally Sheet", {"name": doc.tally_sheet, "docstatus": ["<", 2]}):
		return doc.tally_sheet
	ts = frappe.get_doc(
		{
			"doctype": "Tally Sheet",
			"source_type": "SMR",
			"source_doctype": "SMR",
			"source_document": doc.name,
			"supplier_po": doc.supplier_po,
			"tally_template": frappe.db.get_value("Tally Template", {"supplier": doc.supplier}),
			"lines": [],
		}
	)
	ts.flags.ignore_mandatory = True
	ts.insert()
	doc.tally_sheet = ts.name
	doc.save()
	return ts.name


@frappe.whitelist()
def make_purchase_receipt(smr: str):
	"""SMR-30: a draft Purchase Receipt into the stock location, one batch per tally lot."""
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt as make_pr

	from pvfss.pvfss_quality import traceability

	doc = _smr(smr, "read")
	frappe.has_permission("Purchase Receipt", "create", throw=True)
	if doc.docstatus != 1 or doc.get("workflow_state") not in (ACCEPTED, PARTIAL):
		frappe.throw(_("Create the receipt after the SMR is accepted."))
	if (
		doc.purchase_receipt
		and frappe.db.get_value("Purchase Receipt", doc.purchase_receipt, "docstatus") < 2
	):
		return doc.purchase_receipt

	accepted = {r.po_item: r for r in doc.items if flt(r.accepted_qty) > 0}
	lots = {}
	if doc.tally_sheet:
		for t in frappe.get_all(
			"Tally Line",
			filters={"parent": doc.tally_sheet, "parenttype": "Tally Sheet"},
			fields=["po_line_ref", "heat_number", "heat_no", "lot_no", "qty", "item_code"],
			order_by="idx",
		):
			lots.setdefault(t.po_line_ref, []).append(t)

	pr = make_pr(doc.supplier_po)
	pr.set_warehouse = doc.stock_location
	rows = []
	for row in pr.items:
		line = accepted.get(row.purchase_order_item)
		if not line:
			continue
		base = row.as_dict()
		for key in ("name", "idx", "serial_and_batch_bundle"):
			base.pop(key, None)
		base["warehouse"] = doc.stock_location
		if not traceability.is_heat_traceable(row.item_code) or not lots.get(line.line_ref):
			rows.append(_qty(base, line.accepted_qty))
			continue
		remaining = flt(line.accepted_qty)
		for lot in lots[line.line_ref]:
			if remaining <= QTY_TOLERANCE:
				break
			if not lot.heat_number:
				frappe.throw(
					_("Line {0}: heat {1} has no Heat Number. Submit its MTC first.").format(
						line.line_ref, lot.heat_no
					)
				)
			qty = min(flt(lot.qty), remaining)
			remaining -= qty
			rows.append(
				_qty(
					dict(base),
					qty,
					use_serial_batch_fields=1,
					batch_no=lot_batch(lot, doc.tally_sheet, doc.supplier_po),
				)
			)
	if not rows:
		frappe.throw(_("No accepted quantity to receive."))
	pr.set("items", [])
	for row in rows:
		pr.append("items", row)
	pr.pvfss_smr = doc.name
	pr.insert()
	doc.db_set("purchase_receipt", pr.name)
	return pr.name


def _qty(row, qty, **extra):
	factor = flt(row.get("conversion_factor")) or 1
	row.update(qty=flt(qty), received_qty=flt(qty), stock_qty=flt(qty) * factor, **extra)
	row["received_stock_qty"] = row["stock_qty"]
	return row


def lot_batch(lot, tally_sheet, supplier_po):
	"""TRC-02: the batch for one tally lot (heat + lot), created when new."""
	name = frappe.db.get_value(
		"Batch",
		{"pvfss_heat_number": lot.heat_number, "pvfss_lot_no": lot.lot_no or "1", "item": lot.item_code},
	)
	if name:
		return name
	return (
		frappe.get_doc(
			{
				"doctype": "Batch",
				"item": lot.item_code,
				"pvfss_heat_number": lot.heat_number,
				"pvfss_lot_no": lot.lot_no or "1",
				"pvfss_tally_sheet": tally_sheet,
				"pvfss_supplier_po": supplier_po,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
