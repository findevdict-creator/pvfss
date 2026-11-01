"""Import inquiry lines from the PVFSS Excel template (CRM-04, SCR-CRM-03)."""

import frappe
from frappe import _

from pvfss.utils import settings
from pvfss.utils.line_import import read_rows, template_response, to_float

COLUMNS = [
	("pvfss_customer_line_ref", "Line Ref", "line no", "item no", "line"),
	("item_code", "Item Code", "item"),
	("description", "Description"),
	("pvfss_specification", "Specification", "spec"),
	("qty", "Qty", "quantity"),
	("uom", "UOM", "unit"),
	("pvfss_material_type", "Material Type", "material"),
	("pvfss_product_category", "Product Category", "category", "item group"),
	("pvfss_inspection_req", "Inspection Req", "inspection requirement", "inspection"),
	("pvfss_doc_req", "Doc Req", "document requirement", "documents"),
]

MATERIAL_TYPES = ("CS", "SS", "Alloy", "Other")
UOM_ALIASES = {
	"m": "Meter",
	"mtr": "Meter",
	"mtrs": "Meter",
	"meter": "Meter",
	"meters": "Meter",
	"metre": "Meter",
	"no": "Nos",
	"nos": "Nos",
	"pc": "Nos",
	"pcs": "Nos",
	"ea": "Nos",
	"each": "Nos",
	"kg": "Kg",
	"kgs": "Kg",
	"t": "Ton",
	"ton": "Ton",
	"tons": "Ton",
	"mt": "Ton",
	"set": "Set",
	"sets": "Set",
}


@frappe.whitelist()
def download_template():
	template_response(
		"PVFSS Inquiry Lines.xlsx",
		COLUMNS,
		[
			[
				"1",
				"",
				"Pipe, seamless",
				"ASTM A106 Gr.B, 6in, SCH40, BE",
				120,
				"Meter",
				"CS",
				"Pipes - CS",
				"Hydro test, TPI witness",
				"MTC 3.1",
			]
		],
	)


def _uom(value):
	if not value:
		return None
	value = str(value).strip()
	if frappe.db.exists("UOM", value):
		return value
	return UOM_ALIASES.get(value.lower())


def parse(file_url, existing_refs=()):
	"""Validate every row; returns (rows, ok_count, error_count). Nothing is written."""
	generic = settings.get_value("generic_inquiry_item")
	rows = read_rows(file_url, COLUMNS)
	seen = set(existing_refs)
	ok = errors = 0
	for row in rows:
		problems = []
		ref = str(row.get("pvfss_customer_line_ref") or "").strip()
		if (
			isinstance(row.get("pvfss_customer_line_ref"), float)
			and row["pvfss_customer_line_ref"].is_integer()
		):
			ref = str(int(row["pvfss_customer_line_ref"]))
		row["pvfss_customer_line_ref"] = ref
		if not ref:
			problems.append(_("Line ref missing"))
		elif ref in seen:
			problems.append(_("Duplicate line ref"))
		seen.add(ref)

		if not (row.get("pvfss_specification") or "").strip():
			problems.append(_("Specification missing"))

		qty = to_float(row.get("qty"))
		if not qty or qty <= 0:
			problems.append(_("Qty missing"))
		row["qty"] = qty

		uom = _uom(row.get("uom"))
		if row.get("uom") and not uom:
			problems.append(_("UOM '{0}' not recognised").format(row.get("uom")))
		row["uom"] = uom

		material = (row.get("pvfss_material_type") or "").strip()
		if material and material not in MATERIAL_TYPES:
			match = [m for m in MATERIAL_TYPES if m.lower() == material.lower()]
			if match:
				material = match[0]
			else:
				problems.append(_("Material type '{0}' must be CS, SS, Alloy or Other").format(material))
		row["pvfss_material_type"] = material or None

		category = row.get("pvfss_product_category")
		if category and not frappe.db.exists("Item Group", category):
			problems.append(_("Product category '{0}' not found").format(category))

		item = row.get("item_code")
		if item and not frappe.db.exists("Item", item):
			problems.append(_("Item '{0}' not found").format(item))
		row["matched_item"] = item or None
		row["item_code"] = item or generic
		if not row["item_code"]:
			problems.append(_("No generic inquiry item set in PVFSS Settings"))

		row["status"] = "Error" if problems else "OK"
		row["message"] = "; ".join(problems)
		if problems:
			errors += 1
		else:
			ok += 1
	return rows, ok, errors


@frappe.whitelist()
def preview(inquiry: str, file_url: str, replace: int | str = 0):
	doc = frappe.get_doc("Opportunity", inquiry)
	doc.check_permission("write")
	existing = () if frappe.utils.cint(replace) else [r.pvfss_customer_line_ref for r in doc.items]
	rows, ok, errors = parse(file_url, existing)
	return {"rows": rows, "ok": ok, "errors": errors}


@frappe.whitelist()
def import_lines(inquiry: str, file_url: str, replace: int | str = 0):
	"""Append (or replace with) the OK rows. Returns the number of lines imported."""
	doc = frappe.get_doc("Opportunity", inquiry)
	doc.check_permission("write")
	replace = frappe.utils.cint(replace)
	existing = () if replace else [r.pvfss_customer_line_ref for r in doc.items]
	rows, ok, _errors = parse(file_url, existing)
	if not ok:
		frappe.throw(_("No valid rows to import."))
	if replace:
		doc.set("items", [])
	for row in rows:
		if row["status"] != "OK":
			continue
		line = {
			k: row.get(k)
			for k in (
				"item_code",
				"qty",
				"pvfss_customer_line_ref",
				"pvfss_specification",
				"pvfss_material_type",
				"pvfss_product_category",
				"pvfss_inspection_req",
				"pvfss_doc_req",
			)
		}
		line["description"] = row.get("description") or row.get("pvfss_specification")
		line["item_name"] = (row.get("description") or row.get("pvfss_specification") or "")[:140]
		if row.get("uom"):
			line["uom"] = row["uom"]
		doc.append("items", line)
	doc.save()
	return ok
