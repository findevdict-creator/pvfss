"""Developer helper for step 04-crm: Inquiry (Opportunity) custom fields, property setters
and labels. Run on a developer site, then export fixtures.

    bench --site pvfss.localhost execute pvfss.setup.customisations_04.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULE = "PVFSS CRM"

STAGES = [
	"New",
	"RFQ Sent",
	"Quotes Received",
	"Under Evaluation",
	"Quoted",
	"Won",
	"Lost",
	"No Bid",
	"Cancelled",
]


def custom_fields():
	return {
		"Opportunity": [
			# Header (CRM-02, CRM-06)
			{
				"fieldname": "pvfss_stage",
				"fieldtype": "Select",
				"label": "Stage",
				"options": "\n".join(STAGES),
				"default": "New",
				"read_only": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"bold": 1,
				"insert_after": "status",
				"allow_on_submit": 1,
				"no_copy": 1,
			},
			{
				"fieldname": "pvfss_contractor_ref",
				"fieldtype": "Data",
				"label": "Contractor Ref",
				"reqd": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"in_global_search": 1,
				"search_index": 1,
				"insert_after": "customer_name",
				"description": "Contractor's inquiry / RFQ number.",
			},
			{
				"fieldname": "pvfss_client_project",
				"fieldtype": "Link",
				"label": "Client Project",
				"options": "Client Project",
				"in_standard_filter": 1,
				"insert_after": "pvfss_contractor_ref",
			},
			{
				"fieldname": "pvfss_contract_model",
				"fieldtype": "Data",
				"label": "Contract Model",
				"read_only": 1,
				"fetch_from": "pvfss_client_project.contract_model",
				"insert_after": "pvfss_client_project",
			},
			{
				"fieldname": "pvfss_portal",
				"fieldtype": "Data",
				"label": "Portal",
				"insert_after": "pvfss_contract_model",
			},
			{
				"fieldname": "pvfss_received_on",
				"fieldtype": "Datetime",
				"label": "Received On",
				"reqd": 1,
				"default": "Now",
				"insert_after": "pvfss_stage",
			},
			{
				"fieldname": "pvfss_bid_due_date",
				"fieldtype": "Datetime",
				"label": "Bid Due Date",
				"reqd": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"insert_after": "pvfss_received_on",
			},
			{
				"fieldname": "pvfss_tender_type",
				"fieldtype": "Select",
				"label": "Tender Type",
				"options": "\nLimited\nOpen",
				"insert_after": "pvfss_bid_due_date",
			},
			{
				"fieldname": "pvfss_owner",
				"fieldtype": "Link",
				"label": "Inquiry Owner",
				"options": "User",
				"reqd": 1,
				"in_standard_filter": 1,
				"insert_after": "pvfss_tender_type",
			},
			{
				"fieldname": "pvfss_not_duplicate",
				"fieldtype": "Check",
				"label": "Confirmed not a duplicate",
				"depends_on": "eval:doc.pvfss_duplicate_of",
				"insert_after": "pvfss_owner",
				"no_copy": 1,
			},
			{
				"fieldname": "pvfss_duplicate_of",
				"fieldtype": "Link",
				"label": "Possible Duplicate Of",
				"options": "Opportunity",
				"read_only": 1,
				"depends_on": "eval:doc.pvfss_duplicate_of",
				"insert_after": "pvfss_not_duplicate",
				"no_copy": 1,
			},
			# Key requirements tab (SCR-CRM-02 tab 3)
			{
				"fieldname": "pvfss_key_requirements_tab",
				"fieldtype": "Tab Break",
				"label": "Key Requirements",
				"insert_after": "utm_campaign",
			},
			{
				"fieldname": "pvfss_key_requirements",
				"fieldtype": "Text Editor",
				"label": "Key Requirements",
				"insert_after": "pvfss_key_requirements_tab",
				"description": "Technical, commercial, documentation and inspection requirements. Attach the contractor's inquiry package to this inquiry.",
			},
			# Outcome tab (CRM-08, SCR-CRM-02 tab 4)
			{
				"fieldname": "pvfss_outcome_tab",
				"fieldtype": "Tab Break",
				"label": "Outcome",
				"insert_after": "pvfss_key_requirements",
			},
			{
				"fieldname": "pvfss_competitor_name",
				"fieldtype": "Data",
				"label": "Competitor Name",
				"insert_after": "pvfss_outcome_tab",
				"allow_on_submit": 1,
			},
			{
				"fieldname": "pvfss_competitor_price",
				"fieldtype": "Currency",
				"label": "Competitor Price (AED)",
				"options": "AED",
				"insert_after": "pvfss_competitor_name",
				"allow_on_submit": 1,
			},
			{
				"fieldname": "pvfss_outcome_column",
				"fieldtype": "Column Break",
				"insert_after": "pvfss_competitor_price",
			},
			{
				"fieldname": "pvfss_quoted_value",
				"fieldtype": "Currency",
				"label": "Quoted Value (AED)",
				"options": "AED",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_outcome_column",
			},
			{
				"fieldname": "pvfss_quoted_on",
				"fieldtype": "Date",
				"label": "First Quoted On",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_quoted_value",
			},
			{
				"fieldname": "pvfss_turnaround_days",
				"fieldtype": "Int",
				"label": "Turnaround (days)",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_quoted_on",
			},
			{
				"fieldname": "pvfss_line_count",
				"fieldtype": "Int",
				"label": "Lines",
				"read_only": 1,
				"no_copy": 1,
				"insert_after": "pvfss_turnaround_days",
			},
		],
	}


PROPERTY_SETTERS = [
	# CRM-01: Inquiry is always from a Customer (the contractor)
	("Opportunity", "opportunity_from", "default", "Customer", "Text"),
	("Opportunity", "opportunity_from", "read_only", "1", "Check"),
	("Opportunity", "opportunity_from", "hidden", "1", "Check"),
	("Opportunity", "party_name", "label", "Contractor", "Data"),
	("Opportunity", "party_name", "in_list_view", "1", "Check"),
	("Opportunity", "currency", "default", "AED", "Text"),
	("Opportunity", "title", "hidden", "1", "Check"),
	# Stage is the main status (CRM-06): hide the ERPNext sales funnel fields
	("Opportunity", "sales_stage", "hidden", "1", "Check"),
	("Opportunity", "probability", "hidden", "1", "Check"),
	("Opportunity", "opportunity_owner", "read_only", "1", "Check"),
	(
		"Opportunity",
		None,
		"search_fields",
		"customer_name,pvfss_contractor_ref,pvfss_client_project,pvfss_stage",
		"Data",
	),
	("Opportunity", None, "sort_field", "pvfss_bid_due_date", "Data"),
	("Opportunity", None, "sort_order", "ASC", "Data"),
	# CRM-03: specification text is mandatory per line
	("Opportunity Item", "pvfss_specification", "reqd", "1", "Check"),
	# Inquiry lines carry the contractor's demand; prices come later from supplier quotes and costing
	("Opportunity Item", "rate", "reqd", "0", "Check"),
	("Opportunity Item", "pvfss_customer_line_ref", "in_list_view", "1", "Check"),
	("Opportunity Item", "pvfss_specification", "in_list_view", "1", "Check"),
]

from pvfss.hooks import TRANSLATIONS


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)

	for dt, field, prop, value, ptype in PROPERTY_SETTERS:
		ps = make_property_setter(
			dt, field, prop, value, ptype, for_doctype=not field, validate_fields_for_doctype=False
		)
		frappe.db.set_value("Property Setter", ps.name, "module", MODULE)

	for source, target in TRANSLATIONS.items():
		if not frappe.db.exists("Translation", {"source_text": source, "language": "en"}):
			frappe.get_doc(
				{"doctype": "Translation", "language": "en", "source_text": source, "translated_text": target}
			).insert(ignore_permissions=True)
	frappe.db.commit()
	print("04-crm customisations applied")
