"""Request for Quotation doc events. 05: supplier eligibility (SUP-07). 06 adds RFQ-01 onwards."""

import frappe
from frappe import _

from pvfss.gates.base import GateResult
from pvfss.pvfss_crm import supplier_rules


def validate(doc, method=None):
	check_suppliers(doc)


def check_suppliers(doc):
	"""SUP-07 [RULE]: no RFQ to a Suspended / Blacklisted supplier; warn for conditional ones."""
	result = GateResult(_("Supplier not allowed"), doc=doc, gate="SUP-07")
	warnings = []
	for row in doc.suppliers or []:
		warning = supplier_rules.check_status(result, row.supplier)
		if warning:
			warnings.append(warning)
	result.throw_if_failed()
	if warnings:
		frappe.msgprint(
			"<br>".join(frappe.utils.escape_html(w) for w in warnings), indicator="orange", alert=True
		)
