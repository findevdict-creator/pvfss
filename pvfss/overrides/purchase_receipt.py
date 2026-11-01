"""Purchase Receipt doc events (TRC-02, TRC-03 / G6)."""

import frappe

from pvfss.gates import g6
from pvfss.pvfss_quality import traceability


def before_submit(doc, method=None):
	g6.check(doc).throw_if_failed()


def on_submit(doc, method=None):
	link_batches_to_po(doc)
	traceability.refresh_for_document(doc)


def on_cancel(doc, method=None):
	traceability.refresh_for_document(doc)


def link_batches_to_po(doc):
	"""TRC-02: a batch received against a Supplier PO remembers it."""
	for row in doc.items:
		if not row.get("purchase_order"):
			continue
		for batch, _qty in traceability.row_batches(row):
			if not frappe.db.get_value("Batch", batch, "pvfss_supplier_po"):
				frappe.db.set_value("Batch", batch, "pvfss_supplier_po", row.purchase_order, update_modified=False)
