"""PVFSS workflows (SQ-06, SQ-09; later PUR-10, FIN-31).

Pure data plus a developer helper that writes them to the site; they ship as Workflow,
Workflow State and Workflow Action Master fixtures.

    bench --site pvfss.localhost execute pvfss.setup.workflows.apply
"""

import frappe

DIR = "PVFSS Director"
PBU = "Pre-Bidding User"
PBM = "Pre-Bidding Manager"
POU = "Post-Bidding User"
POM = "Post-Bidding Manager"
QU = "Quality User"
QM = "Quality Manager"
UNDER = "Under Review"

STATE_STYLES = {
	"Customer Approval": "Warning",
	"Pending Quality Manager": "Warning",
	"Accepted with re-test": "Info",
	"Supplier action": "Warning",
	"Verification": "Warning",
	"Closed": "Success",
	"Issued": "Success",
	"Received": "Info",
	"Partially accepted": "Warning",
	"Deviation Approval": "Warning",
	"Value Approval": "Warning",
	"Director Approval": "Warning",
	"Draft": "",
	"Pending Approval": "Warning",
	"Under Review": "Warning",
	"Approved": "Primary",
	"Submitted": "Success",
	"Cancelled": "Inverse",
	"Pending Acceptance": "Warning",
	"Returned": "Danger",
	"Accepted": "Success",
	"Open": "Warning",
	"Rejected": "Danger",
	"Implemented": "Success",
}

