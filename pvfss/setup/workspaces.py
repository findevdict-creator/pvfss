"""Workspace setup (RPT-01, RPT-10): the "Needs your action" block, landing workspaces, weekly email.

Idempotent; runs on install and migrate.
"""

import os

import frappe

ACTION_BLOCK = "PVFSS Needs Your Action"
BLOCK_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pvfss_reports", "blocks")

# RPT-01: users land on their team workspace; the first matching role wins.
ROLE_WORKSPACE = (
	("PVFSS Director", "PVFSS Management"),
	("Finance Manager", "PVFSS Finance"),
	("Quality Manager", "PVFSS Quality"),
	("Post-Bidding Manager", "PVFSS Post-Bidding"),
	("Pre-Bidding Manager", "PVFSS Pre-Bidding"),
	("HSE Manager", "PVFSS HSE"),
	("Finance User", "PVFSS Finance"),
	("Quality User", "PVFSS Quality"),
	("Post-Bidding User", "PVFSS Post-Bidding"),
	("Pre-Bidding User", "PVFSS Pre-Bidding"),
	("Logistics User", "PVFSS Logistics"),
	("HSE User", "PVFSS HSE"),
	("ICV User", "PVFSS ICV"),
	("PVFSS Read Only", "PVFSS Management"),
)
TEAM_WORKSPACES = {ws for _role, ws in ROLE_WORKSPACE}

MANAGEMENT_EMAIL_REPORT = "Management KPI Summary"


def apply():
	apply_action_block()
	setup_management_email()


def _read(name):
	# nosemgrep: frappe-security-file-traversal (name is one of the three fixed block file names below)
	with open(os.path.join(BLOCK_DIR, name)) as f:
		return f.read()


def apply_action_block():
	values = {
		"html": _read("needs_your_action.html"),
		"script": _read("needs_your_action.js"),
		"style": _read("needs_your_action.css"),
		"private": 0,
	}
	if frappe.db.exists("Custom HTML Block", ACTION_BLOCK):
		doc = frappe.get_doc("Custom HTML Block", ACTION_BLOCK)
		if all(doc.get(k) == v for k, v in values.items()):
			return
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.new_doc("Custom HTML Block")
		doc.update(values)
		doc.insert(ignore_permissions=True, set_name=ACTION_BLOCK)


def workspace_for(roles):
	roles = set(roles)
	for role, workspace in ROLE_WORKSPACE:
		if role in roles and frappe.db.exists("Workspace", workspace):
			return workspace
	return None


def set_default_workspace(doc):
	"""User validate: land on the team workspace unless the user chose another (RPT-01)."""
	if doc.user_type != "System User":
		return
	if doc.default_workspace and doc.default_workspace not in TEAM_WORKSPACES:
		return
	workspace = workspace_for(r.role for r in doc.roles)
	if workspace:
		doc.default_workspace = workspace


def setup_management_email():
	"""RPT-10: weekly management email to the Directors, Sundays (Auto Email Report)."""
	if not frappe.db.exists("Report", MANAGEMENT_EMAIL_REPORT):
		return
	directors = frappe.get_all(
		"Has Role",
		filters={
			"role": "PVFSS Director",
			"parenttype": "User",
			"parent": ["not in", ("Administrator", "Guest")],
		},
		pluck="parent",
	)
	emails = sorted(
		e
		for e in frappe.get_all(
			"User", filters={"name": ["in", directors or [""]], "enabled": 1}, pluck="email"
		)
		if e
	)
	if not emails:
		return
	name = frappe.db.get_value("Auto Email Report", {"report": MANAGEMENT_EMAIL_REPORT}, "name")
	doc = frappe.get_doc("Auto Email Report", name) if name else frappe.new_doc("Auto Email Report")
	if name and not doc.enabled:
		return  # switched off on purpose
	doc.update(
		{
			"report": MANAGEMENT_EMAIL_REPORT,
			"user": "Administrator",
			"enabled": 1,
			"frequency": "Weekly",
			"day_of_week": "Sunday",
			"format": "HTML",
			"email_to": "\n".join(emails),
			"description": "<p>Management weekly (RPT-10)</p>",
		}
	)
	doc.flags.ignore_permissions = True
	if name:
		doc.save()
	else:
		doc.insert()
