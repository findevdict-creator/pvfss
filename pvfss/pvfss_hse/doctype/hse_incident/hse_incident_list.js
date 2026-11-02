// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-HSE-09: quick incident report from the list.

frappe.listview_settings["HSE Incident"] = {
	onload(list) {
		list.page.add_inner_button(__("Report an incident"), () => window.pvfss_report_incident());
	},
};

window.pvfss_report_incident = function () {
	const d = new frappe.ui.Dialog({
		title: __("Report an HSE incident"),
		fields: [
			{
				fieldname: "incident_type",
				fieldtype: "Select",
				label: __("Type"),
				reqd: 1,
				options: "Injury\nNear miss\nProperty damage\nEnvironmental\nDangerous occurrence",
			},
			{
				fieldname: "incident_datetime",
				fieldtype: "Datetime",
				label: __("Date and Time"),
				reqd: 1,
				default: frappe.datetime.now_datetime(),
			},
			{ fieldname: "location", fieldtype: "Data", label: __("Location"), reqd: 1 },
			{
				fieldname: "description",
				fieldtype: "Small Text",
				label: __("What happened"),
				reqd: 1,
			},
			{
				fieldname: "people",
				fieldtype: "Data",
				label: __("People involved (comma separated)"),
			},
			{
				fieldname: "immediate_action",
				fieldtype: "Small Text",
				label: __("Immediate action taken"),
			},
			{ fieldname: "photo", fieldtype: "Attach Image", label: __("Photo") },
		],
		primary_action_label: __("Report"),
		primary_action(values) {
			frappe
				.xcall("pvfss.pvfss_hse.doctype.hse_incident.hse_incident.report_incident", values)
				.then((name) => {
					d.hide();
					frappe.msgprint(__("Thank you. Incident {0} reported.", [name]));
				});
		},
	});
	d.show();
};
