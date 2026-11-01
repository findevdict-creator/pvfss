# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from pvfss.pvfss_quality import traceability
from pvfss.pvfss_quality.doctype.heat_number.heat_number import clean_heat_no
from pvfss.pvfss_quality.doctype.mtc.mtc import heats_for

LENGTH_UOMS = ("Meter", "Metre", "m", "Foot", "Feet")
SOURCE_DOCTYPES = {"SMR": "SMR", "Purchase Receipt": "Purchase Receipt", "Inspection": None}


class TallySheet(Document):
	"""Supplier tally sheet: heats and lots per PO line (SMR-03, SCR-SMR-04)."""

	def validate(self):
		self.source_doctype = SOURCE_DOCTYPES.get(self.source_type)
		lines = po_lines(self.supplier_po)
		by_ref = {line.line_ref: line for line in lines}
		mtc_heats = heats_for({clean_heat_no(r.heat_no) for r in self.lines}, self.supplier_po)
		for row in self.lines:
			row.heat_no = clean_heat_no(row.heat_no)
			row.lot_no = (row.lot_no or "").strip() or None
			row.po_line_ref = str(row.po_line_ref or "").strip() or None
			if row.po_line_ref and row.po_line_ref not in by_ref:
				frappe.throw(
					_("Row {0}: PO line {1} is not on {2}.").format(
						row.idx, row.po_line_ref, self.supplier_po
					)
				)
			if row.po_line_ref and not row.item_code:
				row.item_code = by_ref[row.po_line_ref].item_code
			if not row.po_line_ref:
				same_item = [line for line in lines if line.item_code == row.item_code]
				if len(same_item) == 1:
					row.po_line_ref = same_item[0].line_ref
			if row.pieces and row.length_per_piece:
				row.total_length = flt(row.pieces) * flt(row.length_per_piece)
			if not flt(row.qty):
				uom = frappe.get_cached_value("Item", row.item_code, "stock_uom")
				row.qty = flt(row.total_length) if uom in LENGTH_UOMS else flt(row.pieces)
			row.heat_number = resolve_heat(row.heat_no, row.item_code, mtc_heats)
		self.heat_count = len({r.heat_no for r in self.lines})
		self.total_length = sum(flt(r.total_length) for r in self.lines)
		self.total_weight = sum(flt(r.weight) for r in self.lines)

	def totals_by_line(self):
		out = {}
		for row in self.lines:
			out[row.po_line_ref] = out.get(row.po_line_ref, 0) + flt(row.qty)
		return out


def resolve_heat(heat_no, item_code, mtc_heats):
	"""TRC-01: the Heat Number for a tally heat, created from its MTC when it is new."""
	rows = mtc_heats.get(heat_no) or []
	for row in rows:
		if row.heat_number:
			return row.heat_number
	if rows:
		return traceability.get_or_create_heat(
			heat_no, rows[0].manufacturer, item_code, grade=rows[0].grade, mtc=rows[0].certificate_no
		)
	existing = frappe.get_all("Heat Number", filters={"heat_no": heat_no}, pluck="name", limit=2)
	return existing[0] if len(existing) == 1 else None


def po_lines(supplier_po):
	"""PO lines with a line ref: the customer line ref, else the row number."""
	if not supplier_po:
		return []
	rows = frappe.get_all(
		"Purchase Order Item",
		filters={"parent": supplier_po, "parenttype": "Purchase Order"},
		fields=[
			"name",
			"idx",
			"item_code",
			"qty",
			"stock_qty",
			"received_qty",
			"pvfss_customer_line_ref",
			"pvfss_specification",
			"pvfss_product_category",
			"pvfss_material_type",
		],
		order_by="idx",
	)
	for row in rows:
		row.line_ref = row.pvfss_customer_line_ref or str(row.idx)
	return rows
