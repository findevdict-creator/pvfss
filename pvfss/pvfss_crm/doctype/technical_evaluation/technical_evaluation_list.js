frappe.listview_settings["Technical Evaluation"] = {
	add_fields: ["not_compliant_count", "docstatus"],
	get_indicator(doc) {
		if (doc.docstatus === 2) return [__("Cancelled"), "gray", "docstatus,=,2"];
		if (doc.not_compliant_count > 0)
			return [__("Not compliant"), "red", "not_compliant_count,>,0"];
		if (doc.docstatus === 1) return [__("Submitted"), "green", "docstatus,=,1"];
		return [__("Draft"), "gray", "docstatus,=,0"];
	},
};
