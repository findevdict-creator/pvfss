"""User doc events (NFR-04)."""

import frappe
from frappe import _

from pvfss.setup import workspaces
from pvfss.setup.defaults import MIN_PASSWORD_LENGTH


def before_validate(doc, method=None):
	# before_validate: User.validate moves new_password to a private attribute.
	new_password = doc.get("new_password")
	if new_password and len(new_password) < MIN_PASSWORD_LENGTH:
		frappe.throw(
			_("Password must be at least {0} characters long.").format(MIN_PASSWORD_LENGTH),
			title=_("Password policy"),
		)


def validate(doc, method=None):
	workspaces.set_default_workspace(doc)  # RPT-01
