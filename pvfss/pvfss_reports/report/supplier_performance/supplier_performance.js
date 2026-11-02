// Supplier Performance (RPT-07, SCR-RPT-08)

frappe.query_reports["Supplier Performance"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -365),
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "supplier_group",
			label: __("Supplier Group"),
			fieldtype: "Link",
			options: "Supplier Group",
		},
		{
			fieldname: "product_category",
			label: __("Product Category"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
	],
};
