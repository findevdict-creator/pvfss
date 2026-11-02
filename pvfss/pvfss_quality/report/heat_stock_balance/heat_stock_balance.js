frappe.query_reports["Heat Stock Balance"] = {
	filters: [
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "heat_number",
			label: __("Heat Number"),
			fieldtype: "Link",
			options: "Heat Number",
		},
		{
			fieldname: "supplier_po",
			label: __("Supplier PO"),
			fieldtype: "Link",
			options: "Purchase Order",
		},
		{ fieldname: "show_zero", label: __("Show zero balance"), fieldtype: "Check" },
	],
};
