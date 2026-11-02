// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["Cash-flow Forecast"] = {
	filters: [
		{ fieldname: "start_date", label: __("Start Week"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "weeks", label: __("Weeks"), fieldtype: "Int", default: 13 },
		{ fieldname: "bank_accounts", label: __("Bank Accounts"), fieldtype: "MultiSelectList", get_data: (txt) => frappe.db.get_link_options("Account", txt, { account_type: "Bank", is_group: 0 }) },
		{ fieldname: "include_lc", label: __("Include expected LC receipts"), fieldtype: "Check", default: 1 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.line === __("Closing balance") && data[column.fieldname] < 0) value = `<span class="text-danger">${value}</span>`;
		return value;
	},
};
