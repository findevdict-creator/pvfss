"""Write the role permission matrix as Custom DocPerm rows (GEN-21).

Developer helper; production gets the exported fixtures.

    bench --site pvfss.localhost execute pvfss.setup.permissions.apply
    bench --site pvfss.localhost export-fixtures --app pvfss
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

from pvfss.permission_matrix import MATRIX

RIGHTS = {
	"r": ("read", "print", "email", "export", "report", "share"),
	"w": ("write",),
	"c": ("create",),
	"s": ("submit",),
	"x": ("cancel",),
	"a": ("amend",),
	"d": ("delete",),
}


def apply(doctypes=None):
	for doctype, roles in MATRIX.items():
		if doctypes and doctype not in doctypes:
			continue
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		for role, rights in roles.items():
			add_permission(doctype, role, 0)
			wanted = set()
			for code in rights:
				wanted.update(RIGHTS[code])
			for ptype in (
				"read",
				"write",
				"create",
				"submit",
				"cancel",
				"amend",
				"delete",
				"print",
				"email",
				"export",
				"report",
				"share",
			):
				if ptype in ("submit", "cancel", "amend") and not meta.is_submittable:
					continue
				if ptype == "report" and meta.issingle:
					continue
				update_permission_property(
					doctype, role, 0, ptype, 1 if ptype in wanted else 0, validate=False
				)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (setup step run from install / setup wizard hooks; later steps need it persisted)
	frappe.clear_cache()
