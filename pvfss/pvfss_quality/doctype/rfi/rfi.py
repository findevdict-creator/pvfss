# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from pvfss.gates.base import GateResult
from pvfss.pvfss_quality.doctype.itp.itp import DONE, is_hold, point_codes

PARTY_FIELDS = (("PVFSS", "pvfss_point"), ("TPI", "tpi_point"), ("Customer", "customer_point"))


class RFI(Document):
	"""Request for Inspection (QA-10 to QA-12, SCR-QA-08)."""

	def validate(self):
		itp = frappe.get_doc("ITP", self.itp)
		if itp.docstatus != 1:
			frappe.throw(
				_("ITP {0} is not approved. Only approved ITPs can be used on RFIs (QA-04).").format(self.itp)
			)
		if itp.supplier_po != self.supplier_po:
			frappe.throw(_("ITP {0} belongs to {1}.").format(self.itp, itp.supplier_po))
		by_seq = {p.seq: p for p in itp.points}
		parties = set()
		for row in self.points:
			point = by_seq.get(row.seq)
			if not point:
				frappe.throw(_("ITP {0} has no point {1}.").format(self.itp, row.seq))
			if point.status in DONE and self.status in ("Raised", "Scheduled", "Rescheduled"):
				frappe.throw(
					_("Point {0} ({1}) is already {2}.").format(row.seq, point.activity, _(point.status))
				)
			row.activity = point.activity
			row.points = point_codes(point)
			row.is_hold = int(is_hold(point))
			parties.update(party for party, field in PARTY_FIELDS if point.get(field) in ("H", "W"))
		self.parties_required = ", ".join(p for p, _f in PARTY_FIELDS if p in parties)
		self.points_label = ", ".join(f"{r.seq}{' (H)' if r.is_hold else ''}" for r in self.points)
		supplier = frappe.db.get_value("Supplier", self.supplier, "supplier_name") if self.supplier else ""
		self.title = " · ".join(x for x in (supplier, self.points[0].activity if self.points else "") if x)

	def hold_check(self):
		"""QA-12: a Hold point waits for every earlier Hold point (outside this RFI) to close."""
		result = GateResult(_("RFI cannot be scheduled"), doc=self)
		itp = frappe.get_doc("ITP", self.itp)
		covered = {r.seq for r in self.points}
		for row in sorted(self.points, key=lambda r: r.seq):
			if not row.is_hold:
				continue
			for earlier in itp.points:
				if earlier.seq < row.seq and is_hold(earlier) and earlier.seq not in covered:
					result.check(
						earlier.status in DONE,
						_(
							"Hold point {0} ({1}) cannot be scheduled: Hold point {2} ({3}) is still open."
						).format(row.seq, row.activity, earlier.seq, earlier.activity),
						doctype="ITP",
						name=self.itp,
						rule="QA-12",
					)
		return result


def _rfi(name):
	doc = frappe.get_doc("RFI", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def schedule(rfi: str, scheduled_date: str | None = None):
	doc = _rfi(rfi)
	doc.hold_check().throw_if_failed()
	doc.scheduled_date = getdate(scheduled_date or doc.proposed_date)
	doc.status = "Scheduled"
	doc.save()
	return doc.status


@frappe.whitelist()
def reschedule(rfi: str, new_date: str, reason: str):
	if not (reason or "").strip():
		frappe.throw(_("Enter the reason for rescheduling."))
	doc = _rfi(rfi)
	doc.hold_check().throw_if_failed()
	doc.append(
		"reschedules",
		{
			"date_from": doc.scheduled_date or doc.proposed_date,
			"date_to": new_date,
			"reason": reason,
			"changed_by": frappe.session.user,
		},
	)
	doc.scheduled_date = new_date
	doc.status = "Rescheduled"
	doc.save()
	return doc.status


@frappe.whitelist()
def cancel_rfi(rfi: str, reason: str):
	if not (reason or "").strip():
		frappe.throw(_("Enter the cancellation reason."))
	doc = _rfi(rfi)
	doc.cancellation_reason = reason
	doc.status = "Cancelled"
	doc.save()
	return doc.status


@frappe.whitelist()
def make_inspection_report(rfi: str):
	doc = frappe.get_doc("RFI", rfi)
	doc.check_permission("read")
	frappe.has_permission("Inspection Report", "create", throw=True)
	if doc.status not in ("Scheduled", "Rescheduled", "Inspected"):
		frappe.throw(_("Schedule the RFI before recording the inspection."))
	ir = frappe.new_doc("Inspection Report")
	ir.rfi = doc.name
	ir.location = doc.location
	ir.load_from_rfi()
	ir.flags.ignore_mandatory = True
	ir.insert()
	return ir.name


@frappe.whitelist()
def get_events(start: str, end: str, filters: str | list | None = None):
	"""RFI calendar (QA-11): on the scheduled date, falling back to the proposed date."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or [])
	rows = frappe.get_list(
		"RFI",
		filters=filters,
		or_filters=[["scheduled_date", "between", [start, end]], ["proposed_date", "between", [start, end]]],
		fields=["name", "title", "status", "scheduled_date", "proposed_date", "points_label"],
	)
	start, end = getdate(start), getdate(end)
	out = []
	for row in rows:
		row.event_date = row.scheduled_date or row.proposed_date
		row.all_day = 1
		if start <= getdate(row.event_date) <= end:
			out.append(row)
	return out
