// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-HSE-11: Create CAPA from the incident.

frappe.ui.form.on("HSE Incident", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.workflow_state === "Closed") return;
		frm.add_custom_button(__("Create CAPA"), () =>
			frappe.prompt(
				[
					{
						fieldname: "action_type",
						fieldtype: "Select",
						options: "Corrective\nPreventive",
						label: __("Action Type"),
						reqd: 1,
						default: "Corrective",
					},
					{
						fieldname: "description",
						fieldtype: "Small Text",
						label: __("Description"),
						reqd: 1,
					},
					{
						fieldname: "action_owner",
						fieldtype: "Link",
						options: "User",
						label: __("Owner"),
						reqd: 1,
					},
					{ fieldname: "due_date", fieldtype: "Date", label: __("Due Date"), reqd: 1 },
				],
				(v) =>
					frappe
						.xcall("pvfss.pvfss_hse.doctype.hse_incident.hse_incident.make_capa", {
							incident: frm.doc.name,
							...v,
						})
						.then(() => frm.reload_doc()),
				__("Create CAPA")
			)
		);
	},
});
