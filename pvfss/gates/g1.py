"""G1: technical compliance before a customer Quotation (RFQ-11, RFQ-12, SCR-RFQ-10)."""

import frappe
from frappe import _

from pvfss.gates.base import GateResult
from pvfss.pvfss_crm.doctype.technical_evaluation import technical_evaluation as te_module


def check(costing_sheet):
	"""Return a GateResult for creating a Quotation from ``costing_sheet``."""
	doc = frappe.get_doc("Costing Sheet", costing_sheet) if isinstance(costing_sheet, str) else costing_sheet
	result = GateResult(_("Quotation cannot be created"), doc=doc, gate="G1")
	if doc.docstatus != 1:
		result.fail(
			_("Submit the Costing Sheet first."), doctype="Costing Sheet", name=doc.name, rule="RFQ-12"
		)
	if not doc.items:
		result.fail(
			_("The Costing Sheet has no lines."), doctype="Costing Sheet", name=doc.name, rule="RFQ-12"
		)
	te, status = te_module.status_by_sq_item(doc.inquiry)
	if not te:
		result.fail(
			_("No submitted Technical Evaluation for inquiry {0}.").format(doc.inquiry),
			doctype="Opportunity",
			name=doc.inquiry,
			rule="RFQ-12",
		)
		return result
	bad = [
		row.line_ref
		for row in doc.items
		if status.get(row.supplier_quotation_item) not in te_module.COMPLIANT
	]
	if bad:
		result.fail(
			_(
				"Lines {0} are not technically compliant. Re-select suppliers on the Competitive Statement."
			).format(", ".join(bad)),
			doctype="Technical Evaluation",
			name=te.name,
			rule="RFQ-12",
		)
	return result
