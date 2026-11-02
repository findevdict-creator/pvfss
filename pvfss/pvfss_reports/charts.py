"""Workspace charts (screens §19). One Dashboard Chart Source, "PVFSS Chart", serves all of them.

Each Dashboard Chart record passes ``{"chart": key}`` in its filters; ``get`` returns the
frappe-charts data for that key.
"""

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	date_diff,
	flt,
	formatdate,
	get_first_day,
	get_first_day_of_week,
	getdate,
)

from pvfss.pvfss_crm import inquiry as stages
from pvfss.pvfss_reports.kpi import today


def _data(labels, *datasets):
	return {"labels": labels, "datasets": [{"name": name, "values": values} for name, values in datasets]}


def _weeks(n, start=None):
	start = get_first_day_of_week(start or today())
	return [add_days(start, 7 * i) for i in range(n)]


def _week_index(weeks, date):
	if not date:
		return None
	date = getdate(date)
	for i, start in enumerate(weeks):
		if start <= date < add_days(start, 7):
			return i
	return None


def _months(n):
	first = get_first_day(today())
	return [add_months(first, -i) for i in reversed(range(n))]


def _by_week(weeks, dates_amounts):
	values = [0.0] * len(weeks)
	for date, amount in dates_amounts:
		i = _week_index(weeks, date)
		if i is not None:
			values[i] += flt(amount)
	return values


def _week_labels(weeks):
	return [formatdate(w, "dd MMM") for w in weeks]


def _group(doctype, field, filters):
	counts = OrderedDict()
	for value in frappe.get_all(doctype, filters=filters, pluck=field, order_by=f"{field} asc"):
		counts[value] = counts.get(value, 0) + 1
	return counts


def _top(rows, n=10):
	return sorted(rows.items(), key=lambda kv: kv[1], reverse=True)[:n]


# ----------------------------------------------------------------------------- management
def pipeline_by_stage():
	counts = _group("Opportunity", "pvfss_stage", {"pvfss_stage": ["in", stages.PROGRESS]})
	return _data(
		[_(s) for s in stages.PROGRESS], (_("Inquiries"), [counts.get(s, 0) for s in stages.PROGRESS])
	)


def revenue_by_month():
	months = _months(12)
	this_year, last_year = [], []
	for m in months:
		this_year.append(_revenue(m))
		last_year.append(_revenue(add_months(m, -12)))
	return _data(
		[formatdate(m, "MMM yy") for m in months], (_("Revenue"), this_year), (_("Previous year"), last_year)
	)


def _revenue(month):
	from pvfss.pvfss_reports.kpi import revenue

	return revenue(month, add_days(add_months(month, 1), -1))


def overdue_by_customer():
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1, "outstanding_amount": [">", 0], "due_date": ["<", today()]},
		fields=["customer", "outstanding_amount", "conversion_rate"],
	)
	totals = {}
	for r in rows:
		totals[r.customer] = totals.get(r.customer, 0) + flt(r.outstanding_amount) * flt(
			r.conversion_rate or 1
		)
	top = _top(totals)
	return _data([k for k, _v in top], (_("Overdue"), [v for _k, v in top]))


def cash_flow_13w():
	from pvfss.pvfss_finance.report.cash_flow_forecast.cash_flow_forecast import execute

	chart = execute({"weeks": 13})[3]
	return chart["data"]


# ----------------------------------------------------------------------------- pre-bidding
def inquiries_due_by_week():
	weeks = _weeks(8)
	rows = frappe.get_all(
		"Opportunity",
		filters={"pvfss_stage": ["in", stages.PROGRESS], "pvfss_bid_due_date": ["is", "set"]},
		pluck="pvfss_bid_due_date",
	)
	return _data(_week_labels(weeks), (_("Due"), _by_week(weeks, [(d, 1) for d in rows])))


def win_loss_by_contractor():
	rows = frappe.get_all(
		"Opportunity",
		filters={
			"pvfss_stage": ["in", (stages.WON, stages.LOST)],
			"pvfss_quoted_on": [">=", add_days(today(), -365)],
		},
		fields=["party_name", "pvfss_stage"],
	)
	won, lost = {}, {}
	for r in rows:
		target = won if r.pvfss_stage == stages.WON else lost
		target[r.party_name] = target.get(r.party_name, 0) + 1
	names = [k for k, _v in _top({k: won.get(k, 0) + lost.get(k, 0) for k in set(won) | set(lost)})]
	return _data(
		names, (_("Won"), [won.get(n, 0) for n in names]), (_("Lost"), [lost.get(n, 0) for n in names])
	)


def inquiries_per_owner():
	counts = _group("Opportunity", "pvfss_owner", {"pvfss_stage": ["in", stages.PROGRESS]})
	top = _top({(k or _("Unassigned")): v for k, v in counts.items()})
	return _data([k for k, _v in top], (_("Open inquiries"), [v for _k, v in top]))


