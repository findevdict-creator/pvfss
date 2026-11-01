"""Supplier tally sheet import with a saved column mapping per supplier (SMR-03, SCR-SMR-04)."""

import frappe
from frappe import _

from pvfss.utils.line_import import read_rows, template_response

FIELDS = {
	"po_line_ref": ("PO Line", "line", "po line no", "line ref", "item no"),
	"item_code": ("Item Code", "item"),
	"heat_no": ("Heat No", "heat", "heat number", "cast no"),
	"lot_no": ("Lot No", "lot", "bundle", "bundle no"),
	"size": ("Size",),
	"pieces": ("Pieces", "pcs", "nos", "qty pcs"),
	"length_per_piece": ("Length per Piece", "length", "length m"),
	"total_length": ("Total Length", "total length m"),
	"weight": ("Weight", "weight kg", "kg"),
	"marking": ("Marking",),
}
NUMERIC = ("pieces", "length_per_piece", "total_length", "weight")


def columns(template=None):
	cols = {field: list(labels) for field, labels in FIELDS.items()}
	if template:
		for row in frappe.get_doc("Tally Template", template).columns:
			cols[row.target_field].insert(0, row.source_heading)
	return [(field, *labels) for field, labels in cols.items()]


@frappe.whitelist()
def download_template():
	template_response(
		"PVFSS Tally Sheet.xlsx",
		[(f, labels[0]) for f, labels in FIELDS.items()],
		[["1", "", "7A1234", "L1", "6in SCH40", 10, 12, "", 3400, "ASTM A106 B 7A1234"]],
	)


def _number(value):
	if value in (None, ""):
		return None
	try:
		return float(str(value).replace(",", "").strip())
	except ValueError:
		return None


def parse(file_url, template=None):
	rows = read_rows(file_url, columns(template))
	ok = errors = 0
	for row in rows:
		problems = []
		ref = row.get("po_line_ref")
		if isinstance(ref, float) and ref.is_integer():
			ref = int(ref)
		row["po_line_ref"] = str(ref).strip() if ref not in (None, "") else None
		if not str(row.get("heat_no") or "").strip():
			problems.append(_("Heat number missing"))
		for field in NUMERIC:
			raw = row.get(field)
			value = _number(raw)
			if raw not in (None, "") and value is None:
				problems.append(_("{0} is not a number").format(FIELDS[field][0]))
			row[field] = value
		if row.get("pieces") is not None:
			row["pieces"] = int(row["pieces"])
		if not row.get("po_line_ref") and not row.get("item_code"):
			problems.append(_("PO line or item code required"))
		if row.get("item_code") and not frappe.db.exists("Item", row["item_code"]):
			problems.append(_("Item '{0}' not found").format(row["item_code"]))
		row["status"] = "Error" if problems else "OK"
		row["message"] = "; ".join(problems)
		errors += bool(problems)
		ok += not problems
	return rows, ok, errors


@frappe.whitelist()
def preview(tally_sheet: str, file_url: str, template: str | None = None):
	doc = frappe.get_doc("Tally Sheet", tally_sheet)
	doc.check_permission("write")
	rows, ok, errors = parse(file_url, template or doc.tally_template)
	return {"rows": rows, "ok": ok, "errors": errors}


@frappe.whitelist()
def import_lines(tally_sheet: str, file_url: str, template: str | None = None, replace: int | str = 1):
	"""Write the OK rows to the tally sheet. Returns the number of lines imported."""
	doc = frappe.get_doc("Tally Sheet", tally_sheet)
	doc.check_permission("write")
	rows, ok, _errors = parse(file_url, template or doc.tally_template)
	if not ok:
		frappe.throw(_("No valid rows to import."))
	if frappe.utils.cint(replace):
		doc.set("lines", [])
	for row in rows:
		if row["status"] == "OK":
			doc.append("lines", {k: row.get(k) for k in FIELDS})
	if template:
		doc.tally_template = template
	doc.source_file = file_url
	doc.save()
	return ok


@frappe.whitelist()
def save_template(template_name: str, supplier: str | None = None, mapping: str | dict | None = None):
	"""Save a supplier's column headings once (SMR-03): mapping = {target_field: heading}."""
	frappe.has_permission("Tally Template", "create", throw=True)
	mapping = frappe.parse_json(mapping) if isinstance(mapping, str) else (mapping or {})
	doc = (
		frappe.get_doc("Tally Template", template_name)
		if frappe.db.exists("Tally Template", template_name)
		else frappe.new_doc("Tally Template")
	)
	doc.template_name = template_name
	doc.supplier = supplier
	doc.set(
		"columns",
		[{"target_field": f, "source_heading": h} for f, h in mapping.items() if f in FIELDS and h],
	)
	doc.save()
	return doc.name
