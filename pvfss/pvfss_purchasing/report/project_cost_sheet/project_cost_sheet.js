// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
frappe.query_reports["Project Cost Sheet"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project", reqd: 1 },
	],
};
