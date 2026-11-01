"""Inquiry (Opportunity) stage engine and actions (CRM-05 to CRM-09).

Stage is the main status of an inquiry. It only moves forward through linked documents
(CRM-07); the only manual moves are to No Bid or Cancelled (CRM-06, SCR-CRM-05).
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

from pvfss.utils import settings

NEW = "New"
RFQ_SENT = "RFQ Sent"
QUOTES_RECEIVED = "Quotes Received"
UNDER_EVALUATION = "Under Evaluation"
QUOTED = "Quoted"
WON = "Won"
LOST = "Lost"
NO_BID = "No Bid"
CANCELLED = "Cancelled"

PROGRESS = [NEW, RFQ_SENT, QUOTES_RECEIVED, UNDER_EVALUATION, QUOTED]
CLOSED = (WON, LOST, NO_BID, CANCELLED)
MANUAL = (NO_BID, CANCELLED)
NEEDS_REASON = (LOST, NO_BID)

STAGE_COLOURS = {
	NEW: "blue",
	RFQ_SENT: "blue",
	QUOTES_RECEIVED: "blue",
	UNDER_EVALUATION: "orange",
	QUOTED: "orange",
	WON: "green",
	LOST: "red",
	NO_BID: "gray",
	CANCELLED: "gray",
}


def rank(stage):
	if stage in PROGRESS:
		return PROGRESS.index(stage)
	return len(PROGRESS)  # closed stages rank above every open one


# ----------------------------------------------------------------------------- stage engine
def advance(inquiry, stage, source=None):
	"""Move ``inquiry`` to ``stage`` if that is a forward move (CRM-07). Returns True if moved.

	Won and Lost may replace Quoted; a closed inquiry never moves again (except Lost -> Won
	when a Customer PO arrives on a quotation that was marked lost and then revived).
	"""
	if not inquiry or not frappe.db.exists("Opportunity", inquiry):
		return False
	doc = frappe.get_doc("Opportunity", inquiry)
	current = doc.pvfss_stage or NEW

	if current in CLOSED and not (current == LOST and stage == WON):
		return False
	if stage not in CLOSED and rank(stage) <= rank(current):
		return False

	doc.pvfss_stage = stage
	doc.flags.pvfss_stage_change = True
	doc.flags.ignore_permissions = True
	if source:
		doc.add_comment("Info", _("Stage changed to {0} by {1}").format(_(stage), source))
	doc.save()
	return True


def assert_not_unconfirmed_duplicate(doc):
	"""CRM-05: an unconfirmed possible duplicate cannot progress past New."""
	if doc.pvfss_duplicate_of and not cint(doc.pvfss_not_duplicate):
		frappe.throw(
			_("Inquiry {0} may duplicate {1}. Tick 'Confirmed not a duplicate' to continue.").format(
				doc.name, frappe.utils.get_link_to_form("Opportunity", doc.pvfss_duplicate_of)
			),
			title=_("Possible duplicate inquiry"),
		)


def find_duplicate(doc):
	"""Another open inquiry with the same contractor and contractor ref (CRM-05)."""
	if not (doc.party_name and doc.pvfss_contractor_ref):
		return None
	return frappe.db.get_value(
		"Opportunity",
		{
			"party_name": doc.party_name,
			"pvfss_contractor_ref": doc.pvfss_contractor_ref.strip(),
			"name": ["!=", doc.name or ""],
			"pvfss_stage": ["not in", CLOSED],
		},
		"name",
	)


# ----------------------------------------------------------------------------- outcome
def refresh_outcome(doc):
	"""Quoted value, first-quoted date and turnaround (SCR-CRM-02 tab 4)."""
	quotations = frappe.get_all(
		"Quotation",
		filters={"opportunity": doc.name, "docstatus": 1},
		fields=["name", "base_net_total", "transaction_date", "status"],
		order_by="transaction_date asc, creation asc",
	)
	if not quotations:
		return
	active = [q for q in quotations if q.status != "Lost"] or quotations
	doc.pvfss_quoted_value = flt(active[-1].base_net_total)
	doc.pvfss_quoted_on = quotations[0].transaction_date
	if doc.pvfss_received_on:
		doc.pvfss_turnaround_days = max(date_diff(doc.pvfss_quoted_on, getdate(doc.pvfss_received_on)), 0)


# ----------------------------------------------------------------------------- manual close
@frappe.whitelist()
def mark_closed(inquiry, stage, lost_reasons=None, detail=None, competitor_name=None, competitor_price=None):
	"""SCR-CRM-05: mark an inquiry No Bid or Cancelled."""
	if stage not in MANUAL:
		frappe.throw(_("Only No Bid or Cancelled can be set by hand."))
	doc = frappe.get_doc("Opportunity", inquiry)
	doc.check_permission("write")
	if doc.pvfss_stage in (WON, LOST):
		frappe.throw(_("Inquiry {0} is already {1}.").format(doc.name, _(doc.pvfss_stage)))

	if isinstance(lost_reasons, str):
		lost_reasons = frappe.parse_json(lost_reasons) if lost_reasons.startswith("[") else [lost_reasons]
	doc.set("lost_reasons", [{"lost_reason": r} for r in (lost_reasons or [])])
	doc.order_lost_reason = detail
	doc.pvfss_competitor_name = competitor_name
	doc.pvfss_competitor_price = flt(competitor_price)
	doc.pvfss_stage = stage
	doc.status = "Closed"
	doc.flags.pvfss_stage_change = True
	doc.save()
	close_open_todos(doc)
	return doc.pvfss_stage


def close_open_todos(doc):
	for todo in frappe.get_all(
		"ToDo",
		filters={"reference_type": doc.doctype, "reference_name": doc.name, "status": "Open"},
		pluck="name",
	):
		frappe.db.set_value("ToDo", todo, "status", "Closed")


def due_alert_days():
	return settings.get_int("inquiry_due_alert_days", 2)
