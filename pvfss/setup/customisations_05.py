"""Developer helper for step 05-supplier: Supplier custom fields (SUP-01, SUP-02, SUP-04, ICV-03).

bench --site pvfss.localhost execute pvfss.setup.customisations_05.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULE = "PVFSS CRM"
APPROVAL_STATUSES = "Prospect\nApproved\nConditionally approved\nSuspended\nBlacklisted"


def custom_fields():
	last = frappe.get_meta("Supplier").fields[-1].fieldname
	return {
		"Supplier": [
			{
				"fieldname": "pvfss_supplier_type",
				"fieldtype": "Select",
				"label": "PVFSS Supplier Type",
				"options": "Mill\nManufacturer\nStockist\nTrader\nService",
				"default": "Stockist",
				"reqd": 1,
				"insert_after": "supplier_group",
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "pvfss_uae_based",
				"fieldtype": "Check",
				"label": "UAE Based",
				"insert_after": "pvfss_supplier_type",
				"in_standard_filter": 1,
				"description": "Used by ICV (ICV-10).",
			},
			{
				"fieldname": "pvfss_default_retention_pct",
				"fieldtype": "Percent",
				"label": "Default Retention %",
				"insert_after": "pvfss_uae_based",
				"non_negative": 1,
				"description": "Supplier retention default (PUR-03).",
			},
			# Approval tab
			{
				"fieldname": "pvfss_approval_tab",
				"fieldtype": "Tab Break",
				"label": "Approval",
				"insert_after": last,
			},
			{
				"fieldname": "pvfss_approval_status",
				"fieldtype": "Select",
				"label": "Approval Status",
				"options": APPROVAL_STATUSES,
				"default": "Prospect",
				"reqd": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"insert_after": "pvfss_approval_tab",
			},
			{
				"fieldname": "pvfss_approval_date",
				"fieldtype": "Date",
				"label": "Approval Date",
				"insert_after": "pvfss_approval_status",
			},
			{
				"fieldname": "pvfss_approved_by",
				"fieldtype": "Link",
				"label": "Approved By",
				"options": "User",
				"insert_after": "pvfss_approval_date",
			},
			{
				"fieldname": "pvfss_approval_column",
				"fieldtype": "Column Break",
				"insert_after": "pvfss_approved_by",
			},
			{
				"fieldname": "pvfss_approval_remarks",
				"fieldtype": "Small Text",
				"label": "Approval Remarks",
				"insert_after": "pvfss_approval_column",
				"description": "Required when suspending or blacklisting; shown as the warning for conditionally approved suppliers.",
			},
			# Product categories tab (SUP-02)
			{
				"fieldname": "pvfss_categories_tab",
				"fieldtype": "Tab Break",
				"label": "Product Categories",
				"insert_after": "pvfss_approval_remarks",
			},
			{
				"fieldname": "pvfss_product_categories",
				"fieldtype": "Table",
				"label": "Product Categories",
				"options": "Supplier Product Category",
				"insert_after": "pvfss_categories_tab",
			},
			# Documents tab (SUP-04)
			{
				"fieldname": "pvfss_documents_tab",
				"fieldtype": "Tab Break",
				"label": "Documents",
				"insert_after": "pvfss_product_categories",
			},
			{
				"fieldname": "pvfss_documents",
				"fieldtype": "Table",
				"label": "Supplier Documents",
				"options": "Supplier Document",
				"insert_after": "pvfss_documents_tab",
			},
			# ICV tab (ICV-03)
			{
				"fieldname": "pvfss_icv_tab",
				"fieldtype": "Tab Break",
				"label": "ICV",
				"insert_after": "pvfss_documents",
			},
			{
				"fieldname": "pvfss_icv_score",
				"fieldtype": "Percent",
				"label": "ICV Score %",
				"insert_after": "pvfss_icv_tab",
				"in_list_view": 1,
			},
			{
				"fieldname": "pvfss_icv_cert_expiry",
				"fieldtype": "Date",
				"label": "ICV Certificate Expiry",
				"insert_after": "pvfss_icv_score",
			},
			{
				"fieldname": "pvfss_icv_certificate",
				"fieldtype": "Attach",
				"label": "ICV Certificate",
				"insert_after": "pvfss_icv_cert_expiry",
			},
		],
	}


PROPERTY_SETTERS = [
	("Supplier", "country", "reqd", "1", "Check"),
	("Supplier", "country", "default", "United Arab Emirates", "Text"),
]


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	for dt, field, prop, value, ptype in PROPERTY_SETTERS:
		ps = make_property_setter(dt, field, prop, value, ptype, validate_fields_for_doctype=False)
		frappe.db.set_value("Property Setter", ps.name, "module", MODULE)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("05-supplier customisations applied")
