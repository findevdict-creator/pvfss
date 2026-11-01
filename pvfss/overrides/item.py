"""Item doc events (MD-12, MD-13, SCR-MD-05)."""

import frappe
from frappe import _


def validate(doc, method=None):
	# Services and non-stock items never need heat traceability.
	if not doc.is_stock_item:
		doc.pvfss_heat_traceable = 0
		return

	# SCR-MD-05: a heat-traceable stock item must be batch-tracked so heats can be traced (TRC-01).
	if doc.get("pvfss_heat_traceable") and not doc.has_batch_no:
		has_stock = not doc.is_new() and frappe.db.exists(
			"Stock Ledger Entry", {"item_code": doc.name, "is_cancelled": 0}
		)
		if has_stock:
			frappe.throw(
				_("Item {0} is heat traceable, so Has Batch No must be ticked.").format(
					frappe.bold(doc.name)
				),
				title=_("Heat traceability"),
			)
		doc.has_batch_no = 1
