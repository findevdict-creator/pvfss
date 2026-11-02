"""Developer helper for step 13-dispatch: Delivery Note fields (DSP-01, DSP-03, DSP-07 to DSP-09).

bench --site pvfss.localhost execute pvfss.setup.customisations_13.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "PVFSS Logistics"
MODES = "International shipment\nTo port\nDirect to site"
TRANSPORT = "Road\nSea\nAir\nCourier"


def _f(fieldname, fieldtype, label, after, **kw):
	d = {"fieldname": fieldname, "fieldtype": fieldtype, "insert_after": after, **kw}
	if label:
		d["label"] = label
	return d


def custom_fields():
	pod = {"allow_on_submit": 1, "no_copy": 1}
	return {
		"Delivery Note": [
			# Delivery (DSP-01)
			_f("pvfss_customer_po_no", "Data", "Customer PO No", "po_no", read_only=1, in_list_view=1),
			_f(
				"pvfss_project",
				"Link",
				"Project",
				"pvfss_customer_po_no",
				options="Project",
				in_standard_filter=1,
			),
			_f(
				"pvfss_lot_no",
				"Data",
				"Dispatch Lot No",
				"pvfss_project",
				in_list_view=1,
				in_standard_filter=1,
			),
			_f(
				"pvfss_delivery_mode",
				"Select",
				"Delivery Mode",
				"pvfss_lot_no",
				options=MODES,
				default="Direct to site",
				in_standard_filter=1,
			),
			_f(
				"pvfss_transport_mode",
				"Select",
				"Transport",
				"pvfss_delivery_mode",
				options=TRANSPORT,
				default="Road",
			),
			_f(
				"pvfss_dispatch_gate", "Data", "Dispatch Gate", "pvfss_transport_mode", read_only=1, no_copy=1
			),
			_f(
				"pvfss_documents_ready",
				"Data",
				"Documents Ready",
				"pvfss_dispatch_gate",
				read_only=1,
				no_copy=1,
				in_list_view=1,
			),
			# Shipping (DSP-01)
			_f("pvfss_shipping_tab", "Tab Break", "Shipping", "pvfss_documents_ready"),
			_f("pvfss_port_of_loading", "Data", "Port of Loading", "pvfss_shipping_tab"),
			_f("pvfss_port_of_discharge", "Data", "Port of Discharge", "pvfss_port_of_loading"),
			_f("pvfss_vessel", "Data", "Vessel / Flight", "pvfss_port_of_discharge"),
			_f("pvfss_bl_no", "Data", "B/L or AWB No", "pvfss_vessel"),
			_f("pvfss_bl_date", "Date", "B/L Date", "pvfss_bl_no"),
			_f("pvfss_shipping_cb", "Column Break", None, "pvfss_bl_date"),
			_f("pvfss_container_nos", "Small Text", "Container Nos", "pvfss_shipping_cb"),
			_f(
				"pvfss_freight_forwarder",
				"Link",
				"Freight Forwarder",
				"pvfss_container_nos",
				options="Supplier",
			),
			_f("pvfss_etd", "Date", "ETD", "pvfss_freight_forwarder", allow_on_submit=1),
			_f("pvfss_eta", "Date", "ETA", "pvfss_etd", allow_on_submit=1, in_list_view=1),
			# Dispatch documents (DSP-03)
			_f("pvfss_documents_tab", "Tab Break", "Dispatch Documents", "pvfss_eta"),
			_f(
				"pvfss_dispatch_documents",
				"Table",
				"Dispatch Documents",
				"pvfss_documents_tab",
				options="Dispatch Document",
				allow_on_submit=1,
			),
			# Packages (DSP-07)
			_f("pvfss_packages_tab", "Tab Break", "Packages", "pvfss_dispatch_documents"),
			_f(
				"pvfss_marking_instructions",
				"Small Text",
				"Marking Instructions (PO / SO)",
				"pvfss_packages_tab",
				read_only=1,
			),
			_f(
				"pvfss_packages",
				"Table",
				"Packages",
				"pvfss_marking_instructions",
				options="Dispatch Package",
			),
			# Customs & freight (DSP-08)
			_f("pvfss_customs_tab", "Tab Break", "Customs & Freight", "pvfss_packages"),
			_f(
				"pvfss_customs_declaration_no",
				"Data",
				"Customs Declaration No",
				"pvfss_customs_tab",
				allow_on_submit=1,
			),
			_f(
				"pvfss_customs_date",
				"Date",
				"Declaration Date",
				"pvfss_customs_declaration_no",
				allow_on_submit=1,
			),
			_f(
				"pvfss_port_agent",
				"Link",
				"Port Handling Agent",
				"pvfss_customs_date",
				options="Supplier",
				allow_on_submit=1,
			),
			_f(
				"pvfss_freight_invoices",
				"Table",
				"Freight / Clearing Invoices",
				"pvfss_port_agent",
				options="Dispatch Freight Invoice",
				allow_on_submit=1,
			),
			# Delivery confirmation (DSP-09)
			_f("pvfss_pod_tab", "Tab Break", "Delivery Confirmation", "pvfss_freight_invoices"),
			_f("pvfss_pod_date", "Date", "POD Date", "pvfss_pod_tab", **pod),
			_f("pvfss_received_by", "Data", "Received by", "pvfss_pod_date", **pod),
			_f("pvfss_pod_attachment", "Attach", "POD Attachment", "pvfss_received_by", **pod),
			_f("pvfss_delivery_remarks", "Small Text", "Delivery Remarks", "pvfss_pod_attachment", **pod),
			_f(
				"pvfss_sales_invoice",
				"Link",
				"Draft Sales Invoice",
				"pvfss_delivery_remarks",
				options="Sales Invoice",
				read_only=1,
				**pod,
			),
			_f(
				"pvfss_pod_alerted_on",
				"Date",
				"POD Alert Sent",
				"pvfss_sales_invoice",
				read_only=1,
				hidden=1,
				**pod,
			),
		],
		"Delivery Note Item": [
			_f("pvfss_irn", "Link", "IRN", "pvfss_doc_req", options="IRN", read_only=1, no_copy=1),
			_f("pvfss_irn_qty", "Float", "IRN Released Qty", "pvfss_irn", read_only=1, no_copy=1),
			_f(
				"pvfss_shipped_before", "Float", "Previously Shipped", "pvfss_irn_qty", read_only=1, no_copy=1
			),
			_f("pvfss_gate_status", "Data", "Gate", "pvfss_shipped_before", read_only=1, no_copy=1),
		],
	}


def apply():
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("13-dispatch customisations applied")
