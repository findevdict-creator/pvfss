"""10-traceability: heat traceability needs serial / batch tracking switched on (TRC-01, TRC-02)."""

import frappe


def execute():
	frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
