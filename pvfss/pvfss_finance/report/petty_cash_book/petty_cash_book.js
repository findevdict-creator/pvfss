// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors

frappe.query_reports["Petty Cash Book"] = {
	filters: [
		{
			fieldname: "custodian",
			label: __("Custodian"),
			fieldtype: "Link",
			options: "Employee",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
