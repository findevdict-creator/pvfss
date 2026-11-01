# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
"""Competitive Statement (RFQ-07, SCR-RFQ-08): supplier quotations side by side per inquiry line.

Prices are shown in AED (each quotation's own exchange rate) or in the quotation currency.
The lowest compliant price and best lead time per line are flagged for the client to
highlight; the radio column selects the line (RFQ-08).
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from pvfss.pvfss_crm import selection

SHORT = {"Ready stock": "RS", "Manufacture": "MFG", "Compliant": "C", "Deviation": "D", "Not compliant": "NC"}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.inquiry:
		return [], []
	frappe.has_permission("Opportunity", "read", filters.inquiry, throw=True)
	data, quotations = build(filters)
	return get_columns(quotations, filters), data, None, None, summary(quotations)


def build(filters):
	in_aed = (filters.show_in or "AED") == "AED"
	only_compliant = cint(filters.only_compliant)
	inquiry = frappe.get_doc("Opportunity", filters.inquiry)
	lines = selection.quotation_lines(inquiry.name, include_cancelled=cint(filters.include_cancelled))

	quotations = {}
	for line in lines:
		q = quotations.setdefault(
			line.supplier_quotation,
			frappe._dict(
				name=line.supplier_quotation,
				key=frappe.scrub(line.supplier_quotation),
				supplier=line.supplier,
				supplier_name=line.supplier_name,
				currency=line.currency,
				valid_till=line.valid_till,
				validity_passed=selection.validity_passed(line.valid_till),
				docstatus=line.docstatus,
				total=0.0,
				quoted=0,
				compliant=0,
				lowest=0,
			),
		)
		q.setdefault("lines", {})[line.line_ref] = line

	best_price = selection.lowest_compliant(lines)
	best_lead = {}
	for line in lines:
		if selection.is_quoted(line) and line.compliance != "Not compliant" and cint(line.lead_time_days):
			if line.line_ref not in best_lead or cint(line.lead_time_days) < best_lead[line.line_ref]:
				best_lead[line.line_ref] = cint(line.lead_time_days)

	data = []
	for item in inquiry.items:
		ref = item.pvfss_customer_line_ref
		row = frappe._dict(
			line_ref=ref,
			specification=item.pvfss_specification or item.description,
			qty=item.qty,
			uom=item.uom,
		)
		selected = None
		for q in quotations.values():
			line = q.get("lines", {}).get(ref)
			if not line:
				continue
			k = q.key
			quoted = selection.is_quoted(line)
			if quoted and not (only_compliant and line.compliance == "Not compliant"):
				row[f"{k}_price"] = flt(line.base_rate if in_aed else line.rate)
				row[f"{k}_lead"] = cint(line.lead_time_days) or None
				row[f"{k}_avail"] = SHORT.get(line.availability, line.availability)
				row[f"{k}_comp"] = SHORT.get(line.compliance, line.compliance)
				row[f"{k}_lowest"] = (
					1 if best_price.get(ref) and best_price[ref].sq_item == line.sq_item else 0
				)
				row[f"{k}_bestlead"] = (
					1 if cint(line.lead_time_days) and best_lead.get(ref) == cint(line.lead_time_days) else 0
				)
			elif not quoted:
				row[f"{k}_avail"] = _("No quote")
			row[f"{k}_sel"] = cint(line.selected)
			row[f"{k}_item"] = line.sq_item
			if quoted:
				q.quoted += 1
				q.total += flt(line.base_rate) * flt(line.qty)
				if line.compliance == "Compliant":
					q.compliant += 1
				if row.get(f"{k}_lowest"):
					q.lowest += 1
			if cint(line.selected):
				selected = (q, line)

		low = best_price.get(ref)
		row.lowest_supplier = low.supplier if low else None
		row.lowest_price = flt(low.base_rate) if low else None
		if selected:
			row.selected_supplier = selected[0].supplier
			row.selected_price = flt(selected[1].base_rate)
			row.difference = flt(row.selected_price) - flt(row.lowest_price) if low else None
		data.append(row)

	total_lines = len(inquiry.items)
	footer = {
		"total": _("Total AED"),
		"quoted": _("Lines quoted"),
		"compliant": _("Lines compliant"),
		"lowest": _("Lines lowest"),
	}
	for key, label in footer.items():
		row = frappe._dict(line_ref="", specification=label, is_footer=1)
		for q in quotations.values():
			if key == "total":
				row[f"{q.key}_price"] = flt(q.total, 2)
			else:
				row[f"{q.key}_avail"] = f"{q[key]} / {total_lines}"
		data.append(row)
	return data, list(quotations.values())


def get_columns(quotations, filters):
	in_aed = (filters.show_in or "AED") == "AED"
	cols = [
		{"label": _("Line"), "fieldname": "line_ref", "fieldtype": "Data", "width": 60},
		{"label": _("Specification"), "fieldname": "specification", "fieldtype": "Data", "width": 220},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 70},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 60},
	]
	for q in quotations:
		head = f"{q.supplier_name or q.supplier} ({q.name})"
		if q.validity_passed:
			head += " ⚠"
		if q.docstatus == 0:
			head += " " + _("[draft]")
		currency = "AED" if in_aed else q.currency
		cols += [
			{
				"label": f"{head}: {_('Price')} {currency}",
				"fieldname": f"{q.key}_price",
				"fieldtype": "Float",
				"precision": 2,
				"width": 110,
			},
			{"label": _("Lead"), "fieldname": f"{q.key}_lead", "fieldtype": "Int", "width": 60},
			{"label": _("Avail"), "fieldname": f"{q.key}_avail", "fieldtype": "Data", "width": 70},
			{"label": _("Comp"), "fieldname": f"{q.key}_comp", "fieldtype": "Data", "width": 55},
			{"label": _("Sel"), "fieldname": f"{q.key}_sel", "fieldtype": "Check", "width": 45},
		]
	cols += [
		{
			"label": _("Lowest Compliant Supplier"),
			"fieldname": "lowest_supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 160,
		},
		{
			"label": _("Lowest Price AED"),
			"fieldname": "lowest_price",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Selected Supplier"),
			"fieldname": "selected_supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 160,
		},
		{
			"label": _("Selected Price AED"),
			"fieldname": "selected_price",
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"label": _("Difference AED"),
			"fieldname": "difference",
			"fieldtype": "Float",
			"precision": 2,
			"width": 100,
		},
	]
	return cols


def summary(quotations):
	return [
		{
			"label": q.supplier_name or q.supplier,
			"value": flt(q.total, 2),
			"datatype": "Currency",
			"currency": "AED",
			"indicator": "Green" if q.lowest else "Blue",
		}
		for q in quotations
	]
