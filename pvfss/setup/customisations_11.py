"""Developer helper for step 11-smr: the SMR link on Purchase Receipt (SMR-30).

bench --site pvfss.localhost execute pvfss.setup.customisations_11.apply
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from pvfss.patches import batch_tally_sheet_link
from pvfss.setup import customisations_10

MODULE = "PVFSS Quality"


def custom_fields():
	return {
		"Purchase Receipt": [
			{
				"fieldname": "pvfss_smr",
				"fieldtype": "Link",
				"label": "SMR",
				"options": "SMR",
				"insert_after": "supplier_delivery_note",
				"read_only": 1,
				"no_copy": 1,
				"description": "Ready-stock offer this receipt was created from (SMR-30).",
			}
		],
	}


def apply():
	batch_tally_sheet_link.execute()
	customisations_10.apply()  # Batch tally sheet field is now a Link to Tally Sheet
	fields = custom_fields()
	for rows in fields.values():
		for f in rows:
			f.setdefault("module", MODULE)
	create_custom_fields(fields, update=True)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (developer command run from bench execute, outside a request)
	print("11-smr customisations applied")