WORKFLOWS = {
	# SQ-06 / G2: approval by margin band
	"PVFSS Quotation": {
		"document_type": "Quotation",
		"states": [
			("Draft", 0, PBU),
			("Draft", 0, PBM),
			("Pending Approval", 0, PBM),
			("Pending Approval", 0, DIR),
			("Approved", 0, PBU),
			("Approved", 0, PBM),
			("Submitted", 1, PBU),
			("Submitted", 1, PBM),
			("Cancelled", 2, PBM),
		],
		"transitions": [
			("Draft", "Send for Approval", "Pending Approval", PBU, None),
			("Draft", "Send for Approval", "Pending Approval", PBM, None),
			(
				"Pending Approval",
				"Approve",
				"Approved",
				PBM,
				'doc.pvfss_approver_role == "Pre-Bidding Manager"',
			),
			("Pending Approval", "Approve", "Approved", DIR, None),
			("Pending Approval", "Reject", "Draft", PBM, None),
			("Pending Approval", "Reject", "Draft", DIR, None),
			("Approved", "Return to Draft", "Draft", PBU, None),
			("Approved", "Return to Draft", "Draft", PBM, None),
			("Approved", "Submit", "Submitted", PBU, None),
			("Approved", "Submit", "Submitted", PBM, None),
			("Submitted", "Cancel", "Cancelled", PBM, None),
		],
	},
	# PUR-05, PUR-06, PUR-07, PUR-10 / G3: Supplier PO approvals
	"PVFSS Supplier PO": {
		"document_type": "Purchase Order",
		"states": [
			("Draft", 0, POU),
			("Draft", 0, POM),
			("Draft", 0, PBU),
			("Deviation Approval", 0, POM),
			("Value Approval", 0, POM),
			("Value Approval", 0, DIR),
			("Director Approval", 0, DIR),
			("Approved", 0, POU),
			("Approved", 0, POM),
			("Submitted", 1, POU),
			("Submitted", 1, POM),
			("Cancelled", 2, POM),
		],
		"transitions": [
			*[
				(
					"Draft",
					"Send for Approval",
					nxt,
					role,
					cond,
				)
				for role in (POU, POM, PBU)
				for nxt, cond in (
					("Deviation Approval", "doc.pvfss_deviation_count"),
					(
						"Director Approval",
						'not doc.pvfss_deviation_count and doc.pvfss_approval_route == "Director Approval"',
					),
					(
						"Value Approval",
						'not doc.pvfss_deviation_count and doc.pvfss_approval_route != "Director Approval"',
					),
				)
			],
			(
				"Deviation Approval",
				"Approve Deviations",
				"Director Approval",
				POM,
				'doc.pvfss_approval_route == "Director Approval"',
			),
			(
				"Deviation Approval",
				"Approve Deviations",
				"Value Approval",
				POM,
				'doc.pvfss_approval_route != "Director Approval"',
			),
			("Deviation Approval", "Reject", "Draft", POM, None),
			("Value Approval", "Approve", "Approved", POM, 'doc.pvfss_approval_route != "Director Approval"'),
			("Value Approval", "Approve", "Approved", DIR, None),
			("Value Approval", "Reject", "Draft", POM, None),
			("Value Approval", "Reject", "Draft", DIR, None),
			("Director Approval", "Approve", "Approved", DIR, None),
			("Director Approval", "Reject", "Draft", DIR, None),
			("Approved", "Return to Draft", "Draft", POU, None),
			("Approved", "Return to Draft", "Draft", POM, None),
			("Approved", "Submit", "Submitted", POU, None),
			("Approved", "Submit", "Submitted", POM, None),
			("Submitted", "Cancel", "Cancelled", POM, None),
		],
	},
	# SQ-09: Customer PO review against the quotation
	"PVFSS Customer PO": {
		"document_type": "Sales Order",
		"states": [
			("Draft", 0, PBU),
			("Draft", 0, POU),
			("Draft", 0, POM),
			("Under Review", 0, POM),
			("Approved", 0, POU),
			("Approved", 0, POM),
			("Submitted", 1, POU),
			("Submitted", 1, POM),
			("Cancelled", 2, POM),
		],
		"transitions": [
			("Draft", "Submit for Review", "Under Review", PBU, "doc.pvfss_review_complete"),
			("Draft", "Submit for Review", "Under Review", POU, "doc.pvfss_review_complete"),
			("Draft", "Submit for Review", "Under Review", POM, "doc.pvfss_review_complete"),
			("Under Review", "Approve", "Approved", POM, None),
			("Under Review", "Return", "Draft", POM, None),
			("Under Review", "Submit", "Submitted", POU, "not doc.pvfss_difference_count"),
			("Under Review", "Submit", "Submitted", POM, "not doc.pvfss_difference_count"),
			("Approved", "Return to Draft", "Draft", POU, None),
			("Approved", "Return to Draft", "Draft", POM, None),
			("Approved", "Submit", "Submitted", POU, None),
			("Approved", "Submit", "Submitted", POM, None),
			("Submitted", "Cancel", "Cancelled", POM, None),
		],
	},
	# PRJ-01 to PRJ-04 / G4: Pre-Bidding hands over, the Post-Bidding Manager accepts or returns
	"PVFSS Project Handover": {
		"document_type": "Project Handover",
		"states": [
			("Draft", 0, PBU),
			("Draft", 0, PBM),
			("Pending Acceptance", 0, POM),
			("Returned", 0, PBU),
			("Returned", 0, PBM),
			("Accepted", 1, POM),
			("Cancelled", 2, POM),
		],
		"transitions": [
			("Draft", "Submit Handover", "Pending Acceptance", PBM, None),
			("Pending Acceptance", "Accept", "Accepted", POM, None),
			("Pending Acceptance", "Return", "Returned", POM, None),
			("Returned", "Submit Handover", "Pending Acceptance", PBM, None),
			("Accepted", "Cancel", "Cancelled", POM, None),
		],
	},
	# PRJ-30: change register; a change that reduces margin needs the Director
	"PVFSS Project Change": {
		"document_type": "Project Change",
		"states": [
			("Open", 0, POU),
			("Open", 0, POM),
			("Approved", 1, POM),
			("Approved", 1, DIR),
			("Rejected", 1, POM),
			("Rejected", 1, DIR),
			("Implemented", 1, POU),
			("Implemented", 1, POM),
		],
		"transitions": [
			("Open", "Approve", "Approved", POM, "(doc.margin_impact or 0) >= 0"),
			("Open", "Approve", "Approved", DIR, None),
			("Open", "Reject", "Rejected", POM, None),
			("Open", "Reject", "Rejected", DIR, None),
			("Approved", "Implement", "Implemented", POU, None),
			("Approved", "Implement", "Implemented", POM, None),
		],
	},
	# SMR-01 / SCR-SMR-02: ready-stock offer review
	"PVFSS SMR": {
		"document_type": "SMR",
		"states": [
			("Received", 0, QU),
			("Received", 0, QM),
			("Received", 0, POU),
			("Under Review", 0, QU),
			("Under Review", 0, QM),
			("Accepted", 1, QU),
			("Accepted", 1, QM),
			("Partially accepted", 1, QU),
			("Partially accepted", 1, QM),
			("Rejected", 1, QU),
			("Rejected", 1, QM),
			("Cancelled", 2, QM),
		],
		"transitions": [
			("Received", "Start Review", "Under Review", QU, None),
			("Received", "Start Review", "Under Review", QM, None),
			*[
				(UNDER, action, state, role, None)
				for action, state in (
					("Accept", "Accepted"),
					("Partially Accept", "Partially accepted"),
					("Reject", "Rejected"),
				)
				for role in (QU, QM)
			],
			("Accepted", "Cancel", "Cancelled", QM, None),
			("Partially accepted", "Cancel", "Cancelled", QM, None),
			("Rejected", "Cancel", "Cancelled", QM, None),
		],
	},
	# QA-04: ITP approval; customer approval only when required
	"PVFSS ITP": {
		"document_type": "ITP",
		"states": [
			("Draft", 0, QU),
			("Draft", 0, QM),
			("Customer Approval", 0, QM),
			("Approved", 1, QM),
			("Cancelled", 2, QM),
		],
		"transitions": [
			(
				"Draft",
				"Send for Customer Approval",
				"Customer Approval",
				QM,
				"doc.customer_approval_required",
			),
			("Draft", "Approve", "Approved", QM, "not doc.customer_approval_required"),
			("Customer Approval", "Approve", "Approved", QM, None),
			("Customer Approval", "Reject", "Draft", QM, None),
			("Approved", "Cancel", "Cancelled", QM, None),
		],
	},
	# QA-23: Quality User reviews, Quality Manager decides
	"PVFSS MTC": {
		"document_type": "MTC",
		"states": [
			("Draft", 0, QU),
			("Draft", 0, QM),
			("Under Review", 0, QU),
			("Under Review", 0, QM),
			("Pending Quality Manager", 0, QM),
			("Accepted", 1, QM),
			("Rejected", 1, QM),
			("Accepted with re-test", 1, QM),
			("Cancelled", 2, QM),
		],
		"transitions": [
			("Draft", "Submit for Review", "Under Review", QU, None),
			("Draft", "Submit for Review", "Under Review", QM, None),
			("Under Review", "Send to Quality Manager", "Pending Quality Manager", QU, None),
			("Under Review", "Send to Quality Manager", "Pending Quality Manager", QM, None),
			("Pending Quality Manager", "Accept", "Accepted", QM, None),
			("Pending Quality Manager", "Accept with Re-test", "Accepted with re-test", QM, None),
			("Pending Quality Manager", "Reject", "Rejected", QM, None),
			("Pending Quality Manager", "Return", "Under Review", QM, None),
			("Accepted", "Cancel", "Cancelled", QM, None),
			("Rejected", "Cancel", "Cancelled", QM, None),
			("Accepted with re-test", "Cancel", "Cancelled", QM, None),
		],
	},
	# SCR-QA-16: NCR life cycle on the standard Non Conformance
	"PVFSS NCR": {
		"document_type": "Non Conformance",
		"states": [
			("Open", 0, QU),
			("Open", 0, QM),
			("Supplier action", 0, QU),
			("Supplier action", 0, QM),
			("Supplier action", 0, POU),
			("Verification", 0, QU),
			("Verification", 0, QM),
			("Closed", 0, QM),
		],
		"transitions": [
			("Open", "Send to Supplier", "Supplier action", QU, None),
			("Open", "Send to Supplier", "Supplier action", QM, None),
			("Supplier action", "Submit for Verification", "Verification", QU, None),
			("Supplier action", "Submit for Verification", "Verification", QM, None),
			("Supplier action", "Submit for Verification", "Verification", POU, None),
			("Verification", "Close", "Closed", QM, None),
			("Verification", "Return", "Supplier action", QM, None),
		],
	},
	# QA-34: IRN issue by the Quality Manager
	"PVFSS IRN": {
		"document_type": "IRN",
		"states": [
			("Draft", 0, QU),
			("Draft", 0, QM),
			("Pending Quality Manager", 0, QM),
			("Issued", 1, QM),
			("Cancelled", 2, QM),
		],
		"transitions": [
			("Draft", "Send for Approval", "Pending Quality Manager", QU, None),
			("Draft", "Send for Approval", "Pending Quality Manager", QM, None),
			("Pending Quality Manager", "Issue", "Issued", QM, None),
			("Pending Quality Manager", "Return", "Draft", QM, None),
			("Issued", "Cancel", "Cancelled", QM, None),
		],
	},
}


