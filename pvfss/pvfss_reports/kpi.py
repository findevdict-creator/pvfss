"""Workspace number cards and charts (RPT-01 to RPT-08, screens §19).

Every card and chart is one function here, keyed by name. The standard Number Cards
(type Custom) call ``card`` and the Dashboard Charts (source "PVFSS Chart") call ``chart``
with the key in their filters, so each figure is computed in one place and tested.
Amounts are in company currency (AED).
"""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	flt,
	get_first_day,
	get_first_day_of_week,
	get_last_day,
	getdate,
	nowdate,
)

from pvfss.pvfss_crm import inquiry as stages


# ----------------------------------------------------------------------------- helpers
def today():
	return getdate(nowdate())


def year_start():
	return today().replace(month=1, day=1)


def month_start():
	return get_first_day(today())


def _sum(doctype, field, filters):
	return sum(flt(v) for v in frappe.get_all(doctype, filters=filters, pluck=field))


def _base_outstanding(doctype, filters):
	"""Outstanding in company currency (outstanding_amount is in the invoice currency)."""
	rows = frappe.get_all(doctype, filters=filters, fields=["outstanding_amount", "conversion_rate"])
	return sum(flt(r.outstanding_amount) * flt(r.conversion_rate or 1) for r in rows)


def _count(doctype, filters):
	return frappe.db.count(doctype, filters)


def _route(doctype, **filters):
	return {"route": ["List", doctype], "route_options": filters}


def _report(name, **filters):
	return {"route": ["query-report", name], "route_options": filters}


# ----------------------------------------------------------------------------- management
def pipeline_value():
	"""Open inquiries at their quoted value (RPT-02)."""
	return _sum("Opportunity", "pvfss_quoted_value", {"pvfss_stage": stages.QUOTED})


def win_rate(from_date, to_date=None):
	"""Won / (won + lost) for inquiries first quoted in the period, %."""
	rows = frappe.get_all(
		"Opportunity",
		filters={
			"pvfss_stage": ["in", (stages.WON, stages.LOST)],
			"pvfss_quoted_on": ["between", [from_date, to_date or today()]],
		},
		pluck="pvfss_stage",
	)
	return flt(rows.count(stages.WON) * 100 / len(rows), 1) if rows else 0


def revenue(from_date, to_date=None):
	return _sum(
		"Sales Invoice",
		"base_net_total",
		{"docstatus": 1, "posting_date": ["between", [from_date, to_date or today()]]},
	)


def gross_margin_pct():
	"""Invoiced margin over open and completed projects (Project Cost Sheet, RPT-02)."""
	from pvfss.pvfss_purchasing.report.project_cost_sheet.project_cost_sheet import build

	income = cost = 0.0
	for project in frappe.get_all("Project", filters={"status": ["!=", "Cancelled"]}, pluck="name"):
		f = build(project)
		income += f["invoiced"]
		cost += f["actual_cost"] if f["invoiced"] else 0
	return flt((income - cost) * 100 / income, 1) if income else 0


def cash_position():
	"""Bank balances in company currency (RPT-02)."""
	accounts = frappe.get_all("Account", filters={"account_type": "Bank", "is_group": 0}, pluck="name")
	if not accounts:
		return 0
	rows = frappe.get_all(
		"GL Entry", filters={"account": ["in", accounts], "is_cancelled": 0}, fields=["debit", "credit"]
	)
	return sum(flt(r.debit) - flt(r.credit) for r in rows)


def overdue_receivables():
	return _base_outstanding(
		"Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", today()]}
	)


def receivables_outstanding():
	return _base_outstanding("Sales Invoice", {"docstatus": 1, "outstanding_amount": [">", 0]})


def projects_at_risk():
	return _count("Project", {"status": "Open", "pvfss_delivery_at_risk": 1})


def icv_score():
	"""Active certificate score, else the latest period estimate."""
	from pvfss.pvfss_icv.icv import current_score

	return current_score()


def icv_days_left():
	from pvfss.pvfss_icv.icv import active_certificate

	cert = active_certificate()
	return (getdate(cert.expiry_date) - today()).days if cert and cert.expiry_date else 0


