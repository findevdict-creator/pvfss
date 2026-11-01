// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-TRC-02: heat form with summary and Trace.

frappe.ui.form.on("Heat Number", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Trace this heat"), () =>
			frappe.set_route("heat-trace", { type: "Heat Number", key: frm.doc.name })
		);
		const s = frm.doc.__onload && frm.doc.__onload.summary;
		if (s) {
			frm.dashboard.add_comment(
				__("{0} batches · received {1} · shipped {2} · balance {3} · open NCRs {4}", [
					s.batches,
					s.received,
					s.shipped,
					s.balance,
					s.open_ncrs,
				]),
				"blue",
				true
			);
		}
	},
});
