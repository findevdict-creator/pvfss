// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["PDC Maturity Register"] = {
	filters: [
		{
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nReceived\nIssued",
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), 30),
		},
		{ fieldname: "party", label: __("Party"), fieldtype: "Data" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nIn hand\nDeposited\nIssued\nPresented\nCleared\nBounced",
		},
	],
};
