"""HSE KPIs (HSE-41): leading and lagging indicators with LTIFR from the monthly hours."""

import frappe
from frappe.utils import add_days, flt, get_first_day, getdate

LTIFR_BASE = 1_000_000


def kpis(from_date, to_date):
	from_date, to_date = getdate(from_date), getdate(to_date)
	period = ["between", [from_date, to_date]]
	incidents = frappe.get_all(
		"HSE Incident",
		filters={"incident_datetime": ["between", [from_date, add_days(to_date, 1)]]},
		fields=["incident_type", "is_lti", "lost_days"],
	)
	by_type = {}
	for row in incidents:
		by_type[row.incident_type] = by_type.get(row.incident_type, 0) + 1
	hours = sum(
		flt(h)
		for h in frappe.get_all(
			"HSE Monthly Statistics", filters={"month": ["between", [get_first_day(from_date), to_date]]}, pluck="hours_worked"
		)
	)
	lti = sum(1 for r in incidents if r.is_lti)
	capas = frappe.get_all("CAPA", filters={"due_date": period}, pluck="status")
	closed = sum(1 for s in capas if s == "Verified-Closed")
	return {
		"from_date": from_date,
		"to_date": to_date,
		"trainings_completed": frappe.db.count("HSE Training Record", {"training_date": period}),
		"inspections_done": frappe.db.count(
			"HSE Audit", {"audit_type": "Site inspection", "status": ["in", ("Done", "Closed")], "actual_date": period}
		),
		"audits_done": frappe.db.count("HSE Audit", {"status": ["in", ("Done", "Closed")], "actual_date": period}),
		"near_misses": by_type.get("Near miss", 0),
		"capa_total": len(capas),
		"capa_closed": closed,
		"capa_closure_rate": flt(closed * 100 / len(capas), 1) if capas else 0,
		"lti_count": lti,
		"lost_days": sum(int(r.lost_days or 0) for r in incidents),
		"hours_worked": hours,
		"ltifr": flt(lti * LTIFR_BASE / hours, 2) if hours else 0,
		"incidents_by_type": by_type,
		"incidents_total": len(incidents),
	}
