// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-QA-05: ITP form. Load from template, waive a point (QM), create an RFI.

frappe.ui.form.on("ITP", {
	setup(frm) {
		frm.set_query("supplier_po", () => ({ filters: { docstatus: 1 } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.template) {
			frm.add_custom_button(__("Load from template"), () =>
				frm.call("load_from_template").then(() => frm.refresh_field("points"))
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("RFI"), () => itp_make_rfi(frm), __("Create"));
			if (frappe.user.has_role("Quality Manager")) {
				frm.add_custom_button(__("Waive point"), () => itp_waive(frm));
			}
		}
		if (frm.doc.next_hold_point) {
			frm.dashboard.set_headline_alert(
				`<span class="indicator red">${__("Next open Hold point: {0}", [
					frappe.utils.escape_html(frm.doc.next_hold_point),
				])}</span>&nbsp;&nbsp;<span class="indicator blue">${__("Points closed {0}", [
					frm.doc.points_closed,
				])}</span>`
			);
		}
	},
});

function open_points(frm) {
	return (frm.doc.points || []).filter((p) => p.status === "Open");
}

function itp_make_rfi(frm) {
	const points = open_points(frm);
	frappe.prompt(
		[
			{
				fieldname: "seqs",
				label: __("Points"),
				fieldtype: "MultiCheck",
				options: points.map((p) => ({ label: `${p.seq} ${p.activity}`, value: p.seq })),
				columns: 1,
			},
		],
		(values) =>
			frappe
				.xcall("pvfss.pvfss_quality.doctype.itp.itp.make_rfi", {
					itp: frm.doc.name,
					seqs: values.seqs,
				})
				.then((name) => frappe.set_route("Form", "RFI", name)),
		__("Create RFI"),
		__("Create")
	);
}

function itp_waive(frm) {
	frappe.prompt(
		[
			{
				fieldname: "seq",
				label: __("Point"),
				fieldtype: "Select",
				options: open_points(frm).map((p) => String(p.seq)),
				reqd: 1,
			},
			{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
		],
		(values) =>
			frappe
				.xcall("pvfss.pvfss_quality.doctype.itp.itp.waive_point", {
					itp: frm.doc.name,
					...values,
				})
				.then(() => frm.reload_doc()),
		__("Waive ITP point"),
		__("Waive")
	);
}
