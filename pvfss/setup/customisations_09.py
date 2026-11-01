"""Developer helper for step 09-project: Project fields (PRJ-04, PRJ-05, PRJ-10, PRJ-11, PRJ-21,
PRJ-40, FIN-50 dates) and the cost type tag on purchase invoice lines (PRJ-31).

    bench --site pvfss.localhost execute pvfss.setup.customisations_09.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "PVFSS Purchasing"
COST_TYPES = "Material\nFreight\nInspection / TPI\nDocumentation\nTesting\nFinance\nCustoms and port\nOther"


def _f(fieldname, fieldtype, label, after, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype, "insert_after": after, **kw}
	if label:
		d["label"] = label
	return d


def custom_fields():
	return {
		"Project": [
			# Dashboard tab first (SCR-PRJ-05)
			_f("pvfss_dashboard_tab", "Tab Break", "Dashboard", "project_name"),
			_f("pvfss_dashboard", "HTML", "Project Dashboard", "pvfss_dashboard_tab"),
			_f("pvfss_details_tab", "Tab Break", "Details", "pvfss_dashboard"),
			_f(
				"pvfss_handover",
				"Link",
				"Project Handover",
				"pvfss_details_tab",
				options="Project Handover",
				read_only=1,
			),
			_f(
				"pvfss_client_project",
				"Link",
				"Client Project",
				"pvfss_handover",
				options="Client Project",
				in_standard_filter=1,
			),
			_f(
				"pvfss_customer_po_no",
				"Data",
				"Customer PO No",
				"pvfss_client_project",
				read_only=1,
				in_list_view=1,
			),
			_f(
				"pvfss_post_bidding_owner",
				"Link",
				"Post-Bidding Owner",
				"pvfss_customer_po_no",
				options="User",
				in_standard_filter=1,
			),
			_f("pvfss_quality_lead", "Link", "Quality Lead", "pvfss_post_bidding_owner", options="User"),
			_f("pvfss_details_column", "Column Break", None, "pvfss_quality_lead"),
			_f(
				"pvfss_customer_delivery_date",
				"Date",
				"Customer Delivery Date",
				"pvfss_details_column",
				in_list_view=1,
			),
			_f(
				"pvfss_status_summary",
				"Data",
				"Status Summary",
				"pvfss_customer_delivery_date",
				read_only=1,
				in_list_view=1,
			),
			_f(
				"pvfss_delivery_at_risk",
				"Check",
				"Delivery at Risk",
				"pvfss_status_summary",
				read_only=1,
				in_standard_filter=1,
			),
			_f("pvfss_risk_reason", "Small Text", "Risk Reason", "pvfss_delivery_at_risk", read_only=1),
			# Supply routes (PRJ-10, PRJ-21)
			_f("pvfss_routes_tab", "Tab Break", "Supply Routes", "pvfss_risk_reason"),
			_f(
				"pvfss_supply_routes",
				"Table",
				"Supply Routes",
				"pvfss_routes_tab",
				options="Project Supply Route",
			),
			# Technical requirements (PRJ-05)
			_f("pvfss_requirements_tab", "Tab Break", "Technical Requirements", "pvfss_supply_routes"),
			_f(
				"pvfss_technical_requirements",
				"Table",
				"Technical Requirements",
				"pvfss_requirements_tab",
				options="Technical Requirement",
			),
			# MTC rules (SMR-20, inherited from the client project)
			_f("pvfss_mtc_tab", "Tab Break", "MTC Rules", "pvfss_technical_requirements"),
			_f(
				"pvfss_mtc_overrides",
				"Table",
				"MTC Age Overrides",
				"pvfss_mtc_tab",
				options="Client Project MTC Override",
			),
			# Retention and warranty (PRJ-10, FIN-50)
			_f("pvfss_retention_tab", "Tab Break", "Retention & Warranty", "pvfss_mtc_overrides"),
			_f("pvfss_retention_pct", "Percent", "Retention %", "pvfss_retention_tab", read_only=1),
			_f("pvfss_retention_basis", "Data", "Retention Basis", "pvfss_retention_pct", read_only=1),
			_f("pvfss_warranty_months", "Int", "Warranty (months)", "pvfss_retention_basis"),
			_f("pvfss_retention_column", "Column Break", None, "pvfss_warranty_months"),
			_f(
				"pvfss_final_acceptance_date",
				"Date",
				"Delivery / Final Acceptance Date",
				"pvfss_retention_column",
			),
			_f(
				"pvfss_warranty_end_date",
				"Date",
				"Warranty End Date",
				"pvfss_final_acceptance_date",
				read_only=1,
			),
			_f(
				"pvfss_retention_release_date",
				"Date",
				"Retention Release Due",
				"pvfss_warranty_end_date",
				read_only=1,
			),
			# Closure (PRJ-40)
			_f("pvfss_closure_tab", "Tab Break", "Closure", "pvfss_retention_release_date"),
			_f(
				"pvfss_closure_items",
				"Table",
				"Closure Checklist",
				"pvfss_closure_tab",
				options="Project Closure Item",
			),
		],
		"Purchase Invoice Item": [
			_f(
				"pvfss_cost_type",
				"Select",
				"PVFSS Cost Type",
				"pvfss_doc_req",
				options=COST_TYPES,
				default="Material",
				description="Cost type for the Project Cost Sheet (PRJ-31).",
			),
		],
		"Journal Entry Account": [
			_f(
				"pvfss_cost_type", "Select", "PVFSS Cost Type", "project", options=COST_TYPES, default="Other"
			),
		],
	}


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("09-project customisations applied")
