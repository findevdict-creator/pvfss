"""Automatic filing of attachments into the project folders (DMS-01, DMS-02)."""

import frappe

from pvfss.pvfss_purchasing.project import create_folders

ATTACHMENTS = "Home/Attachments"
SUBFOLDER = {
	"Opportunity": "01 Inquiry & RFQ",
	"Request for Quotation": "01 Inquiry & RFQ",
	"Supplier Quotation": "01 Inquiry & RFQ",
	"Costing Sheet": "01 Inquiry & RFQ",
	"Quotation": "02 Quotation & Customer PO",
	"Sales Order": "02 Quotation & Customer PO",
	"Project Handover": "02 Quotation & Customer PO",
	"Purchase Order": "03 Supplier PO",
	"Expediting Log": "03 Supplier PO",
	"Purchase Receipt": "03 Supplier PO",
	"SMR": "04 Quality",
	"Tally Sheet": "04 Quality",
	"MTC": "04 Quality",
	"ITP": "04 Quality",
	"RFI": "04 Quality",
	"Inspection Report": "04 Quality",
	"Non Conformance": "04 Quality",
	"IRN": "04 Quality",
	"Quality Document Submittal": "04 Quality",
	"Delivery Note": "05 Dispatch",
	"Sales Invoice": "06 Finance",
	"Purchase Invoice": "06 Finance",
	"Payment Entry": "06 Finance",
	"Letter of Credit": "06 Finance",
	"Project": "07 Correspondence",
	"Project Document": None,  # the document type's default subfolder
}
# fields that lead from a document to the next one up the chain
LINKS = (
	("project", "Project"),
	("pvfss_project", "Project"),
	("supplier_po", "Purchase Order"),
	("pvfss_supplier_po", "Purchase Order"),
	("purchase_order", "Purchase Order"),
	("pvfss_sales_order", "Sales Order"),
	("sales_order", "Sales Order"),
	("against_sales_order", "Sales Order"),
	("rfi", "RFI"),
	("smr", "SMR"),
	("opportunity", "Opportunity"),
	("pvfss_inquiry", "Opportunity"),
)
MAX_DEPTH = 4


def project_of(doctype, name, depth=0):
	"""The Project a document belongs to, following its links (header first, then the first item)."""
	if not name or depth > MAX_DEPTH or not frappe.db.exists(doctype, name):
		return None
	if doctype == "Project":
		return name
	if doctype == "Opportunity":
		so = frappe.db.get_value("Sales Order", {"pvfss_inquiry": name, "docstatus": 1}, "name")
		return project_of("Sales Order", so, depth + 1) if so else None
	meta = frappe.get_meta(doctype)
	values = frappe.db.get_value(
		doctype, name, [f for f, _dt in LINKS if meta.has_field(f)] or ["name"], as_dict=True
	)
	for fieldname, target in LINKS:
		if meta.has_field(fieldname) and values.get(fieldname):
			found = project_of(target, values[fieldname], depth + 1)
			if found:
				return found
	items = meta.get_field("items")
	if items:
		child_meta = frappe.get_meta(items.options)
		fields = [f for f, _dt in LINKS if child_meta.has_field(f)]
		if fields:
			row = frappe.db.get_value(
				items.options, {"parent": name, "parenttype": doctype}, fields, as_dict=True
			)
			for fieldname, target in LINKS:
				if row and row.get(fieldname):
					found = project_of(target, row[fieldname], depth + 1)
					if found:
						return found
	return None


def folder_for(project, subfolder):
	root = create_folders(frappe.get_doc("Project", project))
	return f"{root}/{subfolder}"


def target_folder(doctype, name):
	if doctype not in SUBFOLDER:
		return None
	project = project_of(doctype, name)
	if not project:
		return None
	subfolder = SUBFOLDER[doctype]
	if doctype == "Project Document":
		subfolder = frappe.db.get_value(
			"Project Document Type",
			frappe.db.get_value("Project Document", name, "document_type"),
			"default_subfolder",
		)
	return folder_for(project, subfolder or "07 Correspondence")


def file_attachment(doc, method=None):
	"""File after_insert: move a new attachment into its project subfolder (DMS-02)."""
	if doc.is_folder or not doc.attached_to_doctype or (doc.folder or ATTACHMENTS) != ATTACHMENTS:
		return
	folder = target_folder(doc.attached_to_doctype, doc.attached_to_name)
	if folder:
		doc.db_set("folder", folder, update_modified=False)


def file_existing(project):
	"""When the project folders are created: move earlier attachments of its documents (DMS-02)."""
	moved = 0
	for row in frappe.get_all(
		"File",
		filters={"folder": ATTACHMENTS, "is_folder": 0, "attached_to_doctype": ["in", list(SUBFOLDER)]},
		fields=["name", "attached_to_doctype", "attached_to_name"],
	):
		if project_of(row.attached_to_doctype, row.attached_to_name) != project:
			continue
		folder = target_folder(row.attached_to_doctype, row.attached_to_name)
		if folder:
			frappe.db.set_value("File", row.name, "folder", folder, update_modified=False)
			moved += 1
	return moved


@frappe.whitelist()
def project_folder(doctype: str, name: str):
	"""SCR-DMS-01 'Open project folder' on Project, Customer PO and Supplier PO."""
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	project = project_of(doctype, name)
	return create_folders(frappe.get_doc("Project", project)) if project else None
