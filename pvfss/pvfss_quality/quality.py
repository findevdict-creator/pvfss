"""Quality plug-ins for traceability (TRC-10, TRC-12): inspection, NCR and IRN stages and register columns."""

import frappe
from frappe.utils import flt

from pvfss.gates.g5 import accepted_mtc
from pvfss.overrides.non_conformance import open_ncrs


def trace_nodes(heats, batches):
	nodes = []
	if not heats:
		return nodes
	for row in frappe.db.sql(
		"""select distinct ir.name, ir.result_summary, ir.inspection_date, t.heat_number
		from `tabTest Result` t join `tabInspection Report` ir on ir.name = t.parent
		where t.heat_number in %(h)s and ir.docstatus = 1
		union
		select distinct ir.name, ir.result_summary, ir.inspection_date, m.heat_number
		from `tabRFI Material` m join `tabInspection Report` ir on ir.rfi = m.parent
		where m.heat_number in %(h)s and ir.docstatus = 1""",
		{"h": tuple(heats)},
		as_dict=True,
	):
		nodes.append(
			{
				"stage": "Inspection",
				"doctype": "Inspection Report",
				"name": row.name,
				"status": row.result_summary,
				"facts": {"Date": row.inspection_date},
				"heat": row.heat_number,
			}
		)
	for heat, ncrs in open_ncrs(heats).items():
		for ncr in ncrs:
			nodes.append(
				{
					"stage": "NCR",
					"doctype": "Non Conformance",
					"name": ncr.name,
					"status": ncr.pvfss_severity,
					"facts": {"Severity": ncr.pvfss_severity},
					"heat": heat,
				}
			)
	for row in frappe.db.sql(
		"""select i.name, i.issue_date, l.heat_number, sum(l.qty_released) as qty
		from `tabIRN Line` l join `tabIRN` i on i.name = l.parent
		where l.heat_number in %(h)s and i.docstatus = 1
		group by i.name, l.heat_number""",
		{"h": tuple(heats)},
		as_dict=True,
	):
		nodes.append(
			{
				"stage": "IRN",
				"doctype": "IRN",
				"name": row.name,
				"status": "Issued",
				"facts": {"Date": row.issue_date, "Released": flt(row.qty)},
				"heat": row.heat_number,
			}
		)
	return nodes


def register_columns(heats):
	"""Heat Number Register: MTC status, qty released on IRNs and open NCRs per heat."""
	if not heats:
		return {}
	released = dict(
		frappe.db.sql(
			"""select l.heat_number, sum(l.qty_released) from `tabIRN Line` l
			join `tabIRN` i on i.name = l.parent
			where l.heat_number in %(h)s and i.docstatus = 1 group by l.heat_number""",
			{"h": tuple(heats)},
		)
	)
	ncrs = open_ncrs(heats)
	out = {}
	for heat in heats:
		mtc = accepted_mtc(heat)
		out[heat] = {
			"mtc_status": (mtc.review_result or mtc.workflow_state or "Draft") if mtc else None,
			"qty_released": flt(released.get(heat)),
			"open_ncrs": len({r.name for r in ncrs.get(heat, [])}),
		}
	return out
