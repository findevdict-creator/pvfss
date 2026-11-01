"""Product name, logo, favicon, letterhead and print style (GEN-08, GEN-62, plan §6.4-6.5).

Applied on install and migrate. Values PVFSS changed by hand (anything other than Frappe's
defaults) are left alone.
"""

import frappe

PRODUCT_NAME = "PVFSS ERP"
LOGO = "/assets/pvfss/images/logo.svg"
FAVICON = "/assets/pvfss/images/favicon.svg"
FOOTER = "© PVFSS Solutions LLC · Powered by Quantum-Electro · Built on open-source software (GPL)"

LETTER_HEAD = "PVFSS"
PRINT_STYLE = "PVFSS"


def apply():
	_set_if_default("System Settings", "app_name", PRODUCT_NAME, ("", None, "Frappe", "ERPNext"))
	_set_if_default("System Settings", "otp_issuer_name", PRODUCT_NAME, ("", None, "Frappe Framework"))
	_set_if_default("Navbar Settings", "app_logo", LOGO, ("", None))
	_set_if_default("Website Settings", "app_name", PRODUCT_NAME, ("", None, "Frappe", "ERPNext"))
	_set_if_default("Website Settings", "app_logo", LOGO, ("", None))
	_set_if_default("Website Settings", "favicon", FAVICON, ("", None))
	_set_if_default("Website Settings", "copyright", FOOTER, ("", None))
	_set_if_default("Website Settings", "disable_signup", 1, ("", None, 0))
	ensure_print_style()
	ensure_letter_head()
	_set_if_default("Print Settings", "print_style", PRINT_STYLE, ("", None, "Redesign", "Modern", "Classic"))


def _set_if_default(doctype, field, value, defaults):
	if not frappe.get_meta(doctype).has_field(field):
		return
	if frappe.db.get_single_value(doctype, field) in defaults:
		frappe.db.set_single_value(doctype, field, value)


def ensure_print_style():
	css = frappe.read_file(frappe.get_app_path("pvfss", "templates", "print", "pvfss_print.css"))
	if frappe.db.exists("Print Style", PRINT_STYLE):
		frappe.db.set_value("Print Style", PRINT_STYLE, "css", css)
		return
	frappe.get_doc(
		{"doctype": "Print Style", "print_style_name": PRINT_STYLE, "css": css, "standard": 0}
	).insert(ignore_permissions=True)


def ensure_letter_head():
	header = frappe.read_file(frappe.get_app_path("pvfss", "templates", "print", "letter_head.html"))
	footer = frappe.read_file(frappe.get_app_path("pvfss", "templates", "print", "letter_head_footer.html"))
	values = {
		"source": "HTML",
		"content": header,
		"footer_source": "HTML",
		"footer": footer,
		"is_default": 1,
	}
	if frappe.db.exists("Letter Head", LETTER_HEAD):
		frappe.db.set_value("Letter Head", LETTER_HEAD, values)
		return
	frappe.get_doc({"doctype": "Letter Head", "letter_head_name": LETTER_HEAD, **values}).insert(
		ignore_permissions=True
	)
