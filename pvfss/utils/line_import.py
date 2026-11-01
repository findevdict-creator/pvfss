"""Shared spreadsheet line import (CRM-04, later RFQ-06 and SMR-03).

Reads an uploaded .xlsx or .csv (a File record), maps header labels to field names and
returns plain dict rows. Each importer validates the rows itself and returns a preview with
a status per row; nothing is written until the user confirms.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.csvutils import read_csv_content
from frappe.utils.xlsxutils import make_xlsx, read_xlsx_file_from_attached_file


def _norm(label):
	return re.sub(r"[^a-z0-9]+", " ", (label or "").lower()).strip()


def read_rows(file_url, columns):
	"""Return a list of dicts keyed by fieldname.

	``columns`` is a list of (fieldname, label, aliases...) tuples; header cells are matched
	case- and punctuation-insensitively against the label and aliases.
	"""
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	content = file_doc.get_content()
	if file_doc.file_name.lower().endswith((".xlsx", ".xlsm")):
		raw = read_xlsx_file_from_attached_file(fcontent=content)
	elif file_doc.file_name.lower().endswith(".csv"):
		raw = read_csv_content(content)
	else:
		frappe.throw(_("Upload an .xlsx or .csv file."))

	raw = [r for r in raw if any(c not in (None, "") for c in r)]
	if not raw:
		return []

	lookup = {}
	for fieldname, *labels in columns:
		for label in labels:
			lookup[_norm(label)] = fieldname
		lookup[_norm(fieldname)] = fieldname

	header = [lookup.get(_norm(str(c or ""))) for c in raw[0]]
	if not any(header):
		frappe.throw(_("The first row must hold the column headings of the PVFSS template."))

	rows = []
	for idx, cells in enumerate(raw[1:], start=2):
		row = {"_row": idx}
		for fieldname, value in zip(header, cells, strict=False):
			if fieldname:
				row[fieldname] = value.strip() if isinstance(value, str) else value
		rows.append(row)
	return rows


def template_response(filename, columns, sample_rows=None):
	"""Send an .xlsx template with the column labels as the header row."""
	data = [[c[1] for c in columns], *(sample_rows or [])]
	xlsx = make_xlsx(data, "Lines")
	frappe.response["filename"] = filename
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"


def to_float(value):
	if value in (None, ""):
		return None
	try:
		return flt(str(value).replace(",", ""))
	except Exception:
		return None
