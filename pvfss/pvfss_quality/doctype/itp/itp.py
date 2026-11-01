# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

OPEN, CLOSED, WAIVED = "Open", "Closed", "Waived"
DONE = (CLOSED, WAIVED)
TEMPLATE_FIELDS = (
	"seq",
	"activity",
	"point_type",
	"applicable_lines",
	"check_type",
	"reference_standard",
	"acceptance_criteria",
	"pvfss_point",
	"tpi_point",
	"customer_point",
	"records_required",
)


def is_hold(point):
	return "H" in (point.pvfss_point, point.tpi_point, point.customer_point)


def point_codes(point):
	return " / ".join(p or "-" for p in (point.pvfss_point, point.tpi_point, point.customer_point))


def lines_of(value):
	return {v.strip() for v in (value or "").split(",") if v.strip()}


def applies_to(point, line_ref, itp_lines=None):
	lines = lines_of(point.applicable_lines) or lines_of(itp_lines)
	return not lines or str(line_ref) in lines


class ITP(Document):
	"""Inspection and Test Plan (QA-03, QA-04, SCR-QA-05)."""

	def validate(self):
		if self.template and not self.points:
			self.load_from_template()
		seqs = [p.seq for p in self.points]
		if len(seqs) != len(set(seqs)):
			frappe.throw(_("Each ITP point needs its own sequence number."))
		self.points.sort(key=lambda p: p.seq)
		for idx, point in enumerate(self.points, start=1):
			point.idx = idx
		self.refresh_progress()

	def before_submit(self):
		if self.customer_approval_required and not self.customer_approval_ref:
			frappe.throw(_("Enter the customer approval reference before approving this ITP (QA-04)."))

	@frappe.whitelist()
	def load_from_template(self):
		template = frappe.get_doc("ITP Template", self.template)
		self.set("points", [{f: row.get(f) for f in TEMPLATE_FIELDS} for row in template.points])

	def refresh_progress(self):
		done = [p for p in self.points if p.status in DONE]
		self.points_closed = f"{len(done)}/{len(self.points)}"
		holds = [p for p in self.points if is_hold(p) and p.status not in DONE]
		self.hold_points_open = len(holds)
		self.next_hold_point = f"{holds[0].seq} ({holds[0].activity})" if holds else None

	def save_progress(self):
		self.refresh_progress()
		for point in self.points:
			point.db_update()
		self.db_set(
			{
				"points_closed": self.points_closed,
				"hold_points_open": self.hold_points_open,
				"next_hold_point": self.next_hold_point,
			}
		)


def set_points(itp, seqs, status, closed_by=None):
	"""Close (or reopen) points from an Inspection Report."""
	doc = frappe.get_doc("ITP", itp)
	for point in doc.points:
		if point.seq in seqs and point.status != WAIVED:
			point.status = status
			point.closed_by = closed_by if status == CLOSED else None
	doc.save_progress()


@frappe.whitelist()
def waive_point(itp: str, seq: int | str, reason: str):
	"""SCR-QA-05 "Waive point": Quality Manager only, with a reason (QA-33 a)."""
	if "Quality Manager" not in frappe.get_roles():
		frappe.throw(_("Only the Quality Manager can waive an ITP point."), frappe.PermissionError)
	if not (reason or "").strip():
		frappe.throw(_("Enter the waiver reason."))
	doc = frappe.get_doc("ITP", itp)
	doc.check_permission("read")
	point = next((p for p in doc.points if p.seq == int(seq)), None)
	if not point:
		frappe.throw(_("ITP {0} has no point {1}.").format(itp, seq))
	point.status = WAIVED
	point.waiver_reason = reason.strip()
	point.waived_by = frappe.session.user
	doc.save_progress()
	doc.add_comment("Info", _("Point {0} waived: {1}").format(seq, reason))
	return point.status


@frappe.whitelist()
def make_rfi(itp: str, seqs: str | list | None = None):
	"""SCR-QA-05 Create ▸ RFI for the selected (default: next open) points."""
	doc = frappe.get_doc("ITP", itp)
	doc.check_permission("read")
	if doc.docstatus != 1:
		frappe.throw(_("Only an approved ITP can be used on an RFI (QA-04)."))
	seqs = frappe.parse_json(seqs) if isinstance(seqs, str) else seqs
	open_points = [p for p in doc.points if p.status == OPEN]
	chosen = [p for p in open_points if p.seq in {int(s) for s in seqs}] if seqs else open_points[:1]
	rfi = frappe.get_doc(
		{
			"doctype": "RFI",
			"supplier_po": doc.supplier_po,
			"itp": doc.name,
			"points": [{"seq": p.seq} for p in chosen],
		}
	)
	rfi.flags.ignore_mandatory = True
	rfi.insert()
	return rfi.name
