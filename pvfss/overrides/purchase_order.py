"""Purchase Order (Supplier PO) doc events. 05: supplier eligibility (SUP-07). 08 adds PUR rules."""

import frappe
from frappe import _

from pvfss.gates.base import GateResult
from pvfss.pvfss_crm import supplier_rules


def validate(doc, method=None):
	check_supplier(doc)


def check_supplier(doc):
	"""SUP-07 [RULE]: no PO to a Suspended / Blacklisted supplier; warn for conditional ones."""
	result = GateResult(_("Supplier not allowed"), doc=doc, gate="SUP-07")
	warning = supplier_rules.check_status(result, doc.supplier)
	result.throw_if_failed()
	if warning:
		frappe.msgprint(frappe.utils.escape_html(warning), indicator="orange", alert=True)
