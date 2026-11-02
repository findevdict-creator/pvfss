"""Module 14 tests (DMS-01 to DMS-10). Names carry the requirement ID (GEN-07)."""

import io
import zipfile
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from pvfss.pvfss_crm.test_quotation import make_user
from pvfss.pvfss_dms import dossier, filing
from pvfss.pvfss_dms.doctype.project_document import project_document as pd
from pvfss.pvfss_dms.report.submittal_register import submittal_register
from pvfss.pvfss_purchasing.test_project import accepted_project, ready_handover, receive_manual_rows
from pvfss.setup import masters
from pvfss.tests import factories as f


def attach(doctype, name, file_name="doc.txt", content=b"text test"):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": content,
			"attached_to_doctype": doctype,
			"attached_to_name": name,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)


def project_document(project, document_type="MTC", document_no="MTC-0001", **kw):
	return frappe.get_doc(
		{
			"doctype": "Project Document",
			"project": project,
			"document_type": document_type,
			"document_no": document_no,
			"title": kw.pop("title", f"{document_type} {document_no}"),
			**kw,
		}
	).insert()


def new_revision(doc, note="First issue", content=b"text rev", **kw):
	file = attach("Project Document", doc.name, f"{doc.document_no}.txt", content)
	rev = pd.upload_revision(doc.name, file.file_url, note, **kw)
	return rev, file


