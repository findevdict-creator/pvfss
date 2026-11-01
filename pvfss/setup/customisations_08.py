"""Developer helper for step 08-purchasing: Supplier PO (Purchase Order) fields (PUR-01 to PUR-11).

    bench --site pvfss.localhost execute pvfss.setup.customisations_08.apply

The PO line keeps ERPNext's own ``sales_order`` / ``sales_order_item`` /
``supplier_quotation_item`` links (PUR-02); they are locked after creation.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

MODULE = "PVFSS Purchasing"


def _f(fieldname, fieldtype, label, after, **kw):
	return {"fieldname": fieldname, "fieldtype": fieldtype, "label": label, "insert_after": after, **kw}


def custom_fields():
	return {
		"Purchase Order": [
			_f(
				"pvfss_sales_order",
				"Link",
				"Customer PO",
				"supplier",
				options="Sales Order",
				read_only=1,
				in_standard_filter=1,
			),
			_f("pvfss_customer_po_no", "Data", "Customer PO No", "pvfss_sales_order", read_only=1),
			_f(
				"pvfss_client_project",
				"Link",
				"Client Project",
				"pvfss_customer_po_no",
				options="Client Project",
				read_only=1,
			),
			_f(
				"pvfss_payment_method",
				"Select",
				"Payment Method",
				"pvfss_client_project",
				options="\nTT\nPDC\nLC",
			),
			_f("pvfss_lc_required", "Check", "LC Required", "pvfss_payment_method"),
			_f(
				"pvfss_avl_customer_approval_ref",
				"Data",
				"AVL Customer Approval Ref",
				"pvfss_lc_required",
				description="Customer approval for a supplier that is not on the client project AVL (SUP-03). Post-Bidding Manager only.",
			),
			_f(
				"pvfss_amendment_reason",
				"Small Text",
				"Amendment Reason",
				"pvfss_avl_customer_approval_ref",
				depends_on="eval:doc.amended_from",
				mandatory_depends_on="eval:doc.amended_from",
				no_copy=1,
			),
			# Flow-down requirements (PUR-03)
			_f("pvfss_flowdown_tab", "Tab Break", "Flow-down Requirements", "auto_repeat_section"),
			_f(
				"pvfss_inspection_requirements",
				"Text",
				"Inspection Requirements (ITP / TPI / customer inspection)",
				"pvfss_flowdown_tab",
			),
			_f(
				"pvfss_document_requirements",
				"Text",
				"Document Requirements (MTC type, CoO, MDR ...)",
				"pvfss_inspection_requirements",
			),
			_f("pvfss_flowdown_column", "Column Break", None, "pvfss_document_requirements"),
			_f(
				"pvfss_packing_instructions",
				"Text",
				"Packing and Marking Instructions",
				"pvfss_flowdown_column",
			),
			_f(
				"pvfss_supplier_retention_pct",
				"Percent",
				"Supplier Retention %",
				"pvfss_packing_instructions",
				non_negative=1,
			),
			_f("pvfss_technical_notes", "Text", "Technical Notes", "pvfss_supplier_retention_pct"),
			# Compliance check (PUR-04, PUR-05, PUR-07)
			_f("pvfss_compliance_tab", "Tab Break", "Compliance Check", "pvfss_technical_notes"),
			_f(
				"pvfss_compliance_status",
				"Data",
				"Compliance Result",
				"pvfss_compliance_tab",
				read_only=1,
				no_copy=1,
			),
			_f(
				"pvfss_deviation_count",
				"Int",
				"Deviations",
				"pvfss_compliance_status",
				read_only=1,
				no_copy=1,
				in_list_view=1,
			),
			_f("pvfss_flag_count", "Int", "Flags", "pvfss_deviation_count", read_only=1, no_copy=1),
			_f(
				"pvfss_over_order_lines",
				"Int",
				"Over-ordered Lines",
				"pvfss_flag_count",
				read_only=1,
				no_copy=1,
			),
			_f(
				"pvfss_compliance",
				"Table",
				"Compliance Lines",
				"pvfss_over_order_lines",
				options="PO Compliance Line",
				no_copy=1,
			),
			# Margin (PUR-06) and approval route (PUR-10)
			_f("pvfss_margin_tab", "Tab Break", "Margin", "pvfss_compliance"),
			_f(
				"pvfss_margin_amount",
				"Currency",
				"PO Margin AED",
				"pvfss_margin_tab",
				options="Company:company:default_currency",
				read_only=1,
				no_copy=1,
			),
			_f("pvfss_margin_pct", "Percent", "PO Margin %", "pvfss_margin_amount", read_only=1, no_copy=1),
			_f(
				"pvfss_negative_margin_lines",
				"Small Text",
				"Lines with Negative Margin",
				"pvfss_margin_pct",
				read_only=1,
				no_copy=1,
			),
			_f("pvfss_margin_column", "Column Break", None, "pvfss_negative_margin_lines"),
			_f(
				"pvfss_approval_route",
				"Select",
				"Approval Route",
				"pvfss_margin_column",
				options="\nValue Approval\nDirector Approval",
				read_only=1,
				no_copy=1,
				description="Director when the total in AED is at or above the PVFSS Settings threshold or a line has a negative margin.",
			),
			# Proforma (PUR-11)
			_f("pvfss_proforma_tab", "Tab Break", "Proforma & LC", "pvfss_approval_route"),
			_f("pvfss_proforma_file", "Attach", "Supplier Proforma", "pvfss_proforma_tab"),
			_f(
				"pvfss_proforma_amount",
				"Currency",
				"Proforma Amount",
				"pvfss_proforma_file",
				options="currency",
			),
			_f("pvfss_proforma_date", "Date", "Proforma Date", "pvfss_proforma_amount"),
		],
		"Purchase Order Item": [
			_f(
				"pvfss_so_rate",
				"Currency",
				"Customer PO Rate AED",
				"pvfss_doc_req",
				options="Company:company:default_currency",
				read_only=1,
				no_copy=1,
			),
			_f(
				"pvfss_line_margin",
				"Currency",
				"Line Margin AED",
				"pvfss_so_rate",
				options="Company:company:default_currency",
				read_only=1,
				no_copy=1,
			),
			_f(
				"pvfss_line_margin_pct",
				"Percent",
				"Line Margin %",
				"pvfss_line_margin",
				read_only=1,
				no_copy=1,
				in_list_view=1,
				columns=1,
			),
		],
	}


PROPERTY_SETTERS = [
	("Purchase Order Item", "sales_order", "read_only", "1", "Check"),
	("Purchase Order Item", "sales_order_item", "read_only", "1", "Check"),
	("Purchase Order Item", "supplier_quotation", "read_only", "1", "Check"),
	("Purchase Order Item", "supplier_quotation_item", "read_only", "1", "Check"),
	("Purchase Order", None, "default_print_format", "PVFSS Supplier PO", "Data"),
]


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
			if f.get("label") is None:
				f.pop("label")
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
	print("08-purchasing customisations applied")
