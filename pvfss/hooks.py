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
	"Supplier Quotation": {"on_submit": "pvfss.overrides.opportunity.on_supplier_quotation_submit"},
	"Quotation": {
		"on_submit": "pvfss.overrides.opportunity.on_quotation_submit",
		"on_update_after_submit": "pvfss.overrides.opportunity.on_quotation_update_after_submit",
	},
	"Sales Order": {"on_submit": "pvfss.overrides.opportunity.on_sales_order_submit"},
	# Module 2: Supplier management (SUP-01 to SUP-07)
	"Supplier": {"validate": "pvfss.overrides.supplier.validate"},
	"Request for Quotation": {"validate": "pvfss.overrides.request_for_quotation.validate"},
	"Purchase Order": {"validate": "pvfss.overrides.purchase_order.validate"},
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
]

# Tests
# -----
before_tests = "pvfss.setup.install.before_tests"
