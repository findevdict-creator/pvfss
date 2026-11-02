app_name = "pvfss"
app_title = "PVFSS ERP"
app_publisher = "Quantum-Electro Pvt Ltd"
app_description = "PVFSS ERP: custom app for PVFSS Solutions LLC on ERPNext v16"
app_email = "support@quantum-electro.com"
app_license = "gpl-3.0"  # keep GPL notices (GEN-08)

required_apps = ["frappe", "erpnext"]

# Includes
# --------
# Theme (GEN-08, plan §6): CSS variables only, plus shared client utilities.
app_include_css = "/assets/pvfss/css/pvfss_theme.css"
app_include_js = "pvfss.bundle.js"
web_include_css = "/assets/pvfss/css/pvfss_web.css"
app_logo_url = "/assets/pvfss/images/logo.svg"

website_context = {
	"favicon": "/assets/pvfss/images/favicon.svg",
	"splash_image": "/assets/pvfss/images/logo.svg",
}

# Client scripts for standard DocTypes (shipped as files, not Client Script fixtures)
doctype_js = {
	"Opportunity": "public/js/doctype/opportunity.js",
	"Supplier": "public/js/doctype/supplier.js",
	"Request for Quotation": "public/js/doctype/request_for_quotation.js",
	"Supplier Quotation": "public/js/doctype/supplier_quotation.js",
	"Quotation": "public/js/doctype/quotation.js",
	"Sales Order": "public/js/doctype/sales_order.js",
	"Purchase Order": "public/js/doctype/purchase_order.js",
	"Project": "public/js/doctype/project.js",
	"Batch": "public/js/doctype/batch.js",
	"Non Conformance": "public/js/doctype/non_conformance.js",
	"Delivery Note": "public/js/doctype/delivery_note.js",
}
doctype_list_js = {
	"Opportunity": "public/js/doctype/opportunity_list.js",
	"Supplier": "public/js/doctype/supplier_list.js",
}

# Installation
# ------------
after_install = "pvfss.setup.install.after_install"
after_migrate = "pvfss.setup.install.after_migrate"
setup_wizard_complete = "pvfss.setup.masters.setup_wizard_complete"  # company defaults (GEN-10 to 12, MD-20)

