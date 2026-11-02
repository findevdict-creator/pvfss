"""HSE KPI Summary (HSE-41): leading and lagging KPIs for a period, with LTIFR."""

import frappe
from frappe import _
from frappe.utils import add_months, nowdate

from pvfss.pvfss_hse import kpi

LABELS = (
	("trainings_completed", "Trainings completed", "Leading"),
	("inspections_done", "Site inspections done", "Leading"),
	("audits_done", "Audits and inspections done", "Leading"),
	("near_misses", "Near misses reported", "Leading"),
	("capa_closure_rate", "CAPA closure rate %", "Leading"),
	("lti_count", "Lost time injuries", "Lagging"),
	("lost_days", "Lost days", "Lagging"),
	("hours_worked", "Hours worked", "Lagging"),
	("ltifr", "LTIFR (per 1,000,000 hours)", "Lagging"),
	("incidents_total", "Incidents", "Lagging"),
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	values = kpi.kpis(filters.from_date or add_months(nowdate(), -12), filters.to_date or nowdate())
	data = [{"kpi": _(label), "kind": _(kind), "value": values[key]} for key, label, kind in LABELS]
	data += [
		{"kpi": _("Incidents: {0}").format(_(t)), "kind": _("Lagging"), "value": n}
		for t, n in sorted(values["incidents_by_type"].items())
	]
	columns = [
		{"fieldname": "kind", "label": _("Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "kpi", "label": _("KPI"), "fieldtype": "Data", "width": 260},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Float", "width": 120},
	]
	chart = {
		"data": {
			"labels": [_(t) for t in values["incidents_by_type"]],
			"datasets": [{"name": _("Incidents"), "values": list(values["incidents_by_type"].values())}],
		},
		"type": "bar",
	}
	summary = [
		{
			"label": _("LTIFR"),
			"value": values["ltifr"],
			"datatype": "Float",
			"indicator": "red" if values["ltifr"] else "green",
		},
		{"label": _("CAPA closure %"), "value": values["capa_closure_rate"], "datatype": "Float"},
		{"label": _("Near misses"), "value": values["near_misses"], "datatype": "Int"},
	]
	return columns, data, None, chart, summary
