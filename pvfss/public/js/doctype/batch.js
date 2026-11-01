// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-TRC-05: heat status banner and Trace on the Batch form.

frappe.ui.form.on("Batch", {
	refresh(frm) {
		const status = frm.doc.pvfss_heat_status;
		if (status === "On hold" || status === "Rejected") {
			frm.dashboard.set_headline_alert(
				`<span class="indicator ${status === "Rejected" ? "red" : "orange"}">${__("Heat {0} is {1}", [
					frm.doc.pvfss_heat_number,
					__(status),
				])}</span>`
			);
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Trace"), () =>
				frappe.set_route("heat-trace", { type: "Batch", key: frm.doc.name })
			);
		}
	},
});
