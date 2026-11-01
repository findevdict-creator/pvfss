frappe.listview_settings["Client Project"] = {
	add_fields: ["avl_required", "disabled"],
	get_indicator(doc) {
		if (doc.disabled) return [__("Disabled"), "gray", "disabled,=,1"];
		return doc.avl_required
			? [__("AVL required"), "blue", "avl_required,=,1"]
			: [__("Active"), "green", "disabled,=,0"];
	},
};