# ----------------------------------------------------------------------------- pre-bidding
OPEN_STAGES = ["in", stages.PROGRESS]


def open_inquiries():
	return _count("Opportunity", {"pvfss_stage": OPEN_STAGES})


def inquiries_due_this_week():
	start = get_first_day_of_week(today())
	return _count(
		"Opportunity",
		{
			"pvfss_stage": OPEN_STAGES,
			"pvfss_bid_due_date": ["between", [f"{start} 00:00:00", f"{add_days(start, 6)} 23:59:59"]],
		},
	)


def quoted_this_month():
	return _count("Quotation", {"docstatus": 1, "transaction_date": [">=", month_start()]})


def avg_turnaround_days():
	"""Average days received → first quoted, inquiries quoted in the last 90 days (CRM-13)."""
	rows = frappe.get_all(
		"Opportunity",
		filters={"pvfss_quoted_on": [">=", add_days(today(), -90)], "pvfss_turnaround_days": ["is", "set"]},
		pluck="pvfss_turnaround_days",
	)
	return flt(sum(rows) / len(rows), 1) if rows else 0


# ----------------------------------------------------------------------------- post-bidding
def deliveries_due_30():
	"""Customer PO lines with an open quantity due in the next 30 days."""
	return frappe.db.sql(
		"""select count(distinct soi.parent) from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		where so.docstatus = 1 and so.status not in ('Completed', 'Closed')
		and soi.delivered_qty < soi.qty and soi.delivery_date between %s and %s""",
		(today(), add_days(today(), 30)),
	)[0][0]


def delayed_pos():
	"""Supplier POs whose expediting forecast is later than the committed date."""
	return frappe.db.sql(
		"""select count(distinct e.purchase_order) from `tabExpediting Milestone` m
		join `tabExpediting Log` e on e.name = m.parent
		where e.status != 'Complete' and m.actual_date is null
		and m.forecast_date > m.committed_date"""
	)[0][0]


def open_handovers():
	return _count("Project Handover", {"docstatus": 0})


def open_project_changes():
	return _count("Project Change", {"docstatus": 0})


def pos_awaiting_approval():
	return _count("Purchase Order", {"docstatus": 0, "workflow_state": ["like", "%Approval%"]})


# ----------------------------------------------------------------------------- quality
def rfis_this_week():
	start = get_first_day_of_week(today())
	return _count(
		"RFI",
		{
			"status": ["in", ("Raised", "Scheduled", "Rescheduled")],
			"scheduled_date": ["between", [start, add_days(start, 6)]],
		},
	)


def rfis_overdue():
	return _count(
		"RFI", {"status": ["in", ("Raised", "Scheduled", "Rescheduled")], "scheduled_date": ["<", today()]}
	)


def open_ncrs():
	return _count("Non Conformance", {"status": "Open"})


def irns_this_month():
	return _count("IRN", {"docstatus": 1, "issue_date": [">=", month_start()]})


def mtcs_pending_review():
	return _count("MTC", {"docstatus": 0})


def mtcs_near_age_limit():
	"""Heats in stock whose MTC reaches its age limit within the alert window (SMR-21)."""
	from pvfss.utils import mtc_age, settings

	window = add_days(today(), settings.get_int("mtc_age_alert_days", 60))
	count = 0
	for row in frappe.db.sql(
		"""select m.issue_date, m.supplier_po, coalesce(mh.item_code, h.item_code) as item_code
		from `tabMTC Heat` mh
		join `tabMTC` m on m.name = mh.parent
		join `tabHeat Number` h on h.name = mh.heat_number
		where m.docstatus = 1 and h.balance_qty > 0""",
		as_dict=True,
	):
		project = row.supplier_po and frappe.db.get_value("Purchase Order", row.supplier_po, "project")
		rule = mtc_age.find_rule(row.item_code, project)
		if rule and rule["months"] and add_months(getdate(row.issue_date), rule["months"]) <= window:
			count += 1
	return count


