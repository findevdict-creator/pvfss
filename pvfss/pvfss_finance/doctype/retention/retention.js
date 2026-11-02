// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-FIN-13: Request release, Release and Forfeit.

const RET = "pvfss.pvfss_finance.doctype.retention.retention";

frappe.ui.form.on("Retention", {
	refresh(frm) {
		const call = (method, args) =>
			frappe.xcall(`${RET}.${method}`, { retention: frm.doc.name, ...(args || {}) }).then(() => frm.reload_doc());
		if (frm.doc.status === "Held") frm.add_custom_button(__("Request release"), () => call("request_release"));
		if (!["Held", "Release requested"].includes(frm.doc.status) || !frappe.user.has_role("Finance Manager")) return;
		frm.add_custom_button(__("Release"), () => call("release")).addClass("btn-primary");
		frm.add_custom_button(__("Forfeit"), () =>
			frappe.prompt(
				[{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 }],
				(v) => call("forfeit", v),
				__("Forfeit retention")
			)
		);
	},
});