# ----------------------------------------------------------------------------- post-bidding
def deliveries_due_by_week():
	weeks = _weeks(8)
	rows = frappe.db.sql(
		"""select soi.delivery_date, (soi.qty - soi.delivered_qty) * soi.base_net_rate
		from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
		where so.docstatus = 1 and so.status not in ('Completed', 'Closed') and soi.delivered_qty < soi.qty""",
	)
	return _data(_week_labels(weeks), (_("Value due"), _by_week(weeks, rows)))


def po_status():
	rows = frappe.get_all(
		"Purchase Order",
		filters={"docstatus": ["<", 2], "status": ["not in", ("Completed", "Closed")]},
		fields=["workflow_state", "status", "docstatus"],
	)
	counts = OrderedDict()
	for r in rows:
		key = r.workflow_state if r.docstatus == 0 else r.status
		counts[key or _("Draft")] = counts.get(key or _("Draft"), 0) + 1
	return _data([_(k) for k in counts], (_("POs"), list(counts.values())))


def late_milestones_by_supplier():
	rows = frappe.db.sql(
		"""select e.supplier, count(*) from `tabExpediting Milestone` m
		join `tabExpediting Log` e on e.name = m.parent
		where m.actual_date is null and (m.status = 'Late' or m.forecast_date > m.committed_date)
		group by e.supplier"""
	)
	top = _top(dict(rows))
	return _data([k for k, _v in top], (_("Late milestones"), [v for _k, v in top]))


# ----------------------------------------------------------------------------- quality
AGE_BANDS = ((0, 7, "0-7 d"), (8, 30, "8-30 d"), (31, 90, "31-90 d"), (91, 100000, "> 90 d"))


def ncrs_by_severity_age():
	rows = frappe.get_all(
		"Non Conformance",
		filters={"status": "Open"},
		fields=["pvfss_severity", "pvfss_raised_on", "creation"],
	)
	severities = ("Critical", "Major", "Minor")
	values = {s: [0] * len(AGE_BANDS) for s in severities}
	for r in rows:
		age = date_diff(today(), r.pvfss_raised_on or r.creation)
		for i, (low, high, _label) in enumerate(AGE_BANDS):
			if low <= age <= high:
				values.setdefault(r.pvfss_severity or "Minor", [0] * len(AGE_BANDS))[i] += 1
	return _data([b[2] for b in AGE_BANDS], *[(_(s), values[s]) for s in severities])


def rfis_by_status_month():
	counts = _group("RFI", "status", {"creation": [">=", get_first_day(today())]})
	return _data([_(k) for k in counts], (_("RFIs"), list(counts.values())))


def irn_qty_by_month():
	months = _months(6)
	values = []
	for m in months:
		values.append(
			flt(
				frappe.db.sql(
					"""select sum(l.qty_released) from `tabIRN Line` l join `tabIRN` i on i.name = l.parent
				where i.docstatus = 1 and i.issue_date between %s and %s""",
					(m, add_days(add_months(m, 1), -1)),
				)[0][0]
			)
		)
	return _data([formatdate(m, "MMM yy") for m in months], (_("Qty released"), values))


# ----------------------------------------------------------------------------- logistics
def dispatches_per_week():
	weeks = _weeks(8, add_days(today(), -49))
	rows = frappe.get_all(
		"Delivery Note", filters={"docstatus": 1, "posting_date": [">=", weeks[0]]}, pluck="posting_date"
	)
	return _data(_week_labels(weeks), (_("Delivery Notes"), _by_week(weeks, [(d, 1) for d in rows])))


def dns_by_mode():
	counts = _group(
		"Delivery Note",
		"pvfss_transport_mode",
		{"docstatus": 1, "posting_date": [">=", add_days(today(), -90)]},
	)
	return _data([_(k) if k else _("Not set") for k in counts], (_("Delivery Notes"), list(counts.values())))


# ----------------------------------------------------------------------------- finance
AGEING = ((None, 0, "Not due"), (1, 30, "1-30"), (31, 60, "31-60"), (61, 90, "61-90"), (91, None, "> 90"))


def receivables_ageing():
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1, "outstanding_amount": [">", 0]},
		fields=["due_date", "outstanding_amount", "conversion_rate"],
	)
	values = [0.0] * len(AGEING)
	for r in rows:
		days = date_diff(today(), r.due_date)
		for i, (low, high, _label) in enumerate(AGEING):
			if (low is None or days >= low) and (high is None or days <= high):
				values[i] += flt(r.outstanding_amount) * flt(r.conversion_rate or 1)
				break
	return _data([_(a[2]) for a in AGEING], (_("Outstanding"), values))


def payables_due_by_week():
	weeks = _weeks(8)
	rows = frappe.db.sql(
		"""select ifnull(ps.due_date, pi.due_date), ifnull(ps.outstanding, pi.outstanding_amount) * pi.conversion_rate
		from `tabPurchase Invoice` pi left join `tabPayment Schedule` ps on ps.parent = pi.name and ps.parenttype = 'Purchase Invoice'
		where pi.docstatus = 1 and pi.outstanding_amount > 0"""
	)
	return _data(_week_labels(weeks), (_("Payables due"), _by_week(weeks, rows)))


