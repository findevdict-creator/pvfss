"""Management KPI Summary (RPT-02, RPT-10): the Management number-card figures as one table.

The weekly Auto Email Report "Management weekly" sends this report to the Directors.
"""

import frappe
from frappe import _

from pvfss.pvfss_reports.kpi import CARDS

MANAGEMENT_CARDS = (
	"pipeline_value",
	"win_rate_90",
	"win_rate_ytd",
	"revenue_mtd",
	"revenue_ytd",
	"gross_margin_pct",
	"cash_position",
	"overdue_receivables",
	"projects_at_risk",
	"icv_score",
	"icv_days_left",
)


def execute(filters=None):
	columns = [
		{"fieldname": "figure", "label": _("Figure"), "fieldtype": "Data", "width": 260},
		{"fieldname": "value", "label": _("Value"), "fieldtype": "Data", "width": 180},
	]
	data = []
	for key in MANAGEMENT_CARDS:
		label, fn, fieldtype, _target = CARDS[key]
		value = fn()
		data.append(
			{"figure": _(label), "value": frappe.format(value, {"fieldtype": fieldtype}), "raw": value}
		)
	return columns, data
