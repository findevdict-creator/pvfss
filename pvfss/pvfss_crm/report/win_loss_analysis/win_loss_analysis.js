// Win / Loss Analysis (CRM-13, SCR-CRM-07)

frappe.query_reports["Win Loss Analysis"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Received from"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -365),
		},
		{
			fieldname: "to_date",
			label: __("Received to"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "group_by",
			label: __("Group by"),
			fieldtype: "Select",
			options: ["Contractor", "Client Project", "Product Category", "Owner", "Lost Reason"],
			default: "Contractor",
		},
		{
			fieldname: "party_name",
			label: __("Contractor"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "pvfss_client_project",
			label: __("Client Project"),
			fieldtype: "Link",
			options: "Client Project",
		},
		{ fieldname: "pvfss_owner", label: __("Owner"), fieldtype: "Link", options: "User" },
	],
};
