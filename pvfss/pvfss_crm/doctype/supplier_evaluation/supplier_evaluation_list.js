// SCR-SUP-04: weighted score colour bands.
frappe.listview_settings["Supplier Evaluation"] = {
	add_fields: ["band", "weighted_total", "docstatus"],
	get_indicator(doc) {
		if (doc.docstatus === 0) return [__("Draft"), "gray", "docstatus,=,0"];
		const colours = { Good: "green", Satisfactory: "blue", Weak: "orange", Poor: "red" };
		return [
			`${__(doc.band || "")} ${doc.weighted_total || ""}`,
			colours[doc.band] || "gray",
			`band,=,${doc.band}`,
		];
	},
};
