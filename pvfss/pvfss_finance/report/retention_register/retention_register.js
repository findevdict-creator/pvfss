// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["Retention Register"] = {
	filters: [
		{ fieldname: "direction", label: __("Direction"), fieldtype: "Select", options: "\nReceivable\nPayable" },
		{ fieldname: "party", label: __("Party"), fieldtype: "Data" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "from_date", label: __("Due From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Due To"), fieldtype: "Date" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nHeld\nRelease requested\nReleased\nForfeited" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_to_due" && data && data.days_to_due < 0) value = `<span class="text-danger">${value}</span>`;
		return value;
	},
};
