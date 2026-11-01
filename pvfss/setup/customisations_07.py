"""Developer helper for step 07-quotation: Quotation and Customer PO (Sales Order) fields
(SQ-02, SQ-07 to SQ-09, ICV-20).

    bench --site pvfss.localhost execute pvfss.setup.customisations_07.apply

The contractor's PO number and date use ERPNext's own ``po_no`` / ``po_date`` on the Sales
Order (requirements: ``pvfss_customer_po_no`` / ``pvfss_customer_po_date``), made mandatory,
so they keep flowing to Delivery Notes and Sales Invoices.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULE = "PVFSS CRM"


def custom_fields():
	return {
		"Quotation": [
			{
				"fieldname": "pvfss_costing_sheet",
				"fieldtype": "Link",
				"label": "Costing Sheet",
				"options": "Costing Sheet",
				"read_only": 1,
				"insert_after": "valid_till",
			},
			{
				"fieldname": "pvfss_delivery_terms",
				"fieldtype": "Small Text",
				"label": "Delivery Terms",
				"insert_after": "pvfss_costing_sheet",
			},
			# Margin tab (SCR-SQ-02)
			{
				"fieldname": "pvfss_margin_tab",
				"fieldtype": "Tab Break",
				"label": "Margin",
				"insert_after": "auto_repeat_section",
			},
			{
				"fieldname": "pvfss_margin_pct",
				"fieldtype": "Percent",
				"label": "Margin %",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_margin_tab",
				"in_list_view": 1,
			},
			{
				"fieldname": "pvfss_margin_amount",
				"fieldtype": "Currency",
				"label": "Margin AED",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_margin_pct",
			},
			{
				"fieldname": "pvfss_landed_cost",
				"fieldtype": "Currency",
				"label": "Costing Landed Cost AED",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_margin_amount",
			},
			{
				"fieldname": "pvfss_margin_column",
				"fieldtype": "Column Break",
				"insert_after": "pvfss_landed_cost",
			},
			{
				"fieldname": "pvfss_approver_role",
				"fieldtype": "Data",
				"label": "Approval By",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_margin_column",
				"description": "Pre-Bidding Manager at or above the minimum margin, otherwise a Director (SQ-06).",
			},
			{
				"fieldname": "pvfss_approved_by",
				"fieldtype": "Link",
				"label": "Approved By",
				"options": "User",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_approver_role",
			},
			# Deviations tab
			{
				"fieldname": "pvfss_deviations_tab",
				"fieldtype": "Tab Break",
				"label": "Deviations",
				"insert_after": "pvfss_approved_by",
			},
			{
				"fieldname": "pvfss_technical_deviations",
				"fieldtype": "Text",
				"label": "Technical Deviations",
				"insert_after": "pvfss_deviations_tab",
				"description": "Accepted deviations, printed on the quotation.",
			},
			# ICV evaluation tab (ICV-20)
			{
				"fieldname": "pvfss_icv_tab",
				"fieldtype": "Tab Break",
				"label": "ICV Evaluation",
				"insert_after": "pvfss_technical_deviations",
			},
			{
				"fieldname": "pvfss_icv_score_used",
				"fieldtype": "Percent",
				"label": "ICV Score Used %",
				"insert_after": "pvfss_icv_tab",
			},
			{
				"fieldname": "pvfss_icv_weightage_pct",
				"fieldtype": "Percent",
				"label": "Tender ICV Weightage %",
				"insert_after": "pvfss_icv_score_used",
			},
			{
				"fieldname": "pvfss_evaluated_price",
				"fieldtype": "Currency",
				"label": "Evaluated Price",
				"options": "currency",
				"read_only": 1,
				"insert_after": "pvfss_icv_weightage_pct",
				"description": "Bid price x (1 - ICV score x weightage).",
			},
		],
		"Quotation Item": [
			{
				"fieldname": "pvfss_lead_time_days",
				"fieldtype": "Int",
				"label": "Lead Time (days)",
				"insert_after": "pvfss_doc_req",
				"in_list_view": 1,
				"columns": 1,
			},
			{
				"fieldname": "pvfss_landed_cost",
				"fieldtype": "Currency",
				"label": "Landed Unit Cost AED",
				"options": "Company:company:default_currency",
				"read_only": 1,
				"insert_after": "pvfss_lead_time_days",
			},
			{
				"fieldname": "pvfss_line_margin_pct",
				"fieldtype": "Percent",
				"label": "Line Margin %",
				"read_only": 1,
				"insert_after": "pvfss_landed_cost",
			},
		],
		"Sales Order": [
			{
				"fieldname": "pvfss_customer_po_file",
				"fieldtype": "Attach",
				"label": "Customer PO File",
				"reqd": 1,
				"insert_after": "po_date",
			},
			{
				"fieldname": "pvfss_inquiry",
				"fieldtype": "Link",
				"label": "Inquiry",
				"options": "Opportunity",
				"read_only": 1,
				"insert_after": "pvfss_customer_po_file",
			},
			{
				"fieldname": "pvfss_client_project",
				"fieldtype": "Link",
				"label": "Client Project",
				"options": "Client Project",
				"insert_after": "pvfss_inquiry",
				"in_standard_filter": 1,
			},
			# Commercial tab
			{
				"fieldname": "pvfss_commercial_tab",
				"fieldtype": "Tab Break",
				"label": "Commercial",
				"insert_after": "auto_repeat_section",
			},
			{
				"fieldname": "pvfss_payment_method",
				"fieldtype": "Select",
				"label": "Payment Method",
				"options": "\nTT\nPDC\nLC",
				"reqd": 1,
				"insert_after": "pvfss_commercial_tab",
			},
			{
				"fieldname": "pvfss_retention_pct",
				"fieldtype": "Percent",
				"label": "Retention %",
				"non_negative": 1,
				"insert_after": "pvfss_payment_method",
			},
			{
				"fieldname": "pvfss_retention_basis",
				"fieldtype": "Select",
				"label": "Retention Basis",
				"options": "\nPer invoice\nTotal project value",
				"insert_after": "pvfss_retention_pct",
				"mandatory_depends_on": "eval:doc.pvfss_retention_pct > 0",
			},
			{
				"fieldname": "pvfss_commercial_column",
				"fieldtype": "Column Break",
				"insert_after": "pvfss_retention_basis",
			},
			{
				"fieldname": "pvfss_warranty_months",
				"fieldtype": "Int",
				"label": "Warranty (months)",
				"non_negative": 1,
				"insert_after": "pvfss_commercial_column",
			},
			{
				"fieldname": "pvfss_ld_terms",
				"fieldtype": "Small Text",
				"label": "Liquidated Damages Terms",
				"insert_after": "pvfss_warranty_months",
			},
			{
				"fieldname": "pvfss_advance_billing_allowed",
				"fieldtype": "Check",
				"label": "Advance Billing Allowed",
				"insert_after": "pvfss_ld_terms",
				"description": "Set by a Finance Manager only (FIN-10).",
			},
			# PO review tab (SQ-08)
			{
				"fieldname": "pvfss_review_tab",
				"fieldtype": "Tab Break",
				"label": "PO Review",
				"insert_after": "pvfss_advance_billing_allowed",
			},
			{
				"fieldname": "pvfss_review_status",
				"fieldtype": "Data",
				"label": "Review Result",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_review_tab",
			},
			{
				"fieldname": "pvfss_review_complete",
				"fieldtype": "Check",
				"label": "Review Complete",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_review_status",
			},
			{
				"fieldname": "pvfss_difference_count",
				"fieldtype": "Int",
				"label": "Differences vs Quotation",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_review_complete",
			},
			{
				"fieldname": "pvfss_po_review",
				"fieldtype": "Table",
				"label": "Customer PO Review",
				"options": "Customer PO Review Item",
				"insert_after": "pvfss_difference_count",
			},
			{
				"fieldname": "pvfss_differences_section",
				"fieldtype": "Section Break",
				"label": "Quotation vs Customer PO",
				"insert_after": "pvfss_po_review",
			},
			{
				"fieldname": "pvfss_differences",
				"fieldtype": "Table",
				"label": "Differences",
				"options": "Customer PO Difference",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_differences_section",
				"description": "Built on save (SQ-09). Each difference needs a Deviation with remark on its review check.",
			},
		],
	}


PROPERTY_SETTERS = [
	("Sales Order", "po_no", "reqd", "1", "Check"),
	("Sales Order", "po_no", "label", "Customer PO No", "Data"),
	("Sales Order", "po_no", "in_list_view", "1", "Check"),
	("Sales Order", "po_date", "reqd", "1", "Check"),
	("Sales Order", "po_date", "label", "Customer PO Date", "Data"),
	("Quotation", "valid_till", "reqd", "1", "Check"),
	("Quotation", None, "default_print_format", "PVFSS Quotation", "Data"),
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
	print("07-quotation customisations applied")
