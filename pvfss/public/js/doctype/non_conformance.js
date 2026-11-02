// SCR-QA-16: NCR form. Major / Critical NCRs hold the affected heats (TRC-04, server side).
frappe.ui.form.on("Non Conformance", {
	refresh(frm) {
		const heats = (frm.doc.pvfss_heats || []).filter((r) => r.heat_number);
		if (heats.length && ["Major", "Critical"].includes(frm.doc.pvfss_severity)) {
			frm.dashboard.set_headline_alert(
				`<span class="indicator ${
					frm.doc.workflow_state === "Closed" ? "green" : "red"
				}">${
					frm.doc.workflow_state === "Closed"
						? __("Heats released")
						: __("Heats on hold: {0}", [heats.map((r) => r.heat_number).join(", ")])
				}</span>`
			);
		}
		if (heats.length) {
			frm.add_custom_button(__("Trace heat"), () =>
				frappe.set_route("heat-trace", { type: "Heat Number", key: heats[0].heat_number })
			);
		}
	},
});
