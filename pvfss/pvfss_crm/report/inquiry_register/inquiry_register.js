// Inquiry Register (CRM-11, SCR-CRM-06)

frappe.query_reports["Inquiry Register"] = {
	filters: [
		{ fieldname: "received_from", label: __("Received From"), fieldtype: "Date" },
		{ fieldname: "received_to", label: __("Received To"), fieldtype: "Date" },
		{ fieldname: "due_from", label: __("Due From"), fieldtype: "Date" },
		{ fieldname: "due_to", label: __("Due To"), fieldtype: "Date" },
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
		{
			fieldname: "stage",
			label: __("Stage"),
			fieldtype: "MultiSelectList",
			get_data: () => pvfss.crm.STAGES.map((s) => ({ value: s, description: "" })),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "pvfss_stage" && data && data.pvfss_stage) {
			const color = pvfss.crm.STAGE_COLOURS[data.pvfss_stage] || "gray";
			value = `<span class="indicator-pill ${color}">${__(data.pvfss_stage)}</span>`;
		}
		return value;
	},
};