def state_names():
	return sorted({s[0] for wf in WORKFLOWS.values() for s in wf["states"]})


def action_names():
	return sorted({t[1] for wf in WORKFLOWS.values() for t in wf["transitions"]})


def apply():
	for state in state_names():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert()
		frappe.db.set_value("Workflow State", state, "style", STATE_STYLES.get(state, ""))
	for action in action_names():
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert()

	for name, spec in WORKFLOWS.items():
		doc = (
			frappe.get_doc("Workflow", name)
			if frappe.db.exists("Workflow", name)
			else frappe.new_doc("Workflow")
		)
		doc.workflow_name = name
		doc.document_type = spec["document_type"]
		doc.workflow_state_field = "workflow_state"
		doc.is_active = 1
		doc.send_email_alert = 0
		doc.override_status = 0
		doc.set(
			"states",
			[
				{"state": s, "doc_status": str(ds), "allow_edit": role, "update_field": None}
				for s, ds, role in spec["states"]
			],
		)
		doc.set(
			"transitions",
			[
				{
					"state": s,
					"action": a,
					"next_state": n,
					"allowed": role,
					"allow_self_approval": 1,
					"condition": cond,
				}
				for s, a, n, role, cond in spec["transitions"]
			],
		)
		doc.save()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit (setup step run from install / setup wizard hooks; later steps need it persisted)
	print("PVFSS workflows applied")