# ----------------------------------------------------------------------------- HSE
def incidents_by_type_month():
	months = _months(12)
	types = ("Injury", "Near miss", "Property damage", "Environmental", "Dangerous occurrence")
	values = {t: [0] * len(months) for t in types}
	rows = frappe.get_all(
		"HSE Incident",
		filters={"incident_datetime": [">=", months[0]]},
		fields=["incident_type", "incident_datetime"],
	)
	for r in rows:
		first = get_first_day(getdate(r.incident_datetime))
		if first in months and r.incident_type in values:
			values[r.incident_type][months.index(first)] += 1
	return _data([formatdate(m, "MMM yy") for m in months], *[(_(t), values[t]) for t in types])


def ltifr_12m():
	from pvfss.pvfss_hse.kpi import kpis

	months = _months(12)
	values = [kpis(add_months(m, -11), add_days(add_months(m, 1), -1))["ltifr"] for m in months]
	return _data([formatdate(m, "MMM yy") for m in months], (_("LTIFR rolling 12 months"), values))


def risks_by_rating():
	rows = frappe.get_all("HSE Risk Register", fields=["residual_rating", "rating"])
	order = ("Extreme", "High", "Medium", "Low")
	counts = dict.fromkeys(order, 0)
	for r in rows:
		key = r.residual_rating or r.rating
		if key in counts:
			counts[key] += 1
	return _data([_(k) for k in order], (_("Risks"), [counts[k] for k in order]))


# ----------------------------------------------------------------------------- supplier
def on_time_by_supplier():
	from pvfss.pvfss_reports.report.supplier_performance.supplier_performance import get_rows

	rows = sorted(get_rows({}), key=lambda r: r["pos"], reverse=True)[:10]
	return _data([r["supplier"] for r in rows], (_("On-time %"), [r["on_time_pct"] for r in rows]))


def ncr_rate_by_supplier():
	from pvfss.pvfss_reports.report.supplier_performance.supplier_performance import get_rows

	rows = sorted(get_rows({}), key=lambda r: r["pos"], reverse=True)[:10]
	return _data([r["supplier"] for r in rows], (_("NCRs per PO"), [r["ncr_rate"] for r in rows]))


# The DocType a user must be able to read to see each chart
CHART_DOCTYPES = {
	"pipeline_by_stage": "Opportunity",
	"revenue_by_month": "Sales Invoice",
	"overdue_by_customer": "Sales Invoice",
	"cash_flow_13w": "Payment Entry",
	"inquiries_due_by_week": "Opportunity",
	"win_loss_by_contractor": "Opportunity",
	"inquiries_per_owner": "Opportunity",
	"deliveries_due_by_week": "Sales Order",
	"po_status": "Purchase Order",
	"late_milestones_by_supplier": "Expediting Log",
	"ncrs_by_severity_age": "Non Conformance",
	"rfis_by_status_month": "RFI",
	"irn_qty_by_month": "IRN",
	"dispatches_per_week": "Delivery Note",
	"dns_by_mode": "Delivery Note",
	"receivables_ageing": "Sales Invoice",
	"payables_due_by_week": "Purchase Invoice",
	"incidents_by_type_month": "HSE Incident",
	"ltifr_12m": "HSE Incident",
	"risks_by_rating": "HSE Risk Register",
	"on_time_by_supplier": "Purchase Order",
	"ncr_rate_by_supplier": "Purchase Order",
}

CHARTS = {
	"pipeline_by_stage": pipeline_by_stage,
	"revenue_by_month": revenue_by_month,
	"overdue_by_customer": overdue_by_customer,
	"cash_flow_13w": cash_flow_13w,
	"inquiries_due_by_week": inquiries_due_by_week,
	"win_loss_by_contractor": win_loss_by_contractor,
	"inquiries_per_owner": inquiries_per_owner,
	"deliveries_due_by_week": deliveries_due_by_week,
	"po_status": po_status,
	"late_milestones_by_supplier": late_milestones_by_supplier,
	"ncrs_by_severity_age": ncrs_by_severity_age,
	"rfis_by_status_month": rfis_by_status_month,
	"irn_qty_by_month": irn_qty_by_month,
	"dispatches_per_week": dispatches_per_week,
	"dns_by_mode": dns_by_mode,
	"receivables_ageing": receivables_ageing,
	"payables_due_by_week": payables_due_by_week,
	"incidents_by_type_month": incidents_by_type_month,
	"ltifr_12m": ltifr_12m,
	"risks_by_rating": risks_by_rating,
	"on_time_by_supplier": on_time_by_supplier,
	"ncr_rate_by_supplier": ncr_rate_by_supplier,
}


@frappe.whitelist()
def get(
	chart_name: str | None = None,
	filters: str | dict | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	time_interval: str | None = None,
	timespan: str | None = None,
	refresh: str | int | None = None,
	heatmap_year: str | int | None = None,
):
	"""Dashboard Chart Source method for "PVFSS Chart"."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	key = filters.get("chart")
	if key not in CHARTS:
		frappe.throw(_("Unknown chart {0}").format(key))
	frappe.has_permission(CHART_DOCTYPES[key], "read", throw=True)
	return CHARTS[key]()
