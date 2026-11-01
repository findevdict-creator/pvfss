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

STATE_STYLES = {
	"Draft": "",
	"Pending Approval": "Warning",
	"Under Review": "Warning",
	"Approved": "Primary",
	"Submitted": "Success",
	"Cancelled": "Inverse",
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
	frappe.db.commit()
	print("PVFSS workflows applied")