# ----------------------------------------------------------------------------- logistics
def ready_to_dispatch():
	"""IRN-released quantity not yet on a submitted Delivery Note."""
	released = flt(
		frappe.db.sql(
			"select sum(l.qty_released) from `tabIRN Line` l join `tabIRN` i on i.name = l.parent where i.docstatus = 1"
		)[0][0]
	)
	shipped = flt(
		frappe.db.sql(
			"""select sum(d.qty) from `tabDelivery Note Item` d join `tabDelivery Note` n on n.name = d.parent
			where n.docstatus = 1 and ifnull(d.pvfss_irn, '') != ''"""
		)[0][0]
	)
	return max(released - shipped, 0)


def dns_in_transit():
	return _count(
		"Delivery Note", {"docstatus": 1, "pvfss_pod_date": ["is", "not set"], "pvfss_etd": ["is", "set"]}
	)


def eta_this_week():
	start = get_first_day_of_week(today())
	return _count(
		"Delivery Note",
		{
			"docstatus": 1,
			"pvfss_pod_date": ["is", "not set"],
			"pvfss_eta": ["between", [start, add_days(start, 6)]],
		},
	)


def pod_missing():
	return _count(
		"Delivery Note", {"docstatus": 1, "pvfss_pod_date": ["is", "not set"], "pvfss_eta": ["<", today()]}
	)


# ----------------------------------------------------------------------------- finance
def payables_due_30():
	return _base_outstanding(
		"Purchase Invoice",
		{"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<=", add_days(today(), 30)]},
	)


def retention_due_90():
	return _sum(
		"Retention",
		"base_amount",
		{"direction": "Receivable", "status": "Held", "release_due_date": ["<=", add_days(today(), 90)]},
	)


def lcs_expiring_30():
	return _count(
		"Letter of Credit",
		{
			"docstatus": 1,
			"status": ["not in", ("Paid", "Expired", "Closed")],
			"expiry_date": ["between", [today(), add_days(today(), 30)]],
		},
	)


def pdcs_maturing_14():
	return _count(
		"Post-Dated Cheque",
		{
			"docstatus": 1,
			"status": ["in", ("In hand", "Deposited")],
			"cheque_date": ["between", [today(), add_days(today(), 14)]],
		},
	)