# Document events (GEN-04)
# ------------------------
# Every handler for a standard DocType lives in pvfss/overrides/<doctype>.py.
# Each module branch adds its own entries here.
doc_events = {
	"User": {"before_validate": "pvfss.overrides.user.before_validate"},  # NFR-04 password length
	"Item": {"validate": "pvfss.overrides.item.validate"},  # MD-12 / SCR-MD-05
	# Module 1: CRM (CRM-01 to CRM-09)
	"Opportunity": {
		"validate": "pvfss.overrides.opportunity.validate",
		"after_insert": "pvfss.overrides.opportunity.after_insert",
	},
	"Supplier Quotation": {
		"before_validate": "pvfss.overrides.supplier_quotation.before_validate",
		"validate": "pvfss.overrides.supplier_quotation.validate",
		"before_submit": "pvfss.overrides.supplier_quotation.before_submit",
		"on_submit": "pvfss.overrides.supplier_quotation.on_submit",
		"on_cancel": "pvfss.overrides.supplier_quotation.on_cancel",
	},
	# Module 4: Quotation and Customer PO (SQ-01 to SQ-10)
	"Quotation": {
		"onload": "pvfss.overrides.quotation.onload",
		"validate": "pvfss.overrides.quotation.validate",
		"after_insert": "pvfss.overrides.quotation.after_insert",
		"before_submit": "pvfss.overrides.quotation.before_submit",
		"on_submit": "pvfss.overrides.quotation.on_submit",
		"on_update_after_submit": "pvfss.overrides.quotation.on_update_after_submit",
		"before_cancel": "pvfss.overrides.quotation.before_cancel",
	},
	"Sales Order": {
		"onload": "pvfss.overrides.sales_order.onload",
		"before_validate": "pvfss.overrides.sales_order.before_validate",
		"validate": "pvfss.overrides.sales_order.validate",
		"before_submit": "pvfss.overrides.sales_order.before_submit",
		"on_submit": "pvfss.overrides.sales_order.on_submit",
		"after_insert": "pvfss.pvfss_purchasing.project.auto_change",  # PRJ-30
	},
	# Module 2: Supplier management (SUP-01 to SUP-07)
	"Supplier": {"validate": "pvfss.overrides.supplier.validate"},
	"Request for Quotation": {
		"validate": "pvfss.overrides.request_for_quotation.validate",
		"on_submit": "pvfss.overrides.request_for_quotation.on_submit",
		"onload": "pvfss.overrides.request_for_quotation.onload",
	},
	# Module 5: Purchasing (PUR-01 to PUR-12, G3)
	"Purchase Order": {
		"validate": "pvfss.overrides.purchase_order.validate",
		"before_submit": "pvfss.overrides.purchase_order.before_submit",
		"on_cancel": "pvfss.overrides.purchase_order.on_cancel",
		"after_insert": "pvfss.pvfss_purchasing.project.auto_change",  # PUR-09 / PRJ-30
	},
	# Module 9: Heat number traceability (TRC-01 to TRC-04, G6)
	"Batch": {
		"before_insert": "pvfss.overrides.batch.before_insert",
		"validate": "pvfss.overrides.batch.validate",
	},
	"Purchase Receipt": {
		"before_submit": "pvfss.overrides.purchase_receipt.before_submit",
		"on_submit": "pvfss.overrides.purchase_receipt.on_submit",
		"on_cancel": "pvfss.overrides.purchase_receipt.on_cancel",
	},
	# Module 10: Dispatch (DSP-01 to DSP-10, G7) with TRC-04
	"Delivery Note": {
		"validate": "pvfss.overrides.delivery_note.validate",
		"before_submit": "pvfss.overrides.delivery_note.before_submit",
		"on_submit": "pvfss.overrides.delivery_note.on_submit",
		"on_update_after_submit": "pvfss.overrides.delivery_note.on_update_after_submit",
		"on_cancel": "pvfss.overrides.delivery_note.on_cancel",
	},
	# Module 11: Finance (FIN-10, FIN-20, FIN-31, FIN-50, FIN-51, FIN-60)
	"Sales Invoice": {
		"validate": "pvfss.pvfss_finance.invoicing.sales_invoice_validate",
		"on_submit": "pvfss.pvfss_finance.invoicing.sales_invoice_on_submit",
		"before_cancel": "pvfss.pvfss_finance.invoicing.sales_invoice_before_cancel",
	},
	"Purchase Invoice": {
		"validate": "pvfss.pvfss_finance.invoicing.purchase_invoice_validate",
		"on_submit": "pvfss.pvfss_finance.invoicing.purchase_invoice_on_submit",
		"before_cancel": "pvfss.pvfss_finance.invoicing.purchase_invoice_before_cancel",
	},
	"Payment Entry": {"validate": "pvfss.pvfss_finance.invoicing.payment_entry_validate"},
	# Module 6: Project (PRJ-01 to PRJ-40)
	"Project": {"validate": "pvfss.overrides.project.validate"},
	# Module 8: Quality (QA-02, QA-30, TRC-04)
	"Expediting Log": {
		"validate": "pvfss.pvfss_quality.doctype.quality_document_submittal.quality_document_submittal.check_manufacturing_start"
	},
	"Non Conformance": {
		"validate": "pvfss.overrides.non_conformance.validate",
		"on_update": "pvfss.overrides.non_conformance.on_update",
	},
}

# Scheduled tasks (GEN-61)
# ------------------------
# Server timezone is Asia/Dubai. Alert jobs are registered in pvfss/tasks.py.
scheduler_events = {
	"daily": ["pvfss.tasks.daily_alerts"],
	"hourly": ["pvfss.tasks.hourly_alerts"],
}

# Fixtures (GEN-02)
# -----------------
# Everything customised through Desk is exported here and checked for drift in CI.
from pvfss.permission_matrix import MATRIX
from pvfss.setup import workflows

# UI labels (CRM-01, DQ-08). Kept here so hooks need no Frappe import.
TRANSLATIONS = {
	"Opportunity": "Inquiry",
	"Opportunities": "Inquiries",
	"New Opportunity": "New Inquiry",
	"Sales Order": "Customer PO",
	"Purchase Order": "Supplier PO",
}

PVFSS_ROLES = [
	"PVFSS Director",
	"Pre-Bidding User",
	"Pre-Bidding Manager",
	"Post-Bidding User",
	"Post-Bidding Manager",
	"Quality User",
	"Quality Manager",
	"Logistics User",
	"Finance User",
	"Finance Manager",
	"HSE User",
	"HSE Manager",
	"ICV User",
	"PVFSS Read Only",
]

fixtures = [
	{"dt": "Role", "filters": [["name", "in", PVFSS_ROLES]]},
	{"dt": "Custom Field", "filters": [["module", "like", "PVFSS%"]]},
	{"dt": "Property Setter", "filters": [["module", "like", "PVFSS%"]]},
	{"dt": "Custom DocPerm", "filters": [["parent", "in", list(MATRIX)]]},
	{"dt": "Translation", "filters": [["source_text", "in", list(TRANSLATIONS)], ["language", "=", "en"]]},
	{"dt": "Workflow State", "filters": [["name", "in", workflows.state_names()]]},
	{"dt": "Workflow Action Master", "filters": [["name", "in", workflows.action_names()]]},
	{"dt": "Workflow", "filters": [["name", "in", list(workflows.WORKFLOWS)]]},
]

# Tests
# -----
before_tests = "pvfss.setup.install.before_tests"
