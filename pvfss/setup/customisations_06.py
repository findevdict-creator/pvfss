"""Developer helper for step 06-rfq: RFQ and Supplier Quotation fields (RFQ-01 to RFQ-09).

    bench --site pvfss.localhost execute pvfss.setup.customisations_06.apply

The standard ``opportunity`` link on Request for Quotation, Supplier Quotation and Quotation
is the inquiry link (requirements name it ``pvfss_inquiry``); it is relabelled "Inquiry"
rather than duplicated, so ERPNext's own mappings keep filling it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULE = "PVFSS CRM"
AVAILABILITY = "\nReady stock\nManufacture"
COMPLIANCE = "\nCompliant\nDeviation\nNot compliant"


def custom_fields():
	return {
		"Request for Quotation": [
			{
				"fieldname": "pvfss_supplier_due_date",
				"fieldtype": "Date",
				"label": "Supplier Bid Due Date",
				"insert_after": "transaction_date",
				"description": "Should be before the inquiry bid due date.",
				"in_list_view": 1,
			},
		],
		"Request for Quotation Supplier": [
			{
				"fieldname": "pvfss_approval_status",
				"fieldtype": "Data",
				"label": "Approval Status",
				"fetch_from": "supplier.pvfss_approval_status",
				"read_only": 1,
				"in_list_view": 1,
				"columns": 1,
				"insert_after": "supplier_name",
			},
			{
				"fieldname": "pvfss_avl_flag",
				"fieldtype": "Select",
				"label": "AVL",
				"options": "\nOn AVL\nNot on AVL\nNot required",
				"read_only": 1,
				"in_list_view": 1,
				"columns": 1,
				"insert_after": "pvfss_approval_status",
			},
		],
		"Supplier Quotation": [
			{
				"fieldname": "pvfss_negotiation_tab",
				"fieldtype": "Tab Break",
				"label": "Negotiation",
				"insert_after": "auto_repeat_section",
			},
			{
				"fieldname": "pvfss_negotiation_rounds",
				"fieldtype": "Table",
				"label": "Negotiation Rounds",
				"options": "Negotiation Round",
				"insert_after": "pvfss_negotiation_tab",
				"description": "A revised price or lead time updates the line when saved (RFQ-09).",
			},
			{
				"fieldname": "pvfss_lines_quoted",
				"fieldtype": "Int",
				"label": "Lines Quoted",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "valid_till",
			},
			{
				"fieldname": "pvfss_lines_selected",
				"fieldtype": "Int",
				"label": "Lines Selected",
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
				"insert_after": "pvfss_lines_quoted",
			},
		],
		"Supplier Quotation Item": [
			{
				"fieldname": "pvfss_offer_section",
				"fieldtype": "Section Break",
				"label": "PVFSS Supplier Offer",
				"insert_after": "pvfss_doc_req",
			},
			{
				"fieldname": "pvfss_availability",
				"fieldtype": "Select",
				"label": "Availability",
				"options": AVAILABILITY,
				"insert_after": "pvfss_offer_section",
				"in_list_view": 1,
				"columns": 1,
			},
			{
				"fieldname": "pvfss_manufacturer",
				"fieldtype": "Data",
				"label": "Manufacturer / Mill",
				"insert_after": "pvfss_availability",
			},
			{
				"fieldname": "pvfss_origin",
				"fieldtype": "Link",
				"label": "Origin",
				"options": "Country",
				"insert_after": "pvfss_manufacturer",
			},
			{
				"fieldname": "pvfss_offer_column",
				"fieldtype": "Column Break",
				"insert_after": "pvfss_origin",
			},
			{
				"fieldname": "pvfss_compliance",
				"fieldtype": "Select",
				"label": "Compliance",
				"options": COMPLIANCE,
				"insert_after": "pvfss_offer_column",
				"in_list_view": 1,
				"columns": 1,
			},
			{
				"fieldname": "pvfss_deviation_note",
				"fieldtype": "Small Text",
				"label": "Deviation Note",
				"insert_after": "pvfss_compliance",
				"mandatory_depends_on": "eval:['Deviation','Not compliant'].includes(doc.pvfss_compliance)",
			},
			{
				"fieldname": "pvfss_no_quote",
				"fieldtype": "Check",
				"label": "No Quote",
				"insert_after": "pvfss_deviation_note",
			},
			{
				"fieldname": "pvfss_selected",
				"fieldtype": "Check",
				"label": "Selected",
				"insert_after": "pvfss_no_quote",
				"allow_on_submit": 1,
				"read_only": 1,
				"no_copy": 1,
				"in_list_view": 1,
				"columns": 1,
				"description": "Set from the Competitive Statement; one supplier line per inquiry line (RFQ-08).",
			},
		],
	}


PROPERTY_SETTERS = [
	("Request for Quotation", "opportunity", "label", "Inquiry", "Data"),
	("Request for Quotation", "opportunity", "set_only_once", "1", "Check"),
	("Request for Quotation", "opportunity", "in_standard_filter", "1", "Check"),
	("Supplier Quotation", "opportunity", "label", "Inquiry", "Data"),
	("Supplier Quotation", "opportunity", "in_standard_filter", "1", "Check"),
	("Supplier Quotation", "valid_till", "label", "Validity Date", "Data"),
	("Supplier Quotation", "valid_till", "reqd", "1", "Check"),
	("Supplier Quotation", "valid_till", "in_list_view", "1", "Check"),
	("Supplier Quotation Item", "lead_time_days", "in_list_view", "1", "Check"),
	("Supplier Quotation Item", "lead_time_days", "columns", "1", "Int"),
	("Quotation", "opportunity", "label", "Inquiry", "Data"),
	("Request for Quotation", None, "default_print_format", "PVFSS RFQ", "Data"),
	("Request for Quotation", "email_template", "default", "PVFSS RFQ", "Text"),
]


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	for dt, field, prop, value, ptype in PROPERTY_SETTERS:
		ps = make_property_setter(
			dt,
			field,
			prop,
			value,
			ptype,
			for_doctype=field is None,
			validate_fields_for_doctype=False,
		)
		frappe.db.set_value("Property Setter", ps.name, "module", MODULE)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("06-rfq customisations applied")
