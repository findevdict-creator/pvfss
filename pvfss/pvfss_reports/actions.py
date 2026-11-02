"""The "Needs your action" strip at the top of every team workspace (screens §19.1).

It lists what waits on the current user: documents in a workflow state that one of the
user's roles can act on, open ToDos assigned to the user, and each workspace's overdue items.
Counts use ``frappe.get_list`` so they respect the user's permissions.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, now_datetime

from pvfss.pvfss_crm import inquiry as stages
from pvfss.pvfss_reports.kpi import today

# DocTypes whose workflow approvals show on each workspace
WORKSPACE_DOCTYPES = {
	"PVFSS Management": ("Quotation", "Purchase Order", "Payment Entry", "Project"),
	"PVFSS Pre-Bidding": ("Quotation", "Project Handover"),
	"PVFSS Post-Bidding": (
		"Sales Order",
		"Purchase Order",
		"Project Handover",
		"Project Change",
		"Delivery Note",
	),
	"PVFSS Quality": ("MTC", "IRN", "SMR", "ITP", "Non Conformance"),
	"PVFSS Logistics": ("Delivery Note",),
	"PVFSS Finance": ("Payment Entry", "Petty Cash Voucher"),
	"PVFSS HSE": ("HSE Incident",),
	"PVFSS ICV": (),
	"PVFSS Documents": (),
}


def _me():
	return frappe.session.user


def _extras():
	"""Overdue and waiting items per workspace: (label, doctype, filters)."""
	now, day = now_datetime(), today()
	return {
		"PVFSS Pre-Bidding": [
			(
				_("My inquiries due in 3 days"),
				"Opportunity",
				{
					"pvfss_owner": _me(),
					"pvfss_stage": ["in", stages.PROGRESS],
					"pvfss_bid_due_date": ["<=", add_to_date(now, days=3)],
				},
			),
			(
				_("Supplier quotations past validity"),
				"Supplier Quotation",
				{"docstatus": 1, "status": "Submitted", "valid_till": ["<", day]},
			),
		],
		"PVFSS Post-Bidding": [
			(
				_("Late expediting on my projects"),
				"Expediting Log",
				{
					"status": "Late",
					"project": [
						"in",
						frappe.get_all("Project", {"pvfss_post_bidding_owner": _me()}, pluck="name") or [""],
					],
				},
			),
		],
		"PVFSS Quality": [
			(_("RFIs to schedule"), "RFI", {"status": "Raised"}),
			(
				_("NCRs past supplier response date"),
				"Non Conformance",
				{
					"status": "Open",
					"pvfss_response_due": ["<", day],
					"pvfss_supplier_response_date": ["is", "not set"],
				},
			),
		],
		"PVFSS Logistics": [
			(
				_("Delivery Notes with documents pending"),
				"Delivery Note",
				[
					["docstatus", "=", 0],
					["Dispatch Document", "status", "=", "Pending"],
					["Dispatch Document", "required", "=", 1],
				],
			),
			(
				_("ETA passed and no POD"),
				"Delivery Note",
				{"docstatus": 1, "pvfss_eta": ["<", day], "pvfss_pod_date": ["is", "not set"]},
			),
		],
		"PVFSS Finance": [
			(_("Retentions due"), "Retention", {"status": "Held", "release_due_date": ["<=", day]}),
			(
				_("LCs expiring in 30 days"),
				"Letter of Credit",
				{
					"docstatus": 1,
					"status": ["not in", ("Paid", "Expired", "Closed")],
					"expiry_date": ["between", [day, add_days(day, 30)]],
				},
			),
			(
				_("PDCs maturing in 14 days"),
				"Post-Dated Cheque",
				{
					"docstatus": 1,
					"status": ["in", ("In hand", "Deposited")],
					"cheque_date": ["between", [day, add_days(day, 14)]],
				},
			),
		],
		"PVFSS HSE": [
			(
				_("Incidents not investigated after 48 hours"),
				"HSE Incident",
				{"workflow_state": "Reported", "reported_on": ["<", add_to_date(now, hours=-48)]},
			),
			(_("CAPAs overdue"), "CAPA", {"status": "Overdue"}),
			(_("Trainings expiring"), "HSE Training Record", {"status": "Expiring"}),
			(
				_("Permits expiring in 24 hours"),
				"Permit to Work",
				{"status": "Issued", "valid_to": ["<=", add_to_date(now, hours=24)]},
			),
			(_("Risk reviews due"), "HSE Risk Register", {"review_date": ["<=", day]}),
		],
		"PVFSS Documents": [
			(_("Documents checked out by me"), "Project Document", {"locked_by": _me()}),
		],
	}


def _count(doctype, filters):
	if not frappe.has_permission(doctype, "read"):
		return 0
	return len(set(frappe.get_list(doctype, filters=filters, pluck="name", limit_page_length=500)))


def workflow_items(doctypes=None):
	"""Workflow states one of the user's roles can move a document out of.

	A transition made by the same role that edits the state (an author sending their own draft
	on) is the author's own work, not an approval waiting on them, so it is left out.
	"""
	roles = set(frappe.get_roles())
	items = []
	filters = {"is_active": 1}
	if doctypes is not None:
		if not doctypes:
			return []
		filters["document_type"] = ["in", list(doctypes)]
	for wf in frappe.get_all("Workflow", filters=filters, fields=["name", "document_type"]):
		editors = dict(
			frappe.get_all(
				"Workflow Document State",
				filters={"parent": wf.name},
				fields=["state", "allow_edit"],
				as_list=True,
			)
		)
		actionable = []
		for t in frappe.get_all(
			"Workflow Transition",
			filters={"parent": wf.name},
			fields=["state", "allowed"],
			order_by="idx asc",
		):
			if t.allowed in roles and t.allowed != editors.get(t.state) and t.state not in actionable:
				actionable.append(t.state)
		for state in actionable:
			count = _count(wf.document_type, {"workflow_state": state, "docstatus": ["<", 2]})
			if count:
				items.append(
					{
						"label": _("{0}: {1}").format(_(wf.document_type), _(state)),
						"count": count,
						"route": ["List", wf.document_type],
						"route_options": {"workflow_state": state},
					}
				)
	return items


def workspace_name(value):
	"""The workspace name from its name, title or URL slug (pvfss-quality)."""
	if not value:
		return None
	for name in WORKSPACE_DOCTYPES:
		if (
			value in (name, name.replace("PVFSS ", ""))
			or frappe.scrub(name).replace("_", "-") == value.lower()
		):
			return name
	return value


@frappe.whitelist()
def get(workspace: str | None = None):
	workspace = workspace_name(workspace)
	items = workflow_items(WORKSPACE_DOCTYPES.get(workspace))
	todos = _count("ToDo", {"allocated_to": _me(), "status": "Open"})
	if todos:
		items.append(
			{
				"label": _("My open ToDos"),
				"count": todos,
				"route": ["List", "ToDo"],
				"route_options": {"allocated_to": _me(), "status": "Open"},
			}
		)
	for label, doctype, filters in _extras().get(workspace, []):
		count = _count(doctype, filters)
		if count:
			items.append(
				{
					"label": label,
					"count": count,
					"route": ["List", doctype],
					"route_options": _route_options(filters),
				}
			)
	return items


def _route_options(filters):
	"""List view route options: plain values pass through, operators become [op, value]."""
	if isinstance(filters, list):
		return {}
	out = {}
	for key, value in filters.items():
		out[key] = value if not isinstance(value, list) else [value[0], value[1]]
	return out
