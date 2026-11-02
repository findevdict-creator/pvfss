"""Non Conformance (NCR) doc events (QA-30, QA-31, TRC-04, SCR-QA-16)."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate

from pvfss.pvfss_quality import traceability
from pvfss.utils import alerts, settings

CLOSED = "Closed"
HOLD_SEVERITIES = ("Major", "Critical")


def is_open(doc):
	return doc.get("workflow_state") != CLOSED and doc.status != "Cancelled"


def validate(doc, method=None):
	if not doc.get("pvfss_source"):
		return  # an ERPNext quality NCR without PVFSS fields
	doc.pvfss_raised_by = doc.pvfss_raised_by or frappe.session.user
	doc.pvfss_raised_on = doc.pvfss_raised_on or nowdate()
	if not doc.pvfss_response_due:
		doc.pvfss_response_due = add_days(doc.pvfss_raised_on, settings.get_int("ncr_response_days", 7))
	if doc.pvfss_source_document and not doc.pvfss_source_doctype:
		doc.pvfss_source_doctype = {
			"Inspection Report": "Inspection Report",
			"SMR": "SMR",
			"Receipt": "Purchase Receipt",
			"MTC review": "MTC",
		}.get(doc.pvfss_source)
	for row in doc.pvfss_heats:
		if row.batch and not row.heat_number:
			row.heat_number = frappe.db.get_value("Batch", row.batch, "pvfss_heat_number")
		if row.heat_number and not row.item_code:
			row.item_code = frappe.db.get_value("Heat Number", row.heat_number, "item_code")
	doc.pvfss_heat_list = ", ".join(sorted({r.heat_number for r in doc.pvfss_heats if r.heat_number}))
	if doc.get("workflow_state") == CLOSED:
		if not (doc.pvfss_verified_by and doc.pvfss_verification_date):
			frappe.throw(_("Record who verified the closure and when."), title=_("NCR closure"))
		doc.status = "Resolved"
	if (
		doc.pvfss_disposition == "Use as is"
		and doc.get("workflow_state") == CLOSED
		and not doc.pvfss_concession_ref
	):
		frappe.throw(_("A Use as is disposition needs the customer concession reference."))


def on_update(doc, method=None):
	"""TRC-04: a Major / Critical NCR holds the affected heats; closing releases them."""
	if not doc.get("pvfss_source"):
		return
	before = doc.get_doc_before_save()
	heats = {r.heat_number for r in doc.pvfss_heats if r.heat_number}
	if before:
		heats |= {r.heat_number for r in before.get("pvfss_heats") or [] if r.heat_number}
	for heat in heats:
		sync_heat(heat)


def sync_heat(heat):
	holding = holding_ncrs(heat)
	status = frappe.db.get_value("Heat Number", heat, "status")
	if holding and status == "Active":
		traceability.set_heat_status(heat, "On hold", _("NCR {0}").format(", ".join(holding)))
	elif not holding and status == "On hold":
		traceability.set_heat_status(heat, "Active", _("NCRs closed"))


def open_ncrs(heats):
	"""{heat: [ncr names]} for NCRs that are not Closed."""
	if not heats:
		return {}
	rows = frappe.db.sql(
		"""select h.heat_number, nc.name, nc.pvfss_severity
		from `tabNCR Heat` h join `tabNon Conformance` nc on nc.name = h.parent
		where h.parenttype = 'Non Conformance' and h.heat_number in %(heats)s
			and coalesce(nc.workflow_state, '') != 'Closed' and nc.status != 'Cancelled'""",
		{"heats": tuple(heats)},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.heat_number, []).append(r)
	return out


def holding_ncrs(heat):
	return sorted({r.name for r in open_ncrs([heat]).get(heat, []) if r.pvfss_severity in HOLD_SEVERITIES})


# ----------------------------------------------------------------------------- QA-31
def overdue_alerts():
	"""Daily: supplier response overdue -> Quality and the project's Post-Bidding owner."""
	today = getdate(nowdate())
	rows = frappe.get_all(
		"Non Conformance",
		filters={
			"pvfss_response_due": ["<", today],
			"pvfss_supplier_response_date": ["is", "not set"],
			"pvfss_alerted_on": ["is", "not set"],
			"workflow_state": ["!=", CLOSED],
			"status": ["!=", "Cancelled"],
		},
		fields=["name", "subject", "pvfss_supplier", "pvfss_project", "pvfss_response_due", "pvfss_severity"],
	)
	quality = alerts.users_with_role("Quality User", "Quality Manager")
	for row in rows:
		owner = row.pvfss_project and frappe.db.get_value(
			"Project", row.pvfss_project, "pvfss_post_bidding_owner"
		)
		subject = _("NCR {0} ({1}): supplier response overdue since {2} ({3}).").format(
			row.name,
			row.pvfss_severity,
			frappe.utils.formatdate(row.pvfss_response_due),
			row.pvfss_supplier or "-",
		)
		alerts.send(quality + ([owner] if owner else []), subject, "Non Conformance", row.name)
		frappe.db.set_value("Non Conformance", row.name, "pvfss_alerted_on", today, update_modified=False)
	return len(rows)
