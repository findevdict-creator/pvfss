"""Developer helper for step 12-quality: NCR fields on the standard Non Conformance (QA-30, SCR-QA-16).

bench --site pvfss.localhost execute pvfss.setup.customisations_12.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULE = "PVFSS Quality"
SOURCES = "Inspection Report\nMTC review\nSMR\nReceipt\nCustomer complaint\nInternal"


def _f(fieldname, fieldtype, label, after, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype, "insert_after": after, **kw}
	if label:
		d["label"] = label
	return d


def custom_fields():
	return {
		"Non Conformance": [
			_f("pvfss_ncr_tab", "Tab Break", "Nonconformity", "status"),
			_f(
				"pvfss_source",
				"Select",
				"Source",
				"pvfss_ncr_tab",
				options=SOURCES,
				reqd=1,
				in_standard_filter=1,
				in_list_view=1,
			),
			_f("pvfss_source_doctype", "Link", "Source DocType", "pvfss_source", options="DocType", hidden=1),
			_f(
				"pvfss_source_document",
				"Dynamic Link",
				"Source Document",
				"pvfss_source_doctype",
				options="pvfss_source_doctype",
			),
			_f(
				"pvfss_supplier_po",
				"Link",
				"Supplier PO",
				"pvfss_source_document",
				options="Purchase Order",
				in_standard_filter=1,
			),
			_f(
				"pvfss_supplier",
				"Link",
				"Supplier",
				"pvfss_supplier_po",
				options="Supplier",
				fetch_from="pvfss_supplier_po.supplier",
				read_only=1,
				in_standard_filter=1,
			),
			_f(
				"pvfss_project",
				"Link",
				"Project",
				"pvfss_supplier",
				options="Project",
				fetch_from="pvfss_supplier_po.project",
				fetch_if_empty=1,
				in_standard_filter=1,
			),
			_f("pvfss_ncr_cb1", "Column Break", None, "pvfss_project"),
			_f(
				"pvfss_severity",
				"Select",
				"Severity",
				"pvfss_ncr_cb1",
				options="Minor\nMajor\nCritical",
				reqd=1,
				default="Minor",
				in_list_view=1,
				in_standard_filter=1,
			),
			_f("pvfss_raised_by", "Link", "Raised by", "pvfss_severity", options="User", read_only=1),
			_f("pvfss_raised_on", "Date", "Raised on", "pvfss_raised_by", default="Today"),
			_f("pvfss_heats_section", "Section Break", "Items and Heat Numbers Affected", "pvfss_raised_on"),
			_f("pvfss_heats", "Table", "Heats Affected", "pvfss_heats_section", options="NCR Heat"),
			_f("pvfss_heat_list", "Small Text", "Heats", "pvfss_heats", read_only=1, hidden=1),
			_f("pvfss_disposition_tab", "Tab Break", "Disposition", "pvfss_heat_list"),
			_f(
				"pvfss_disposition",
				"Select",
				"Disposition",
				"pvfss_disposition_tab",
				options="\nUse as is\nRework\nRepair\nReject\nReplace",
			),
			_f(
				"pvfss_concession_ref",
				"Data",
				"Customer Concession Ref",
				"pvfss_disposition",
				depends_on="eval:doc.pvfss_disposition=='Use as is'",
			),
			_f("pvfss_response_due", "Date", "Supplier Response Due", "pvfss_concession_ref", in_list_view=1),
			_f("pvfss_supplier_response_date", "Date", "Supplier Response Date", "pvfss_response_due"),
			_f(
				"pvfss_alerted_on",
				"Date",
				"Overdue Alert Sent",
				"pvfss_supplier_response_date",
				read_only=1,
				no_copy=1,
				hidden=1,
			),
			_f("pvfss_closure_tab", "Tab Break", "Closure", "pvfss_alerted_on"),
			_f("pvfss_verified_by", "Link", "Verified by", "pvfss_closure_tab", options="User"),
			_f("pvfss_verification_date", "Date", "Verification Date", "pvfss_verified_by"),
			_f("pvfss_evidence", "Attach", "Evidence", "pvfss_verification_date"),
			_f("pvfss_closure_remarks", "Small Text", "Closure Remarks", "pvfss_evidence"),
		],
	}


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	ps = make_property_setter(
		"Non Conformance", "procedure", "reqd", 0, "Check", validate_fields_for_doctype=False
	)  # PVFSS NCRs come from inspections, not from a Quality Procedure
	frappe.db.set_value("Property Setter", ps.name, "module", MODULE)
	ps = make_property_setter(
		"Non Conformance",
		None,
		"track_changes",
		1,
		"Check",
		for_doctype=True,
		validate_fields_for_doctype=False,
	)
	frappe.db.set_value("Property Setter", ps.name, "module", MODULE)  # audit trail on NCRs (GEN-60)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("12-quality customisations applied")
