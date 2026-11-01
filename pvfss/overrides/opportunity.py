"""Inquiry (Opportunity) doc events (CRM-01 to CRM-09)."""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, get_link_to_form

from pvfss.pvfss_crm import inquiry as inq


def validate(doc, method=None):
	doc.opportunity_from = "Customer"  # CRM-01
	if not doc.pvfss_owner:
		doc.pvfss_owner = doc.owner if doc.owner and doc.owner != "Guest" else frappe.session.user
	doc.opportunity_owner = doc.pvfss_owner
	if doc.pvfss_contractor_ref:
		doc.pvfss_contractor_ref = doc.pvfss_contractor_ref.strip()
	if not doc.pvfss_portal and doc.party_name:
		doc.pvfss_portal = frappe.db.get_value("Customer", doc.party_name, "pvfss_portal_name")

	validate_dates(doc)
	validate_client_project(doc)
	validate_lines(doc)
	validate_stage_change(doc)
	validate_outcome(doc)
	check_duplicate(doc)
	doc.pvfss_line_count = len(doc.items or [])
	inq.refresh_outcome(doc)


def after_insert(doc, method=None):
	"""CRM-09: assign the inquiry owner."""
	from frappe.desk.form.assign_to import _add as assign

	if doc.pvfss_owner and frappe.db.exists("User", doc.pvfss_owner):
		assign(
			{
				"assign_to": [doc.pvfss_owner],
				"doctype": doc.doctype,
				"name": doc.name,
				"description": _("Inquiry {0} from {1}, due {2}").format(
					doc.name, doc.customer_name or doc.party_name, doc.pvfss_bid_due_date
				),
				"date": get_datetime(doc.pvfss_bid_due_date).date() if doc.pvfss_bid_due_date else None,
			},
			ignore_permissions=True,
		)


def validate_dates(doc):
	if doc.pvfss_received_on and doc.pvfss_bid_due_date:
		if get_datetime(doc.pvfss_bid_due_date) <= get_datetime(doc.pvfss_received_on):
			frappe.throw(_("Bid due date must be after Received on."), title=_("Inquiry dates"))


def validate_client_project(doc):
	if not doc.pvfss_client_project:
		return
	contractor = frappe.db.get_value("Client Project", doc.pvfss_client_project, "main_contractor")
	if (
		contractor
		and doc.party_name
		and contractor != doc.party_name
		and doc.has_value_changed("pvfss_client_project")
	):
		frappe.msgprint(
			_("Client project {0} has main contractor {1}, not {2}.").format(
				doc.pvfss_client_project, contractor, doc.party_name
			),
			indicator="orange",
			alert=True,
		)


def validate_lines(doc):
	"""CRM-03: specification text per line; line refs unique within the inquiry."""
	seen = {}
	missing = []
	for row in doc.items or []:
		if not (row.pvfss_specification or "").strip():
			missing.append(str(row.idx))
		ref = (row.pvfss_customer_line_ref or "").strip()
		if ref:
			if ref in seen:
				frappe.throw(
					_("Line ref {0} is used on rows {1} and {2}.").format(
						frappe.bold(ref), seen[ref], row.idx
					),
					title=_("Duplicate line ref"),
				)
			seen[ref] = row.idx
	if missing:
		frappe.throw(
			_("Specification is required on every line. Missing on rows: {0}").format(", ".join(missing)),
			title=_("Inquiry lines"),
		)


def validate_stage_change(doc):
	"""CRM-06: stage changes only through linked documents or the No Bid / Cancel action."""
	if doc.is_new():
		doc.pvfss_stage = inq.NEW
		return
	if doc.has_value_changed("pvfss_stage") and not doc.flags.pvfss_stage_change:
		frappe.throw(
			_("Stage is set automatically. Use Mark No Bid / Cancel to close an inquiry by hand."),
			title=_("Inquiry stage"),
		)
	if doc.has_value_changed("pvfss_stage") and doc.pvfss_stage != inq.NEW:
		inq.assert_not_unconfirmed_duplicate(doc)


def validate_outcome(doc):
	"""CRM-08: Lost / No Bid need a lost reason and a detail."""
	if doc.pvfss_stage in inq.NEEDS_REASON:
		if not doc.lost_reasons:
			frappe.throw(
				_("Select at least one Lost Reason."), title=_("Inquiry {0}").format(_(doc.pvfss_stage))
			)
		if not (doc.order_lost_reason or "").strip():
			frappe.throw(_("Enter the lost detail."), title=_("Inquiry {0}").format(_(doc.pvfss_stage)))


def check_duplicate(doc):
	"""CRM-05 [RULE]: warn on save, block progress until confirmed."""
	duplicate = inq.find_duplicate(doc)
	doc.pvfss_duplicate_of = duplicate
	if not duplicate:
		doc.pvfss_not_duplicate = 0
		return
	if cint(doc.pvfss_not_duplicate):
		return
	other = frappe.db.get_value("Opportunity", duplicate, ["pvfss_stage", "pvfss_owner"], as_dict=True)
	frappe.msgprint(
		_(
			"Possible duplicate of {0} (stage {1}, owner {2}). Tick 'Confirmed not a duplicate' to continue."
		).format(
			get_link_to_form("Opportunity", duplicate), _(other.pvfss_stage or inq.NEW), other.pvfss_owner
		),
		title=_("Possible duplicate inquiry"),
		indicator="orange",
	)


# ----------------------------------------------------------------------------- linked documents (CRM-07)
def on_supplier_quotation_submit(doc, method=None):
	if doc.get("opportunity"):
		inq.advance(doc.opportunity, inq.QUOTES_RECEIVED, source=doc.name)


def on_quotation_submit(doc, method=None):
	if doc.get("opportunity"):
		if not inq.advance(doc.opportunity, inq.QUOTED, source=doc.name):
			_refresh(doc.opportunity)


def on_quotation_update_after_submit(doc, method=None):
	"""Quotation marked Lost -> Inquiry Lost, carrying the lost reasons."""
	if not doc.get("opportunity") or doc.status != "Lost":
		return
	inquiry = frappe.get_doc("Opportunity", doc.opportunity)
	if inquiry.pvfss_stage in inq.CLOSED:
		return
	if not inquiry.lost_reasons:
		reasons = [r.lost_reason for r in doc.get("lost_reasons") or []]
		reasons = [r for r in reasons if frappe.db.exists("Opportunity Lost Reason", r)] or ["Other"]
		inquiry.set("lost_reasons", [{"lost_reason": r} for r in reasons])
	inquiry.order_lost_reason = (
		inquiry.order_lost_reason or doc.get("order_lost_reason") or _("Quotation {0} lost").format(doc.name)
	)
	inquiry.pvfss_stage = inq.LOST
	inquiry.flags.pvfss_stage_change = True
	inquiry.flags.ignore_permissions = True
	inquiry.save()


def on_sales_order_submit(doc, method=None):
	for quotation in {row.prevdoc_docname for row in doc.items if row.get("prevdoc_docname")}:
		inquiry = frappe.db.get_value("Quotation", quotation, "opportunity")
		if inquiry:
			inq.advance(inquiry, inq.WON, source=doc.name)


def _refresh(inquiry):
	doc = frappe.get_doc("Opportunity", inquiry)
	doc.flags.ignore_permissions = True
	doc.save()
