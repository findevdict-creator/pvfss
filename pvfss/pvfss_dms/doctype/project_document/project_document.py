# Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, now_datetime, nowdate

from pvfss.utils import settings

UNLOCK_ROLES = {"Quality Manager", "Post-Bidding Manager", "System Manager"}


def next_revision(current):
	"""A -> B, Z -> AA, 0 -> 1; blank -> A."""
	if not current:
		return "A"
	if current.isdigit():
		return str(int(current) + 1)
	if current.isalpha() and current.isupper():
		chars = list(current)
		i = len(chars) - 1
		while i >= 0:
			if chars[i] != "Z":
				chars[i] = chr(ord(chars[i]) + 1)
				return "".join(chars)
			chars[i] = "A"
			i -= 1
		return "A" + "".join(chars)
	return f"{current}.1"


class ProjectDocument(Document):
	"""Controlled project document (DMS-03 to DMS-06)."""

	def validate(self):
		self.sync_metadata()
		duplicate = frappe.db.get_value(
			"Project Document",
			{"project": self.project, "document_no": self.document_no, "name": ["!=", self.name or ""]},
			"name",
		)
		if duplicate:
			frappe.throw(
				_("Document {0} is already registered on {1} as {2}.").format(
					self.document_no, self.project, duplicate
				)
			)
		if self.status == "Issued":
			missing = [r.label for r in self.metadata if r.required and not (r.value or "").strip()]
			if missing:
				frappe.throw(_("Fill the mandatory metadata before issuing: {0}.").format(", ".join(missing)))
			if not self.current_file:
				frappe.throw(_("Upload a revision before issuing."))
			self.issue_date = self.issue_date or getdate(nowdate())
			if not self.issued_by or self.has_value_changed("status"):
				self.issued_by = frappe.session.user
		overdue_days = settings.get_int("submittal_overdue_days", 14)
		for row in self.submittals:
			end = row.response_date if row.response not in (None, "", "Pending") else nowdate()
			row.days_waiting = max(date_diff(end, row.submitted_date), 0) if row.submitted_date else 0
		latest = self.submittals[-1] if self.submittals else None
		self.customer_response = latest.response if latest else None
		self.flags.overdue = bool(
			latest and latest.response == "Pending" and latest.days_waiting > overdue_days
		)

	def sync_metadata(self):
		"""Rows follow the document type's mandatory metadata; values are kept."""
		values = {r.label: r.value for r in self.metadata}
		spec = frappe.get_all(
			"Project Document Metadata Field",
			filters={"parent": self.document_type, "parenttype": "Project Document Type"},
			fields=["label", "fieldtype", "options", "required"],
			order_by="idx",
		)
		labels = {s.label for s in spec}
		extra = [r for r in self.metadata if r.label not in labels]
		self.set("metadata", [])
		for s in spec:
			self.append("metadata", {**s, "value": values.get(s.label)})
		for r in extra:
			self.append("metadata", {"label": r.label, "value": r.value})
		self.metadata_text = "; ".join(f"{r.label}: {r.value}" for r in self.metadata if r.value)

	def approval_stamp(self):
		"""DMS-07: Approved by / date / revision, from the latest customer approval or the issue."""
		for row in reversed(self.submittals):
			if row.response in ("Approved", "Approved with comments"):
				return frappe._dict(
					label=_(row.response),
					by=self.customer_name(),
					date=row.response_date,
					revision=row.revision,
				)
		if self.status == "Issued":
			name = frappe.db.get_value("User", self.issued_by, "full_name") if self.issued_by else None
			return frappe._dict(
				label=_("Issued"),
				by=name or self.issued_by,
				date=self.issue_date,
				revision=self.current_revision,
			)
		return None

	def customer_name(self):
		return frappe.db.get_value("Project", self.project, "customer") or _("Customer")

	def check_lock(self):
		if self.locked_by and self.locked_by != frappe.session.user:
			frappe.throw(
				_("{0} has checked this document out since {1}.").format(
					self.locked_by, frappe.utils.format_datetime(self.locked_on)
				)
			)


def _doc(name, ptype="write"):
	doc = frappe.get_doc("Project Document", name)
	doc.check_permission(ptype)
	return doc


@frappe.whitelist()
def check_out(document: str):
	doc = _doc(document)
	doc.check_lock()
	doc.locked_by, doc.locked_on = frappe.session.user, now_datetime()
	doc.save()
	return doc.locked_by


@frappe.whitelist()
def check_in(document: str):
	doc = _doc(document)
	doc.check_lock()
	doc.locked_by = doc.locked_on = None
	doc.save()


@frappe.whitelist()
def force_unlock(document: str):
	if not UNLOCK_ROLES & set(frappe.get_roles()):
		frappe.throw(
			_("Only a Quality or Post-Bidding Manager can force the unlock."), frappe.PermissionError
		)
	doc = _doc(document)
	previous = doc.locked_by
	doc.locked_by = doc.locked_on = None
	doc.save()
	doc.add_comment("Info", _("Unlocked (was checked out by {0}).").format(previous))


@frappe.whitelist()
def upload_revision(
	document: str, file_url: str, change_note: str, revision: str | None = None, issue_now: int = 0
):
	"""SCR-DMS-05: new current revision; earlier files stay in the history (DMS-04)."""
	doc = _doc(document)
	doc.check_lock()
	if not (change_note or "").strip():
		frappe.throw(_("Enter the change note."))
	revision = (revision or next_revision(doc.current_revision)).strip()
	if any(r.revision == revision for r in doc.revisions):
		frappe.throw(_("Revision {0} already exists.").format(revision))
	for row in doc.revisions:
		row.is_current = 0
	doc.append(
		"revisions",
		{
			"revision": revision,
			"file": file_url,
			"revision_date": now_datetime(),
			"revised_by": frappe.session.user,
			"change_note": change_note,
			"is_current": 1,
		},
	)
	doc.current_revision, doc.current_file = revision, file_url
	doc.locked_by = doc.locked_on = None
	if int(issue_now or 0):
		doc.status = "Issued"
		doc.issue_date = getdate(nowdate())
	doc.save()
	return revision


@frappe.whitelist()
def record_submittal(document: str, transmittal_no: str, submitted_date: str | None = None):
	doc = _doc(document)
	if not frappe.db.get_value("Project Document Type", doc.document_type, "customer_submittal"):
		frappe.msgprint(_("This document type does not need customer submittal."), alert=True)
	doc.append(
		"submittals",
		{
			"transmittal_no": transmittal_no,
			"revision": doc.current_revision,
			"submitted_date": submitted_date or nowdate(),
		},
	)
	doc.save()


@frappe.whitelist()
def record_response(
	document: str, response: str, response_date: str | None = None, comments_file: str | None = None
):
	doc = _doc(document)
	pending = [r for r in doc.submittals if r.response == "Pending"]
	if not pending:
		frappe.throw(_("There is no submittal waiting for a response."))
	row = pending[-1]
	row.update(
		{"response": response, "response_date": response_date or nowdate(), "comments_file": comments_file}
	)
	doc.save()
	return row.days_waiting
