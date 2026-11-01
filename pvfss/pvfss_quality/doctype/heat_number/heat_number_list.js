// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-TRC-01: status pills and a Trace action per row.

frappe.listview_settings["Heat Number"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour =
			{ Active: "green", "On hold": "orange", Rejected: "red" }[doc.status] || "gray";
		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
	button: {
		show: () => true,
		get_label: () => __("Trace"),
		get_description: (doc) => __("Trace {0}", [doc.name]),
		action: (doc) => frappe.set_route("heat-trace", { type: "Heat Number", key: doc.name }),
	},
};
