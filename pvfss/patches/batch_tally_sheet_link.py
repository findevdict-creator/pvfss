"""11-smr: Batch.pvfss_tally_sheet changes from Data to a Link to Tally Sheet.

Frappe does not allow a custom field's type to change from Data to Link, so the old field is
removed here and recreated from the fixtures, which sync after this patch. The column held no
data before 11-smr (no tally sheets existed).
"""

import frappe


def execute():
	name = "Batch-pvfss_tally_sheet"
	if frappe.db.get_value("Custom Field", name, "fieldtype") == "Data":
		frappe.delete_doc("Custom Field", name, ignore_permissions=True)
