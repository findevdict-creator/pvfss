frappe.listview_settings["Costing Sheet"] = {
	add_fields: ["margin_pct", "quotation", "docstatus", "non_compliant_lines"],
	get_indicator(doc) {
		if (doc.docstatus === 2) return [__("Cancelled"), "gray", "docstatus,=,2"];
		if (doc.quotation) return [__("Quotation created"), "green", "quotation,is,set"];
		if (doc.non_compliant_lines > 0)
			return [__("Not compliant"), "red", "non_compliant_lines,>,0"];
		if (doc.docstatus === 1) return [__("Submitted"), "blue", "docstatus,=,1"];
		return [__("Draft"), "gray", "docstatus,=,0"];
	},
};
