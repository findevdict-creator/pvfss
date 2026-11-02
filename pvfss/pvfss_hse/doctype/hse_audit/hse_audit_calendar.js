// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-HSE-13: audit schedule on the planned date.

frappe.views.calendar["HSE Audit"] = {
	field_map: {
		start: "planned_date",
		end: "planned_date",
		id: "name",
		title: "title",
		allDay: "allDay",
	},
	get_events_method: "pvfss.pvfss_hse.doctype.hse_audit.hse_audit.get_events",
	filters: [
		{
			fieldtype: "Select",
			fieldname: "audit_type",
			options: "\nInternal audit\nExternal audit\nSite inspection",
			label: __("Type"),
		},
	],
};
