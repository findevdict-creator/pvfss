// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["Invoice and Payment Status"] = {
	filters: [
		{ fieldname: "side", label: __("Side"), fieldtype: "Select", options: "Receivable\nPayable", default: "Receivable", reqd: 1 },
		{ fieldname: "party", label: __("Party"), fieldtype: "Data" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nOverdue\nPaid" },
		{ fieldname: "payment_method", label: __("Payment Method"), fieldtype: "Select", options: "\nTT\nPDC\nLC" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_overdue" && data && data.days_overdue > 0) value = `<span class="text-danger">${value}</span>`;
		return value;
	},
};
