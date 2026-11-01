frappe.listview_settings["Inspection Agency"] = {
	add_fields: ["active"],
	filters: [["active", "=", 1]],
	get_indicator(doc) {
		return doc.active
			? [__("Active"), "green", "active,=,1"]
			: [__("Inactive"), "gray", "active,=,0"];
	},
};
