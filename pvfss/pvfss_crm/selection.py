"""Supplier line selection per inquiry line (RFQ-07, RFQ-08, SCR-RFQ-08).

An inquiry line is identified by its customer line ref (GEN-50), which every RFQ and
Supplier Quotation line carries. Exactly one Supplier Quotation line may be selected per
inquiry line across all quotations of the inquiry.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

LIVE = (0, 1)  # draft and submitted quotations take part; cancelled ones do not


def quotation_lines(inquiry, include_cancelled=False):
	"""All Supplier Quotation lines of an inquiry, with header data, oldest quotation first."""
	docstatus = (0, 1, 2) if include_cancelled else LIVE
	return frappe.db.sql(
		"""
		select sq.name as supplier_quotation, sq.supplier, sq.supplier_name, sq.currency,
			sq.conversion_rate, sq.valid_till, sq.docstatus, sq.transaction_date,
			sqi.name as sq_item, sqi.pvfss_customer_line_ref as line_ref, sqi.item_code,
			sqi.qty, sqi.uom, sqi.rate, sqi.base_rate, sqi.lead_time_days,
			sqi.pvfss_availability as availability, sqi.pvfss_compliance as compliance,
			sqi.pvfss_no_quote as no_quote, sqi.pvfss_selected as selected,
			sqi.pvfss_manufacturer as manufacturer, sqi.pvfss_origin as origin,
			sqi.pvfss_deviation_note as deviation_note
		from `tabSupplier Quotation Item` sqi
		join `tabSupplier Quotation` sq on sq.name = sqi.parent
		where sq.opportunity = %(inquiry)s and sq.docstatus in %(docstatus)s
		order by sq.creation, sqi.idx
		""",
		{"inquiry": inquiry, "docstatus": docstatus},
		as_dict=True,
	)


def is_quoted(line):
	return not cint(line.no_quote) and flt(line.rate) > 0


def lowest_compliant(lines):
	"""{line_ref: line} with the lowest AED price among quoted, Compliant lines."""
	best = {}
	for line in lines:
		if not is_quoted(line) or line.compliance != "Compliant" or line.docstatus != 1:
			continue
		current = best.get(line.line_ref)
		if current is None or flt(line.base_rate) < flt(current.base_rate):
			best[line.line_ref] = line
	return best


def _check_write(sq):
	if not frappe.has_permission("Supplier Quotation", "write", sq):
		frappe.throw(_("Not permitted to select lines on {0}.").format(sq), frappe.PermissionError)


def _set_selected(sq_item, value):
	frappe.db.set_value("Supplier Quotation Item", sq_item, "pvfss_selected", cint(value))


def _refresh_counts(quotations):
	for sq in set(quotations):
		count = frappe.db.count("Supplier Quotation Item", {"parent": sq, "pvfss_selected": 1})
		frappe.db.set_value("Supplier Quotation", sq, "pvfss_lines_selected", count)


@frappe.whitelist()
def select_line(sq_item):
	"""Select one supplier line for its inquiry line, unselecting any other supplier's line."""
	row = frappe.db.get_value(
		"Supplier Quotation Item",
		sq_item,
		["parent", "pvfss_customer_line_ref", "pvfss_no_quote", "rate"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Supplier Quotation line {0} not found.").format(sq_item))
	header = frappe.db.get_value("Supplier Quotation", row.parent, ["opportunity", "docstatus"], as_dict=True)
	if header.docstatus == 2:
		frappe.throw(_("{0} is cancelled.").format(row.parent))
	if not header.opportunity:
		frappe.throw(_("{0} is not linked to an inquiry.").format(row.parent))
	if cint(row.pvfss_no_quote) or not flt(row.rate):
		frappe.throw(_("Line {0} was not quoted on {1}.").format(row.pvfss_customer_line_ref, row.parent))
	_check_write(row.parent)

	touched = [row.parent]
	for other in quotation_lines(header.opportunity):
		if other.line_ref == row.pvfss_customer_line_ref and other.selected and other.sq_item != sq_item:
			_check_write(other.supplier_quotation)
			_set_selected(other.sq_item, 0)
			touched.append(other.supplier_quotation)
	_set_selected(sq_item, 1)
	_refresh_counts(touched)
	return {"inquiry": header.opportunity, "line_ref": row.pvfss_customer_line_ref}


@frappe.whitelist()
def unselect_line(sq_item):
	parent = frappe.db.get_value("Supplier Quotation Item", sq_item, "parent")
	_check_write(parent)
	_set_selected(sq_item, 0)
	_refresh_counts([parent])


@frappe.whitelist()
def select_lowest(inquiry, preview=1):
	"""Select the lowest compliant line for every inquiry line. With ``preview`` only report."""
	frappe.has_permission("Opportunity", "read", inquiry, throw=True)
	best = lowest_compliant(quotation_lines(inquiry))
	result = [
		{
			"line_ref": ref,
			"supplier": line.supplier,
			"supplier_quotation": line.supplier_quotation,
			"sq_item": line.sq_item,
			"base_rate": line.base_rate,
		}
		for ref, line in sorted(best.items(), key=lambda kv: _ref_key(kv[0]))
	]
	if not cint(preview):
		for row in result:
			select_line(row["sq_item"])
	return result


@frappe.whitelist()
def clear_selection(inquiry):
	frappe.has_permission("Opportunity", "read", inquiry, throw=True)
	touched = []
	for line in quotation_lines(inquiry):
		if line.selected:
			_check_write(line.supplier_quotation)
			_set_selected(line.sq_item, 0)
			touched.append(line.supplier_quotation)
	_refresh_counts(touched)
	return len(touched)


def selected_lines(inquiry):
	"""The selected supplier line per inquiry line ref (from submitted quotations only)."""
	return {line.line_ref: line for line in quotation_lines(inquiry) if line.selected and line.docstatus == 1}


def assert_single_selection(doc):
	"""RFQ-08 [RULE] on the Supplier Quotation form itself."""
	if not doc.get("opportunity"):
		return
	seen = set()
	for row in doc.items:
		if not cint(row.pvfss_selected):
			continue
		ref = row.pvfss_customer_line_ref
		if ref in seen:
			frappe.throw(_("Line {0} is selected twice on this quotation.").format(ref))
		seen.add(ref)
		for other in quotation_lines(doc.opportunity):
			if other.supplier_quotation != doc.name and other.line_ref == ref and other.selected:
				frappe.throw(
					_("Line {0} is already selected on {1} ({2}). Unselect it there first.").format(
						ref, other.supplier_quotation, other.supplier
					),
					title=_("Single selection per line"),
				)


def validity_passed(valid_till):
	return bool(valid_till and getdate(valid_till) < getdate(nowdate()))


def _ref_key(ref):
	ref = ref or ""
	return (0, float(ref), "") if ref.replace(".", "", 1).isdigit() else (1, 0, ref)