def vat_payable():
	"""Output VAT less input VAT for the current calendar quarter (FIN-55)."""
	start = today().replace(month=((today().month - 1) // 3) * 3 + 1, day=1)
	end = get_last_day(add_months(start, 2))
	period = ["between", [start, end]]
	output = _sum("Sales Invoice", "base_total_taxes_and_charges", {"docstatus": 1, "posting_date": period})
	inputs = _sum(
		"Purchase Invoice", "base_total_taxes_and_charges", {"docstatus": 1, "posting_date": period}
	)
	return output - inputs


# ----------------------------------------------------------------------------- HSE / ICV / DMS
def _hse(key):
	from pvfss.pvfss_hse.kpi import kpis

	return kpis(year_start(), today())[key]


def supplier_uae_share():
	from pvfss.pvfss_icv.icv import supplier_spend

	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	rows = supplier_spend(year_start(), today(), company)
	total = sum(r["spend"] for r in rows)
	uae = sum(r["spend"] for r in rows if r["uae_based"])
	return flt(uae * 100 / total, 1) if total else 0


def emirati_headcount():
	return _count("Employee", {"status": "Active", "pvfss_nationality_uae": 1})


def awaiting_customer_response():
	return frappe.db.sql(
		"""select count(distinct parent) from `tabProject Document Submittal`
		where parenttype = 'Project Document' and response = 'Pending'"""
	)[0][0]


def overdue_submittals():
	from pvfss.utils import settings

	limit = settings.get_int("submittal_overdue_days", 14)
	return frappe.db.sql(
		"""select count(distinct parent) from `tabProject Document Submittal`
		where parenttype = 'Project Document' and response = 'Pending' and submitted_date < %s""",
		add_days(today(), -limit),
	)[0][0]


def checked_out_by_me():
	return _count("Project Document", {"locked_by": frappe.session.user})


# ----------------------------------------------------------------------------- card registry
# key: (label, value function, fieldtype, click target). Labels are translated where shown.
CARDS = {
	# Management (SCR-RPT-01)
	"pipeline_value": (
		"Pipeline value",
		pipeline_value,
		"Currency",
		_route("Opportunity", pvfss_stage="Quoted"),
	),
	"win_rate_90": (
		"Win rate 90 days",
		lambda: win_rate(add_days(today(), -90)),
		"Percent",
		_report("Win Loss Analysis"),
	),
	"win_rate_ytd": ("Win rate YTD", lambda: win_rate(year_start()), "Percent", _report("Win Loss Analysis")),
	"revenue_mtd": (
		"Revenue MTD",
		lambda: revenue(month_start()),
		"Currency",
		_route("Sales Invoice", docstatus=1),
	),
	"revenue_ytd": (
		"Revenue YTD",
		lambda: revenue(year_start()),
		"Currency",
		_route("Sales Invoice", docstatus=1),
	),
	"gross_margin_pct": ("Gross margin %", gross_margin_pct, "Percent", _report("Project Cost Sheet")),
	"cash_position": ("Cash position", cash_position, "Currency", _route("Payment Entry", docstatus=1)),
	"overdue_receivables": (
		"Overdue receivables",
		overdue_receivables,
		"Currency",
		_route("Sales Invoice", status="Overdue"),
	),
	"projects_at_risk": (
		"Projects at risk",
		projects_at_risk,
		"Int",
		_route("Project", pvfss_delivery_at_risk=1),
	),
	"icv_score": ("ICV score", icv_score, "Percent", _route("ICV Certificate", status="Active")),
	"icv_days_left": (
		"ICV certificate days left",
		icv_days_left,
		"Int",
		_route("ICV Certificate", status="Active"),
	),
	# Pre-Bidding (SCR-RPT-02)
	"open_inquiries": ("Open inquiries", open_inquiries, "Int", _route("Opportunity")),
	"inquiries_due_this_week": (
		"Inquiries due this week",
		inquiries_due_this_week,
		"Int",
		_report("Inquiry Register"),
	),
	"quoted_this_month": ("Quoted this month", quoted_this_month, "Int", _route("Quotation", docstatus=1)),
	"avg_turnaround_days": (
		"Avg quotation turnaround (days)",
		avg_turnaround_days,
		"Float",
		_report("Win Loss Analysis"),
	),
	# Post-Bidding (SCR-RPT-03)
	"deliveries_due_30": (
		"Deliveries due in 30 days",
		deliveries_due_30,
		"Int",
		_route("Sales Order", docstatus=1),
	),
	"delayed_pos": ("Delayed POs", delayed_pos, "Int", _route("Expediting Log", status="Late")),
	"open_handovers": ("Open handovers", open_handovers, "Int", _route("Project Handover", docstatus=0)),
	"open_project_changes": (
		"Open project changes",
		open_project_changes,
		"Int",
		_route("Project Change", docstatus=0),
	),
	"pos_awaiting_approval": (
		"POs awaiting approval",
		pos_awaiting_approval,
		"Int",
		_route("Purchase Order", docstatus=0),
	),
	# Quality (SCR-RPT-04)
	"rfis_this_week": ("RFIs this week", rfis_this_week, "Int", _route("RFI")),
	"rfis_overdue": ("Overdue RFIs", rfis_overdue, "Int", _route("RFI")),
	"open_ncrs": ("Open NCRs", open_ncrs, "Int", _route("Non Conformance", status="Open")),
	"irns_this_month": ("IRNs issued this month", irns_this_month, "Int", _route("IRN", docstatus=1)),
	"mtcs_near_age_limit": (
		"MTCs approaching age limit",
		mtcs_near_age_limit,
		"Int",
		_report("Heat Number Register"),
	),
	"mtcs_pending_review": ("MTCs pending review", mtcs_pending_review, "Int", _route("MTC", docstatus=0)),
	# Logistics (SCR-RPT-05)
	"ready_to_dispatch": (
		"Ready to dispatch (qty)",
		ready_to_dispatch,
		"Float",
		_report("Inspection Release Tracker"),
	),
	"dns_in_transit": ("DNs in transit", dns_in_transit, "Int", _route("Delivery Note", docstatus=1)),
	"eta_this_week": ("ETA this week", eta_this_week, "Int", _route("Delivery Note", docstatus=1)),
	"pod_missing": ("POD missing", pod_missing, "Int", _route("Delivery Note", docstatus=1)),
	# Finance (SCR-RPT-06)
	"receivables_outstanding": (
		"Receivables outstanding",
		receivables_outstanding,
		"Currency",
		_route("Sales Invoice", docstatus=1),
	),
	"payables_due_30": (
		"Payables due in 30 days",
		payables_due_30,
		"Currency",
		_route("Purchase Invoice", docstatus=1),
	),
	"retention_due_90": (
		"Retention due in 90 days",
		retention_due_90,
		"Currency",
		_report("Retention Register"),
	),
	"lcs_expiring_30": (
		"LCs expiring in 30 days",
		lcs_expiring_30,
		"Int",
		_route("Letter of Credit", docstatus=1),
	),
	"pdcs_maturing_14": (
		"PDCs maturing in 14 days",
		pdcs_maturing_14,
		"Int",
		_report("PDC Maturity Register"),
	),
	"vat_payable": (
		"VAT payable this quarter",
		vat_payable,
		"Currency",
		_route("Sales Invoice", docstatus=1),
	),
	# HSE (SCR-RPT-07), year to date
	"hse_trainings": (
		"Trainings completed YTD",
		lambda: _hse("trainings_completed"),
		"Int",
		_route("HSE Training Record"),
	),
	"hse_inspections": ("Inspections done YTD", lambda: _hse("inspections_done"), "Int", _route("HSE Audit")),
	"hse_near_misses": (
		"Near misses YTD",
		lambda: _hse("near_misses"),
		"Int",
		_route("HSE Incident", incident_type="Near miss"),
	),
	"hse_capa_closure": ("CAPA closure rate", lambda: _hse("capa_closure_rate"), "Percent", _route("CAPA")),
	"hse_lti": ("LTIs YTD", lambda: _hse("lti_count"), "Int", _route("HSE Incident", is_lti=1)),
	"hse_ltifr": ("LTIFR YTD", lambda: _hse("ltifr"), "Float", _report("HSE KPI Summary")),
	# ICV (SCR-RPT-09)
	"icv_uae_supplier_share": (
		"UAE supplier spend YTD",
		supplier_uae_share,
		"Percent",
		_route("ICV Period Data"),
	),
	"icv_emirati_headcount": (
		"Emirati headcount",
		emirati_headcount,
		"Int",
		_route("Employee", pvfss_nationality_uae=1),
	),
	# Documents (SCR-RPT-10)
	"dms_awaiting_response": (
		"Awaiting customer response",
		awaiting_customer_response,
		"Int",
		_report("Submittal Register", response="Pending"),
	),
	"dms_overdue_submittals": (
		"Overdue submittals",
		overdue_submittals,
		"Int",
		_report("Submittal Register", overdue_only=1),
	),
	"dms_checked_out_by_me": ("Checked out by me", checked_out_by_me, "Int", _route("Project Document")),
}


@frappe.whitelist()
def card(filters: str | dict | None = None):
	"""Number Card (type Custom) method: ``filters`` holds ``{"card": key}``."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	key = filters.get("card") if isinstance(filters, dict) else None
	if key not in CARDS:
		frappe.throw(_("Unknown card {0}").format(key))
	_label, fn, fieldtype, target = CARDS[key]
	if not can_open(target["route"]):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return {"value": fn(), "fieldtype": fieldtype, **target}


def can_open(route):
	"""A figure is shown only to users who may open the list or report it links to."""
	kind, name = route[0], route[1]
	if kind == "List":
		return bool(frappe.has_permission(name, "read"))
	if kind == "query-report":
		return frappe.get_cached_doc("Report", name).is_permitted()
	return False
