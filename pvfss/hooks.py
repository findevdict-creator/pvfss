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
]

# Tests
# -----
before_tests = "pvfss.setup.install.before_tests"
