"""Supplier Quotation import from the supplier's priced Excel (RFQ-06, SCR-RFQ-07).

Rows are matched to the quotation lines by customer line ref. Nothing is written until the
user applies the preview.
"""

import frappe
from frappe import _
from frappe.utils import cint

from pvfss.utils.line_import import read_rows, to_float

COLUMNS = [
	("pvfss_customer_line_ref", "Line Ref", "line no", "item no", "line"),
	("rate", "Unit Price", "rate", "price", "unit rate"),
	("currency", "Currency"),
	("lead_time_days", "Lead Time Days", "lead time", "delivery days"),
	("pvfss_availability", "Availability"),
	("pvfss_manufacturer", "Manufacturer", "mill", "make"),
	("pvfss_origin", "Origin", "country of origin"),
	("pvfss_compliance", "Compliance", "technical compliance"),
	("pvfss_deviation_note", "Deviation Note", "deviation", "deviations"),
	("pvfss_no_quote", "No Quote", "not quoted"),
]

AVAILABILITY = {
	"ready stock": "Ready stock",
	"rs": "Ready stock",
	"stock": "Ready stock",
	"manufacture": "Manufacture",
	"mfg": "Manufacture",
	"manufacturing": "Manufacture",
}
COMPLIANCE = {
	"compliant": "Compliant",
	"c": "Compliant",
	"yes": "Compliant",
	"deviation": "Deviation",
	"d": "Deviation",
	"not compliant": "Not compliant",
	"nc": "Not compliant",
	"no": "Not compliant",
}
TRUE = ("1", "y", "yes", "true", "x")


def _ref(value):
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value or "").strip()


def _country(value):
	if not value:
		return None
	value = str(value).strip()
	if frappe.db.exists("Country", value):
		return value
	return frappe.db.get_value("Country", {"code": value.lower()}, "name")


def parse(doc, file_url):
	lines = {str(r.pvfss_customer_line_ref or ""): r for r in doc.items}
	rows = read_rows(file_url, COLUMNS)
	seen = set()
	for row in rows:
		problems = []
		ref = _ref(row.get("pvfss_customer_line_ref"))
		row["pvfss_customer_line_ref"] = ref
		row["matched"] = ref in lines
		if not row["matched"]:
			problems.append(_("Line ref not on RFQ"))
		elif ref in seen:
			problems.append(_("Duplicate line ref"))
		seen.add(ref)

		no_quote = str(row.get("pvfss_no_quote") or "").strip().lower() in TRUE
		row["pvfss_no_quote"] = 1 if no_quote else 0
		rate = to_float(row.get("rate"))
		row["rate"] = rate
		if not no_quote and not rate:
			problems.append(_("Rate missing"))

		currency = (row.get("currency") or "").strip()
		if currency and currency != doc.currency:
			problems.append(
				_("Currency {0} differs from the quotation currency {1}").format(currency, doc.currency)
			)

		lead = to_float(row.get("lead_time_days"))
		row["lead_time_days"] = cint(lead) if lead else None

		avail = str(row.get("pvfss_availability") or "").strip()
		row["pvfss_availability"] = AVAILABILITY.get(avail.lower()) if avail else None
		if avail and not row["pvfss_availability"]:
			problems.append(_("Availability '{0}' not recognised").format(avail))

		comp = str(row.get("pvfss_compliance") or "").strip()
		row["pvfss_compliance"] = COMPLIANCE.get(comp.lower()) if comp else None
		if comp and not row["pvfss_compliance"]:
			problems.append(_("Compliance '{0}' not recognised").format(comp))

		origin = row.get("pvfss_origin")
		row["pvfss_origin"] = _country(origin)
		if origin and not row["pvfss_origin"]:
			problems.append(_("Origin '{0}' not found").format(origin))

		row["status"] = "Error" if problems else "OK"
		row["message"] = "; ".join(problems)
	unmatched = sorted(set(lines) - seen - {""})
	return rows, unmatched


@frappe.whitelist()
def preview(supplier_quotation, file_url):
	doc = frappe.get_doc("Supplier Quotation", supplier_quotation)
	doc.check_permission("write")
	rows, unmatched = parse(doc, file_url)
	return {
		"rows": rows,
		"ok": sum(1 for r in rows if r["status"] == "OK"),
		"errors": sum(1 for r in rows if r["status"] != "OK"),
		"unquoted_lines": unmatched,
	}


@frappe.whitelist()
def apply(supplier_quotation, file_url):
	"""Write the OK rows onto the matching lines. Returns the number of lines updated."""
	doc = frappe.get_doc("Supplier Quotation", supplier_quotation)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft Supplier Quotation can be updated from Excel."))
	rows, _unmatched = parse(doc, file_url)
	lines = {str(r.pvfss_customer_line_ref or ""): r for r in doc.items}
	updated = 0
	for row in rows:
		if row["status"] != "OK":
			continue
		line = lines[row["pvfss_customer_line_ref"]]
		for field in (
			"rate",
			"lead_time_days",
			"pvfss_availability",
			"pvfss_manufacturer",
			"pvfss_origin",
			"pvfss_compliance",
			"pvfss_deviation_note",
			"pvfss_no_quote",
		):
			if row.get(field) not in (None, "") or field == "pvfss_no_quote":
				line.set(field, row.get(field))
		if row["rate"]:
			line.price_list_rate = 0
			line.discount_percentage = 0
		updated += 1
	if not updated:
		frappe.throw(_("No valid rows to apply."))
	doc.save()
	return updated
