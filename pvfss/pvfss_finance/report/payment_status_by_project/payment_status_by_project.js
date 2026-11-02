// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["Payment Status by Project"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
	],
};
