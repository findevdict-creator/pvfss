"""Developer helper for step 02-masters: (re)creates the Custom Fields and Property Setters
of this step on a developer site so they can be exported as fixtures.

    bench --site pvfss.localhost execute pvfss.setup.customisations_02.apply
    bench --site pvfss.localhost export-fixtures --app pvfss

Production sites never run this: they get the exported fixtures.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULE = "PVFSS"

# GEN-50: shared line fields on every item child table of the document chain.
LINE_TABLES = [
	"Opportunity Item",
	"Request for Quotation Item",
	"Supplier Quotation Item",
	"Quotation Item",
	"Sales Order Item",
	"Purchase Order Item",
	"Purchase Receipt Item",
	"Delivery Note Item",
	"Sales Invoice Item",
	"Purchase Invoice Item",
]

MATERIAL_TYPES = "\nCS\nSS\nAlloy\nOther"


def line_fields(dt):
	meta = frappe.get_meta(dt)
	order = [df.fieldname for df in meta.fields]
	# Put the PVFSS section just before the quantity section, after the item description block.
	anchor_index = (
		order.index("quantity_and_rate") - 1 if "quantity_and_rate" in order else order.index("description")
	)
	anchor = order[anchor_index]
	return [
		{
			"fieldname": "pvfss_line_section",
			"fieldtype": "Section Break",
			"label": "PVFSS Line Details",
			"insert_after": anchor,
			"collapsible": 1,
		},
		{
			"fieldname": "pvfss_customer_line_ref",
			"fieldtype": "Data",
			"label": "Customer Line Ref",
			"insert_after": "pvfss_line_section",
			"in_list_view": 0,
			"search_index": 1,
			"description": "Contractor's line / item number from the inquiry (GEN-50).",
		},
		{
			"fieldname": "pvfss_material_type",
			"fieldtype": "Select",
			"label": "Material Type",
			"options": MATERIAL_TYPES,
			"insert_after": "pvfss_customer_line_ref",
			"fetch_from": "item_code.pvfss_material_type",
			"fetch_if_empty": 1,
		},
		{
			"fieldname": "pvfss_product_category",
			"fieldtype": "Link",
			"label": "Product Category",
			"options": "Item Group",
			"insert_after": "pvfss_material_type",
			"fetch_from": "item_code.item_group",
			"fetch_if_empty": 1,
		},
		{
			"fieldname": "pvfss_heat_traceable",
			"fieldtype": "Check",
			"label": "Heat Traceable",
			"default": "1",
			"insert_after": "pvfss_product_category",
		},
		{
			"fieldname": "pvfss_line_column",
			"fieldtype": "Column Break",
			"insert_after": "pvfss_heat_traceable",
		},
		{
			"fieldname": "pvfss_specification",
			"fieldtype": "Small Text",
			"label": "Specification",
			"insert_after": "pvfss_line_column",
			"description": "Full line specification as written by the contractor.",
		},
		{
			"fieldname": "pvfss_inspection_req",
			"fieldtype": "Small Text",
			"label": "Inspection Requirement",
			"insert_after": "pvfss_specification",
		},
		{
			"fieldname": "pvfss_doc_req",
			"fieldtype": "Small Text",
			"label": "Document Requirement",
			"insert_after": "pvfss_inspection_req",
			"description": "e.g. MTC 3.1 / 3.2",
		},
	]


def custom_fields():
	fields = {
		# MD-01 + screens C.2
		"Customer": [
			{
				"fieldname": "pvfss_customer_type",
				"fieldtype": "Select",
				"label": "Customer Type",
				"options": "EPC\nEPCM\nDirect Client\nOther",
				"reqd": 1,
				"default": "EPC",
				"insert_after": "customer_group",
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "pvfss_portal_section",
				"fieldtype": "Section Break",
				"label": "Contractor Portal",
				"insert_after": "pvfss_customer_type",
				"collapsible": 1,
			},
			{
				"fieldname": "pvfss_portal_name",
				"fieldtype": "Data",
				"label": "Portal Name",
				"insert_after": "pvfss_portal_section",
			},
			{
				"fieldname": "pvfss_portal_vendor_code",
				"fieldtype": "Data",
				"label": "PVFSS Vendor Code on Portal",
				"insert_after": "pvfss_portal_name",
			},
			{
				"fieldname": "pvfss_portal_column",
				"fieldtype": "Column Break",
				"insert_after": "pvfss_portal_vendor_code",
			},
			{
				"fieldname": "pvfss_portal_url",
				"fieldtype": "Data",
				"label": "Portal URL",
				"options": "URL",
				"insert_after": "pvfss_portal_column",
			},
			{
				"fieldname": "pvfss_default_retention_pct",
				"fieldtype": "Percent",
				"label": "Default Retention %",
				"insert_after": "payment_terms",
				"non_negative": 1,
			},
		],
		# MD-13 + screens C.2
		"Item": [
			{
				"fieldname": "pvfss_section",
				"fieldtype": "Section Break",
				"label": "PVFSS",
				"insert_after": "description",
			},
			{
				"fieldname": "pvfss_material_type",
				"fieldtype": "Select",
				"label": "Material Type",
				"options": MATERIAL_TYPES,
				"insert_after": "pvfss_section",
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "pvfss_mtc_rule_category",
				"fieldtype": "Data",
				"label": "MTC Rule Category",
				"insert_after": "pvfss_material_type",
				"description": "Used to look up the MTC age rule (SMR-20).",
			},
			{
				"fieldname": "pvfss_column",
				"fieldtype": "Column Break",
				"insert_after": "pvfss_mtc_rule_category",
			},
			{
				"fieldname": "pvfss_irn_required",
				"fieldtype": "Check",
				"label": "IRN Required",
				"default": "1",
				"insert_after": "pvfss_column",
				"description": 'Untick for items flagged "IRN not applicable" (DSP-02).',
			},
			{
				"fieldname": "pvfss_heat_traceable",
				"fieldtype": "Check",
				"label": "Heat Traceable",
				"default": "1",
				"insert_after": "pvfss_irn_required",
				"description": "Heat-traceable stock items must have Has Batch No ticked.",
			},
		],
		# MD-24, screens SCR-MD-09
		"Employee": [
			{
				"fieldname": "pvfss_section",
				"fieldtype": "Section Break",
				"label": "PVFSS",
				"insert_after": "employment_type"
				if frappe.get_meta("Employee").has_field("employment_type")
				else "department",
			},
			{
				"fieldname": "pvfss_nationality_uae",
				"fieldtype": "Check",
				"label": "UAE National",
				"insert_after": "pvfss_section",
				"description": "Counted for ICV headcount (ICV-10).",
			},
			{
				"fieldname": "pvfss_is_inspector",
				"fieldtype": "Check",
				"label": "Is Inspector",
				"insert_after": "pvfss_nationality_uae",
				"in_standard_filter": 1,
			},
			{"fieldname": "pvfss_column", "fieldtype": "Column Break", "insert_after": "pvfss_is_inspector"},
			{
				"fieldname": "pvfss_inspector_qualifications",
				"fieldtype": "Small Text",
				"label": "Inspector Qualifications",
				"insert_after": "pvfss_column",
				"depends_on": "pvfss_is_inspector",
			},
		],
	}
	for dt in LINE_TABLES:
		fields[dt] = line_fields(dt)
	return fields


# GEN-40: naming series (year = 2 digits)
NAMING_SERIES = {
	"Opportunity": "INQ-.YY.-.#####",
	"Request for Quotation": "RFQ-.YY.-.#####",
	"Supplier Quotation": "SQ-.YY.-.#####",
	"Quotation": "QTN-.YY.-.#####",
	"Sales Order": "CPO-.YY.-.#####",
	"Purchase Order": "SPO-.YY.-.#####",
	"Project": "PRJ-.YY.-.#####",
	"Delivery Note": "DN-.YY.-.#####",
	"Sales Invoice": "INV-.YY.-.#####",
}


def property_setters():
	for dt, series in NAMING_SERIES.items():
		field = frappe.get_meta(dt).get_field("naming_series")
		existing = [o for o in (field.options or "").split("\n") if o and o != series]
		_ps(dt, "naming_series", "options", "\n".join([series, *existing]), "Text")
		_ps(dt, "naming_series", "default", series, "Text")


def _ps(dt, fieldname, prop, value, ptype):
	ps = make_property_setter(dt, fieldname, prop, value, ptype, validate_fields_for_doctype=False)
	frappe.db.set_value("Property Setter", ps.name, "module", MODULE)


def apply():
	all_fields = custom_fields()
	for fields in all_fields.values():
		for f in fields:
			f.setdefault("module", MODULE)
	create_custom_fields(all_fields, update=True)
	property_setters()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("02-masters customisations applied")
