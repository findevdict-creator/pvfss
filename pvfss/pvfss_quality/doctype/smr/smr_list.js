// SCR-SMR-01: status pills; open SMRs by default.
frappe.listview_settings["SMR"] = {
	add_fields: ["workflow_state", "match_issues", "purchase_receipt"],
	filters: [["workflow_state", "not in", ["Accepted", "Rejected"]]],
	get_indicator(doc) {
		const colours = {
			Received: "blue",
			"Under Review": "orange",
			Accepted: "green",
			"Partially accepted": "orange",
			Rejected: "red",
			Cancelled: "gray",
		};
		const state = doc.workflow_state || "Received";
		return [__(state), colours[state] || "gray", `workflow_state,=,${state}`];
	},
};
