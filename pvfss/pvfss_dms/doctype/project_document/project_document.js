// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-DMS-04 / SCR-DMS-05: revision, lock and submittal actions.

const PDOC = "pvfss.pvfss_dms.doctype.project_document.project_document";

frappe.ui.form.on("Project Document", {
	refresh(frm) {
		const d = frm.doc;
		if (d.current_revision)
			frm.dashboard.add_indicator(__("Rev {0} - current", [d.current_revision]), "blue");
		if (d.locked_by)
			frm.dashboard.add_indicator(
				__("Checked out by {0} since {1}", [
					d.locked_by,
					frappe.datetime.str_to_user(d.locked_on),
				]),
				"orange"
			);
		if (d.customer_response)
			frm.dashboard.add_indicator(
				__(d.customer_response),
				d.customer_response.startsWith("Approved") ? "green" : "orange"
			);
		if (frm.is_new()) return;
		const call = (method, args) =>
			frappe
				.xcall(`${PDOC}.${method}`, { document: d.name, ...(args || {}) })
				.then(() => frm.reload_doc());
		const mine = !d.locked_by || d.locked_by === frappe.session.user;
		if (!d.locked_by) frm.add_custom_button(__("Check out"), () => call("check_out"));
		if (d.locked_by === frappe.session.user)
			frm.add_custom_button(__("Check in"), () => call("check_in"));
		if (
			d.locked_by &&
			d.locked_by !== frappe.session.user &&
			(frappe.user.has_role("Quality Manager") ||
				frappe.user.has_role("Post-Bidding Manager"))
		)
			frm.add_custom_button(__("Force unlock"), () => call("force_unlock"));
		if (mine)
			frm.add_custom_button(__("Upload new revision"), () =>
				frappe.prompt(
					[
						{
							fieldname: "revision",
							fieldtype: "Data",
							label: __("New revision"),
							reqd: 1,
							default: next_rev(d.current_revision),
						},
						{ fieldname: "file_url", fieldtype: "Attach", label: __("File"), reqd: 1 },
						{
							fieldname: "change_note",
							fieldtype: "Small Text",
							label: __("Change note"),
							reqd: 1,
						},
						{ fieldname: "issue_now", fieldtype: "Check", label: __("Issue now") },
					],
					(v) => call("upload_revision", v),
					__("Upload new revision")
				)
			);
		frm.add_custom_button(
			__("Record submittal"),
			() =>
				frappe.prompt(
					[
						{
							fieldname: "transmittal_no",
							fieldtype: "Data",
							label: __("Transmittal No"),
							reqd: 1,
						},
						{
							fieldname: "submitted_date",
							fieldtype: "Date",
							label: __("Submitted"),
							default: frappe.datetime.get_today(),
						},
					],
					(v) => call("record_submittal", v),
					__("Record submittal")
				),
			__("Customer")
		);
		if ((d.submittals || []).some((r) => r.response === "Pending"))
			frm.add_custom_button(
				__("Record response"),
				() =>
					frappe.prompt(
						[
							{
								fieldname: "response",
								fieldtype: "Select",
								label: __("Response"),
								reqd: 1,
								options:
									"Approved\nApproved with comments\nRejected\nRevise and resubmit",
							},
							{
								fieldname: "response_date",
								fieldtype: "Date",
								label: __("Response Date"),
								default: frappe.datetime.get_today(),
							},
							{
								fieldname: "comments_file",
								fieldtype: "Attach",
								label: __("Comments File"),
							},
						],
						(v) => call("record_response", v),
						__("Record response")
					),
				__("Customer")
			);
	},
});

function next_rev(current) {
	if (!current) return "A";
	if (/^\d+$/.test(current)) return String(+current + 1);
	if (/^[A-Y]$/.test(current)) return String.fromCharCode(current.charCodeAt(0) + 1);
	return "";
}
