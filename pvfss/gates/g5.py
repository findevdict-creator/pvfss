"""G5: IRN gate on submit (QA-33, SCR-QA-19). Every failed condition is listed at once."""

import frappe
from frappe import _
from frappe.utils import flt

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality.doctype.itp.itp import DONE, applies_to
from pvfss.utils import mtc_age, settings

QTY_TOLERANCE = 0.001


def accepted_mtc(heat):
	"""(mtc name, review_result) of the best MTC listing the heat: accepted first."""
	rows = frappe.db.sql(
		"""select m.name, m.review_result, m.workflow_state, m.docstatus
		from `tabMTC Heat` mh join `tabMTC` m on m.name = mh.parent
		where mh.heat_number = %s and m.docstatus < 2
		order by field(m.review_result, 'Accepted', 'Accepted with re-test') desc, m.issue_date desc""",
		heat,
		as_dict=True,
	)
	return rows[0] if rows else None


def check(doc):
	from pvfss.overrides.non_conformance import open_ncrs

	result = GateResult(_("IRN cannot be issued"), doc=doc, gate="G5")
	heats = sorted({r.heat_number for r in doc.lines if r.heat_number})
	lines = {r.line_ref for r in doc.lines}

	# (a) ITP points applicable to the released lines are Closed or Waived
	for itp in frappe.get_all("ITP", filters={"supplier_po": doc.supplier_po, "docstatus": 1}, pluck="name"):
		itp_doc = frappe.get_doc("ITP", itp)
		for point in itp_doc.points:
			if any(applies_to(point, line, itp_doc.applies_to_lines) for line in lines):
				result.check(
					point.status in DONE,
					_("{0} point {1} ({2}) is {3}.").format(itp, point.seq, point.activity, _(point.status)),
					doctype="ITP",
					name=itp,
					rule="QA-33 a",
				)

	# (b) no open NCR on the released heats
	for heat, ncrs in open_ncrs(heats).items():
		for ncr in ncrs:
			result.fail(
				_("{0} ({1}) on heat {2} is still open.").format(ncr.name, ncr.pvfss_severity, heat),
				doctype="Non Conformance",
				name=ncr.name,
				rule="QA-33 b",
			)

	# (c) accepted MTC, (d) MTC age, and TRC-04 heat status
	project = doc.project
	recheck = (
		settings.get_flag("recheck_mtc_age_at_irn")
		or settings.get_value("mtc_age_reference_date") == "IRN date"
	)
	for row in doc.lines:
		if not row.heat_number:
			continue
		status = frappe.db.get_value("Heat Number", row.heat_number, "status")
		result.check(
			status not in ("On hold", "Rejected"),
			_("Heat {0} is {1}.").format(row.heat_number, _(status or "")),
			doctype="Heat Number",
			name=row.heat_number,
			rule="TRC-04",
		)
		mtc = accepted_mtc(row.heat_number)
		ok = bool(mtc and mtc.review_result in ("Accepted", "Accepted with re-test"))
		detail = f"{mtc.name} {mtc.review_result or mtc.workflow_state or _('Draft')}" if mtc else _("no MTC")
		result.check(
			ok,
			_("Heat {0} has no accepted MTC ({1}).").format(row.heat_number, detail),
			doctype="MTC" if mtc else "Heat Number",
			name=mtc.name if mtc else row.heat_number,
			rule="QA-33 c",
		)
		if ok and recheck and mtc.review_result == "Accepted":
			age = mtc_age.check(mtc.name, row.heat_number, row.item_code, doc.issue_date, project=project)
			result.check(
				not age["over"],
				(age["message"] or "") + " " + _("(reference IRN date)"),
				doctype="MTC",
				name=mtc.name,
				rule="QA-33 d",
			)

	# (e) released qty per PO line within PO qty - already released
	per_line = {}
	for row in doc.lines:
		per_line.setdefault(row.line_ref, [0.0, row])[0] += flt(row.qty_released)
	for line_ref, (qty, row) in per_line.items():
		result.check(
			qty <= flt(row.po_qty) - flt(row.previously_released) + QTY_TOLERANCE,
			_("Line {0}: releasing {1:g}, remaining {2:g}.").format(
				line_ref, qty, flt(row.po_qty) - flt(row.previously_released)
			),
			rule="QA-33 e",
		)
	return result
