// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-DMS-03

frappe.listview_settings["Project Document"] = {
	add_fields: ["status", "locked_by", "customer_response"],
	get_indicator(doc) {
		const colour = { Draft: "gray", Issued: "green", Superseded: "gray" }[doc.status];
		return [__(doc.status) + (doc.locked_by ? " 🔒" : ""), colour, `status,=,${doc.status}`];
	},
};
