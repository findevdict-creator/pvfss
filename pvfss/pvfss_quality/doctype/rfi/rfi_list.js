// SCR-QA-06: status pills.
frappe.listview_settings["RFI"] = {
	add_fields: ["status", "scheduled_date"],
	get_indicator(doc) {
		const colours = {
			Raised: "blue",
			Scheduled: "blue",
			Rescheduled: "orange",
			Inspected: "orange",
			Closed: "green",
			Cancelled: "gray",
		};
		return [__(doc.status), colours[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
