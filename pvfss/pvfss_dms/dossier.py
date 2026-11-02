"""Final dossier export (DMS-10, SCR-DMS-07): ZIP of current revisions in folder order with an index PDF."""

import io
import zipfile

import frappe
from frappe import _
from frappe.utils import formatdate
from frappe.utils.pdf import get_pdf

EXPORT_ROLES = {"Post-Bidding Manager", "Quality Manager", "System Manager"}
SUBFOLDER_ORDER = (
	"01 Inquiry & RFQ",
	"02 Quotation & Customer PO",
	"03 Supplier PO",
	"04 Quality",
	"05 Dispatch",
	"06 Finance",
	"07 Correspondence",
	"08 Final dossier",
)


def dossier_rows(project, types=None, include_superseded=False):
	filters = {"project": project, "current_file": ["is", "set"]}
	if not include_superseded:
		filters["status"] = ["!=", "Superseded"]
	if types:
		filters["document_type"] = ["in", types]
	rows = frappe.get_all(
		"Project Document",
		filters=filters,
		fields=[
			"name",
			"document_no",
			"title",
			"document_type",
			"current_revision",
			"current_file",
			"issue_date",
		],
	)
	folders = {
		t.name: t.default_subfolder
		for t in frappe.get_all("Project Document Type", fields=["name", "default_subfolder"])
	}
	for row in rows:
		row.subfolder = folders.get(row.document_type) or "07 Correspondence"
	order = {s: i for i, s in enumerate(SUBFOLDER_ORDER)}
	return sorted(rows, key=lambda r: (order.get(r.subfolder, 99), r.document_no))


def _file_bytes(file_url):
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	return frappe.get_doc("File", name).get_content() if name else None


def build(project, types=None, include_superseded=False):
	rows = dossier_rows(project, types, include_superseded)
	buffer = io.BytesIO()
	index = [
		f"<h2>{frappe.utils.escape_html(_('Final dossier'))}: {frappe.utils.escape_html(project)}</h2>",
		"<table border='1' cellpadding='4' style='border-collapse:collapse;width:100%'>",
		"<tr><th>#</th><th>{}</th><th>{}</th><th>{}</th><th>{}</th><th>{}</th></tr>".format(
			_("Folder"), _("Document No"), _("Title"), _("Rev"), _("Date")
		),
	]
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		for i, row in enumerate(rows, start=1):
			content = _file_bytes(row.current_file)
			if content is None:
				continue
			if isinstance(content, str):
				content = content.encode()
			filename = row.current_file.rsplit("/", 1)[-1]
			zf.writestr(
				f"{row.subfolder}/{row.document_no}_Rev{row.current_revision or ''}_{filename}", content
			)
			index.append(
				"<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
					i,
					frappe.utils.escape_html(row.subfolder),
					frappe.utils.escape_html(row.document_no),
					frappe.utils.escape_html(row.title),
					frappe.utils.escape_html(row.current_revision or ""),
					formatdate(row.issue_date) if row.issue_date else "",
				)
			)
		index.append("</table>")
		zf.writestr("00 Index.pdf", get_pdf("".join(index)))
	return buffer.getvalue(), len(rows)


@frappe.whitelist()
def export(project: str, types: str | None = None, include_superseded: int = 0):
	if not EXPORT_ROLES & set(frappe.get_roles()):
		frappe.throw(
			_("Only a Post-Bidding or Quality Manager can export the final dossier."), frappe.PermissionError
		)
	frappe.has_permission("Project", "read", doc=project, throw=True)
	frappe.has_permission("Project Document", "read", throw=True)
	content, _count = build(
		project, frappe.parse_json(types) if types else None, int(include_superseded or 0)
	)
	frappe.response["filename"] = f"{project} - final dossier.zip"
	frappe.response["filecontent"] = content
	frappe.response["type"] = "binary"