class TestDMS(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		f.ensure_test_company()
		masters.seed_document_types()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ------------------------------------------------------------------ DMS-02
	def test_dms02_attachments_land_in_project_subfolders(self):
		so, po, handover = ready_handover()
		early = attach("Sales Order", so.name, "customer_po.txt")
		self.assertEqual(frappe.db.get_value("File", early.name, "folder"), filing.ATTACHMENTS)

		from pvfss.tests.factories import walk_workflow

		handover = walk_workflow(receive_manual_rows(handover), "Submit Handover", "Accept")
		project = handover.project
		root = filing.project_folder("Project", project)
		# attached before the project existed: moved when the folders were created
		self.assertEqual(
			frappe.db.get_value("File", early.name, "folder"), f"{root}/02 Quotation & Customer PO"
		)
		po_file = attach("Purchase Order", po.name, "supplier_po.txt")
		self.assertEqual(frappe.db.get_value("File", po_file.name, "folder"), f"{root}/03 Supplier PO")
		self.assertEqual(filing.project_folder("Purchase Order", po.name), root)
		mtc = project_document(project)
		mtc_file = attach("Project Document", mtc.name, "mtc.txt")
		self.assertEqual(frappe.db.get_value("File", mtc_file.name, "folder"), f"{root}/04 Quality")
		# not linked to a project: stays in Attachments
		other = attach("Customer", so.customer, "profile.txt")
		self.assertEqual(frappe.db.get_value("File", other.name, "folder"), filing.ATTACHMENTS)

	# ------------------------------------------------------------------ DMS-03 / DMS-04 / DMS-05
	def test_dms03_metadata_required_to_issue(self):
		*_rest, project = accepted_project()
		doc = project_document(project.name)
		self.assertEqual([r.label for r in doc.metadata], ["Heat No", "Grade", "Issue Date"])
		new_revision(doc)
		doc.reload()
		doc.status = "Issued"
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		for row, value in zip(doc.metadata, ("H12345", "A106 Gr.B", nowdate()), strict=True):
			row.value = value
		doc.status = "Issued"
		doc.save()
		self.assertIn("H12345", doc.metadata_text)
		self.assertEqual(doc.issued_by, "Administrator")
		self.assertRaises(frappe.ValidationError, project_document, project.name)  # same document no

	def test_dms04_revision_keeps_previous_file(self):
		*_rest, project = accepted_project()
		doc = project_document(project.name, "Drawing", "DWG-001")
		rev_a, file_a = new_revision(doc)
		rev_b, file_b = new_revision(doc, "Nozzle moved", b"text rev b")
		self.assertEqual((rev_a, rev_b), ("A", "B"))
		self.assertEqual(pd.next_revision("Z"), "AA")
		self.assertEqual(pd.next_revision("0"), "1")
		doc.reload()
		self.assertEqual(doc.current_revision, "B")
		self.assertEqual(doc.current_file, file_b.file_url)
		self.assertEqual(
			[(r.revision, r.file, r.is_current) for r in doc.revisions],
			[("A", file_a.file_url, 0), ("B", file_b.file_url, 1)],
		)
		self.assertTrue(frappe.db.exists("File", file_a.name))
		self.assertRaises(frappe.ValidationError, pd.upload_revision, doc.name, file_b.file_url, "again", "B")

	def test_dms05_check_out_lock(self):
		*_rest, project = accepted_project()
		doc = project_document(project.name, "Procedure", "PRC-001")
		other = make_user("dms.other@pvfss.test", "Quality User")
		manager = make_user("dms.qm@pvfss.test", "Quality Manager")
		pd.check_out(doc.name)
		frappe.set_user(other)
		file = attach("Project Document", doc.name, "prc.txt")
		self.assertRaises(frappe.ValidationError, pd.upload_revision, doc.name, file.file_url, "edit")
		self.assertRaises(frappe.PermissionError, pd.force_unlock, doc.name)
		frappe.set_user(manager)
		pd.force_unlock(doc.name)
		frappe.set_user(other)
		self.assertEqual(pd.upload_revision(doc.name, file.file_url, "edit"), "A")

	# ------------------------------------------------------------------ DMS-06 / DMS-07
	def test_dms06_overdue_submittal_and_approval_stamp(self):
		*_rest, project = accepted_project()
		late = project_document(project.name, "ITP", "ITP-001")
		new_revision(late)
		pd.record_submittal(late.name, "TR-001", add_days(nowdate(), -20))
		quick = project_document(project.name, "Data sheet", "DS-001")
		new_revision(quick)
		pd.record_submittal(quick.name, "TR-002", add_days(nowdate(), -3))
		self.assertEqual(pd.record_response(quick.name, "Approved"), 3)

		_cols, rows = submittal_register.execute({"project": project.name, "overdue_only": 1})
		self.assertEqual([r["document_no"] for r in rows], ["ITP-001"])
		self.assertEqual(rows[0]["days_waiting"], 20)

		quick.reload()
		self.assertEqual(quick.customer_response, "Approved")
		stamp = quick.approval_stamp()
		self.assertEqual((stamp.label, stamp.revision), ("Approved", "A"))
		html = f.render_print(quick, "PVFSS Approved Document")
		self.assertIn("DS-001", html)
		self.assertIn("Approved", html)
		self.assertIsNone(frappe.get_doc("Project Document", late.name).approval_stamp())

	# ------------------------------------------------------------------ DMS-08
	def test_dms08_global_search_settings(self):
		masters.seed_global_search()
		allowed = set(frappe.get_all("Global Search DocType", pluck="document_type"))
		self.assertTrue({"Project Document", "Sales Order", "Purchase Order"} <= allowed)

	# ------------------------------------------------------------------ DMS-10
	@patch(
		"pvfss.pvfss_dms.dossier.get_pdf", lambda html: b"%PDF index " + html.encode()
	)  # no wkhtmltopdf in CI
	def test_dms10_final_dossier_zip(self):
		*_rest, project = accepted_project()
		itp = project_document(project.name, "ITP", "ITP-001")
		new_revision(itp)
		new_revision(itp, "Rev B", b"text b")
		mtc = project_document(project.name, "MTC", "MTC-001")
		new_revision(mtc)
		project_document(project.name, "Drawing", "DWG-EMPTY")  # no file: left out
		content, count = dossier.build(project.name)
		self.assertEqual(count, 2)
		names = zipfile.ZipFile(io.BytesIO(content)).namelist()
		self.assertEqual(names[-1], "00 Index.pdf")
		self.assertEqual(len([n for n in names if n.startswith("04 Quality/")]), 2)
		self.assertTrue(any("ITP-001_RevB_" in n for n in names))
		index = zipfile.ZipFile(io.BytesIO(content)).read("00 Index.pdf").decode()
		self.assertLess(index.index("ITP-001"), index.index("MTC-001"))
		_content, count = dossier.build(project.name, types=["MTC"])
		self.assertEqual(count, 1)
		user = make_user("dms.pou@pvfss.test", "Post-Bidding User")
		frappe.set_user(user)
		self.assertRaises(frappe.PermissionError, dossier.export, project.name)
