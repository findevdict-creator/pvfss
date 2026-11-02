# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from pvfss.gates import g5
from pvfss.pvfss_quality.doctype.tally_sheet.tally_sheet import po_lines
from pvfss.utils import alerts


class IRN(Document):
	"""Inspection Release Note (QA-32 to QA-34, SCR-QA-18), gated by G5."""

	def validate(self):
		lines = {line.line_ref: line for line in po_lines(self.supplier_po)}
		released = released_qty(self.supplier_po, exclude=self.name)
		for row in self.lines:
			row.line_ref = str(row.line_ref or "").strip()
			line = lines.get(row.line_ref)
			if not line:
				frappe.throw(
					_("Row {0}: PO line {1} is not on {2}.").format(row.idx, row.line_ref, self.supplier_po)
				)
			row.po_item = line.name
			row.item_code = line.item_code
			row.po_qty = line.qty
			row.previously_released = released.get(line.name, 0)
			row.remaining = flt(line.qty) - flt(row.previously_released)
			if row.batch and not row.heat_number:
				row.heat_number = frappe.db.get_value("Batch", row.batch, "pvfss_heat_number")
			mtc = row.heat_number and g5.accepted_mtc(row.heat_number)
			row.mtc = mtc.name if mtc else None
		self.qty_released = sum(flt(r.qty_released) for r in self.lines)
		self.heats = len({r.heat_number for r in self.lines if r.heat_number})
		if self.docstatus == 0:
			self.refresh_gate_status()

	def refresh_gate_status(self):
		result = g5.check(self)
		for row in self.lines:
			problems = [
				f.message for f in result.failures if row.heat_number and row.heat_number in f.message
			]
			problems += [
				f.message
				for f in result.failures
				if f.message.startswith(_("Line {0}:").format(row.line_ref))
			]
			row.gate_status = "✓" if not problems else "✗ " + problems[0][:120]
		return result

	def before_submit(self):
		g5.check(self).throw_if_failed()
		self.issued_by = frappe.session.user

	def on_submit(self):
		"""QA-34: notify the Post-Bidding owner and Logistics."""
		owner = self.project and frappe.db.get_value("Project", self.project, "pvfss_post_bidding_owner")
		recipients = alerts.users_with_role("Logistics User") + ([owner] if owner else [])
		alerts.send(
			recipients,
			_("IRN {0} issued for {1}: {2:g} released on {3} heats.").format(
				self.name, self.supplier_po, flt(self.qty_released), self.heats
			),
			"IRN",
			self.name,
		)


def released_qty(supplier_po, exclude=None):
	"""{PO item row: qty released on submitted IRNs}."""
	rows = frappe.db.sql(
		"""select l.po_item, sum(l.qty_released) as qty
		from `tabIRN Line` l join `tabIRN` i on i.name = l.parent
		where i.supplier_po = %s and i.docstatus = 1 and i.name != %s
		group by l.po_item""",
		(supplier_po, exclude or ""),
		as_dict=True,
	)
	return {r.po_item: flt(r.qty) for r in rows}


@frappe.whitelist()
def check_gate(irn: str):
	"""SCR-QA-19 "Check gate": the live G5 checklist."""
	doc = frappe.get_doc("IRN", irn)
	doc.check_permission("read")
	return g5.check(doc).as_dict()


@frappe.whitelist()
def releasable_heats(supplier_po: str):
	"""SCR-QA-18 "Load releasable heats": received or tallied heats of the PO with an accepted MTC."""
	frappe.has_permission("IRN", "create", throw=True)
	lines = {line.name: line for line in po_lines(supplier_po)}
	out = []
	for b in frappe.get_all(
		"Batch",
		filters={"pvfss_supplier_po": supplier_po, "pvfss_heat_number": ["is", "set"]},
		fields=["name", "item", "pvfss_heat_number"],
	):
		mtc = g5.accepted_mtc(b.pvfss_heat_number)
		if not mtc or mtc.review_result not in ("Accepted", "Accepted with re-test"):
			continue
		line = next((line for line in lines.values() if line.item_code == b.item), None)
		qty = frappe.db.sql(
			"select sum(qty) from `tabSerial and Batch Entry` where batch_no = %s and is_cancelled = 0 and docstatus = 1",
			b.name,
		)[0][0]
		out.append(
			{
				"line_ref": line.line_ref if line else None,
				"heat_number": b.pvfss_heat_number,
				"batch": b.name,
				"qty_released": flt(qty),
				"mtc": mtc.name,
			}
		)
	return out
