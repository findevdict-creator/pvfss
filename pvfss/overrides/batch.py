"""Batch doc events (TRC-02): one batch = one heat + one lot + one item, named {heat}-{lot}."""

import frappe
from frappe import _

from pvfss.pvfss_quality import traceability


def before_insert(doc, method=None):
	if not doc.batch_id and doc.get("pvfss_heat_number") and doc.get("pvfss_lot_no"):
		candidate = f"{doc.pvfss_heat_number}-{doc.pvfss_lot_no}".replace(" ", "")
		if not frappe.db.exists("Batch", candidate):
			doc.batch_id = candidate


def validate(doc, method=None):
	if traceability.is_heat_traceable(doc.item) and not doc.get("pvfss_heat_number"):
		frappe.throw(
			_("Item {0} is heat traceable: enter the heat number on batch {1}.").format(
				doc.item, doc.batch_id or doc.name or ""
			),
			frappe.MandatoryError,
			title=_("Heat number required"),
		)
	if doc.get("pvfss_heat_number"):
		doc.pvfss_heat_status = frappe.db.get_value("Heat Number", doc.pvfss_heat_number, "status")
		before = doc.get_doc_before_save()
		if before and before.get("pvfss_heat_number") and before.pvfss_heat_number != doc.pvfss_heat_number:
			if frappe.db.exists("Serial and Batch Entry", {"batch_no": doc.name, "is_cancelled": 0, "docstatus": 1}):
				frappe.throw(_("The heat number of a batch with stock transactions cannot change."))
