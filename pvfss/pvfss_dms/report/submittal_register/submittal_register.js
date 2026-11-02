// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["Submittal Register"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "document_type",
			label: __("Type"),
			fieldtype: "Link",
			options: "Project Document Type",
		},
		{
			fieldname: "response",
			label: __("Response"),
			fieldtype: "Select",
			options: "\nPending\nApproved\nApproved with comments\nRejected\nRevise and resubmit",
		},
		{ fieldname: "overdue_only", label: __("Overdue only"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_waiting" && data && data.overdue)
			value = `<span class="text-danger">${value}</span>`;
		return value;
	},
};
