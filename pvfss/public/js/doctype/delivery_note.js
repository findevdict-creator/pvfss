// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-DSP-01 to SCR-DSP-05: dispatch gate panel, documents chip and Record POD on the Delivery Note.

const DSP = "pvfss.pvfss_logistics.dispatch";

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.is_return) return;
		if (frm.doc.pvfss_documents_ready) {
			const [ready, total] = frm.doc.pvfss_documents_ready.split("/").map(Number);
			frm.dashboard.add_indicator(
				__("Documents {0}", [frm.doc.pvfss_documents_ready]),
				ready === total ? "green" : "orange"
			);
		}
		if (frm.doc.pvfss_dispatch_gate) {
			frm.dashboard.add_indicator(
				__("Dispatch gate: {0}", [frm.doc.pvfss_dispatch_gate]),
				frm.doc.pvfss_dispatch_gate === __("OK") ? "green" : "red"
			);
		}
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Check dispatch gate"), () => dispatch_gate(frm));
		}
		if (frm.doc.docstatus === 1 && !frm.doc.pvfss_pod_date) {
			frm.add_custom_button(__("Record POD"), () => record_pod(frm)).addClass("btn-primary");
		}
		if (frm.doc.pvfss_sales_invoice) {
			frm.add_custom_button(__("Draft invoice"), () =>
				frappe.set_route("Form", "Sales Invoice", frm.doc.pvfss_sales_invoice)
			);
		}
	},
});

function dispatch_gate(frm) {
	frappe.xcall(`${DSP}.check_gate`, { delivery_note: frm.doc.name }).then((r) => {
		const esc = frappe.utils.escape_html;
		const items = r.failures.length
			? r.failures
					.map(
						(f) =>
							`<li class="text-danger">✗ ${esc(f.message)} ${
								f.url ? `<a href="${f.url}">${__("Open")}</a>` : ""
							} <small class="text-muted">${esc(f.rule || "")}</small></li>`
					)
					.join("")
			: `<li class="text-success">✓ ${__("Ready for dispatch")}</li>`;
		frappe.msgprint({
			title: __("Dispatch gate"),
			message: `<ul class="list-unstyled">${items}</ul>`,
			indicator: r.failures.length ? "red" : "green",
		});
	});
}

function record_pod(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Record POD"),
		fields: [
			{ fieldname: "pod_date", fieldtype: "Date", label: __("POD Date"), reqd: 1, default: frappe.datetime.get_today() },
			{ fieldname: "received_by", fieldtype: "Data", label: __("Received by"), reqd: 1 },
			{ fieldname: "pod_attachment", fieldtype: "Attach", label: __("Signed POD"), reqd: 1 },
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frappe
				.xcall(`${DSP}.record_pod`, { delivery_note: frm.doc.name, ...values })
				.then((si) => {
					d.hide();
					frm.reload_doc();
					if (si) frappe.show_alert({ message: __("Draft invoice {0} created", [si]), indicator: "green" });
				});
		},
	});
	d.show();
}
