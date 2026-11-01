"""Developer helper for step 10-traceability: Batch heat fields (TRC-02), mill abbreviation (TRC-01).

    bench --site pvfss.localhost execute pvfss.setup.customisations_10.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "PVFSS Quality"


def _f(fieldname, fieldtype, label, after, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype, "insert_after": after, **kw}
	if label:
		d["label"] = label
	return d


def custom_fields():
	return {
		"Manufacturer": [
			_f(
				"pvfss_abbr",
				"Data",
				"Abbreviation",
				"full_name",
				description="Used in Heat Number IDs: {abbreviation}-{heat no} (TRC-01).",
			),
		],
		"Batch": [
			_f("pvfss_trace_section", "Section Break", "Heat Traceability", "reference_name"),
			_f(
				"pvfss_heat_number",
				"Link",
				"Heat Number",
				"pvfss_trace_section",
				options="Heat Number",
				search_index=1,
				in_list_view=1,
				in_standard_filter=1,
				description="Mandatory for heat-traceable items (TRC-02).",
			),
			_f(
				"pvfss_heat_status",
				"Data",
				"Heat Status",
				"pvfss_heat_number",
				fetch_from="pvfss_heat_number.status",
				read_only=1,
			),
			_f("pvfss_lot_no", "Data", "Lot / Bundle No", "pvfss_heat_status", in_list_view=1),
			_f("pvfss_trace_column", "Column Break", None, "pvfss_lot_no"),
			_f(
				"pvfss_supplier_po",
				"Link",
				"Supplier PO",
				"pvfss_trace_column",
				options="Purchase Order",
				search_index=1,
				in_standard_filter=1,
			),
			_f(
				"pvfss_tally_sheet",
				"Data",
				"Tally Sheet",
				"pvfss_supplier_po",
				description="Becomes a link to Tally Sheet in 11-smr.",
			),
		],
	}


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	frappe.db.commit()
	print("10-traceability customisations applied")
