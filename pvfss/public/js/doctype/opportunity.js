// Inquiry form (SCR-CRM-02): stage pill, due badge, duplicate banner, Import Lines, No Bid / Cancel.

const PVFSS_IMPORT = "pvfss.pvfss_crm.inquiry_import";

frappe.ui.form.on("Opportunity", {
	setup(frm) {
		frm.set_query("pvfss_client_project", () => ({
			filters: frm.doc.party_name
				? { main_contractor: frm.doc.party_name, disabled: 0 }
				: { disabled: 0 },
		}));
	},

	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("opportunity_from", "Customer");
			if (!frm.doc.pvfss_owner) frm.set_value("pvfss_owner", frappe.session.user);
		}
	},

	refresh(frm) {
		pvfss.crm.show_head(frm);
		if (frm.is_new()) return;

		const closed = pvfss.crm.CLOSED.includes(frm.doc.pvfss_stage);
		if (!closed && frm.doc.pvfss_stage === "New") {
			frm.add_custom_button(__("Import Lines"), () => pvfss.crm.import_dialog(frm));
		}
		if (!["Won", "Lost", "No Bid", "Cancelled"].includes(frm.doc.pvfss_stage)) {
			frm.add_custom_button(__("Mark No Bid / Cancel"), () => pvfss.crm.close_dialog(frm));
		}
		pvfss.crm.add_bid_buttons(frm, closed);
		frm.add_custom_button(
			__("Download template"),
			() => window.open(`/api/method/${PVFSS_IMPORT}.download_template`),
			__("Lines")
		);
	},

	party_name(frm) {
		if (frm.doc.party_name && !frm.doc.pvfss_portal) {
			frappe.db
				.get_value("Customer", frm.doc.party_name, "pvfss_portal_name")
				.then(
					(r) => r.message && frm.set_value("pvfss_portal", r.message.pvfss_portal_name)
				);
		}
	},
});

pvfss.crm.show_head = function (frm) {
	frm.dashboard.clear_headline();
	const stage = frm.doc.pvfss_stage || "New";
	frm.page.set_indicator(__(stage), pvfss.crm.STAGE_COLOURS[stage] || "gray");

	if (frm.doc.pvfss_duplicate_of && !frm.doc.pvfss_not_duplicate) {
		frm.dashboard.set_headline_alert(
			`${__("Possible duplicate of")} <a href="/app/opportunity/${
				frm.doc.pvfss_duplicate_of
			}">${frm.doc.pvfss_duplicate_of}</a>. ${__(
				"Tick 'Confirmed not a duplicate' to continue."
			)}`,
			"orange"
		);
		return;
	}
	if (frm.doc.pvfss_bid_due_date && !pvfss.crm.CLOSED.includes(stage) && stage !== "Quoted") {
		const days = frappe.datetime.get_day_diff(
			frm.doc.pvfss_bid_due_date,
			frappe.datetime.now_date()
		);
		if (days < 0) frm.dashboard.set_headline_alert(__("Overdue"), "red");
		else if (days <= 2)
			frm.dashboard.set_headline_alert(__("Due in {0} days", [days]), "orange");
	}
};

pvfss.crm.import_dialog = function (frm) {
	let file_url = null;
	const d = new frappe.ui.Dialog({
		title: __("Import Lines"),
		size: "extra-large",
		fields: [
			{
				fieldtype: "HTML",
				options: `<a href="/api/method/${PVFSS_IMPORT}.download_template">${__(
					"Download PVFSS inquiry template"
				)}</a>`,
			},
			{ fieldname: "file", label: __("File (.xlsx / .csv)"), fieldtype: "Attach", reqd: 1 },
			{
				fieldname: "mode",
				label: __("Mode"),
				fieldtype: "Select",
				options: ["Append", "Replace existing lines"],
				default: "Append",
			},
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Preview"),
		primary_action(values) {
			file_url = values.file;
			const replace = values.mode !== "Append" ? 1 : 0;
			if (d.previewed) {
				frappe
					.xcall(`${PVFSS_IMPORT}.import_lines`, {
						inquiry: frm.doc.name,
						file_url,
						replace,
					})
					.then((n) => {
						d.hide();
						frappe.show_alert({
							message: __("{0} lines imported", [n]),
							indicator: "green",
						});
						frm.reload_doc();
					});
				return;
			}
			frappe
				.xcall(`${PVFSS_IMPORT}.preview`, { inquiry: frm.doc.name, file_url, replace })
				.then((r) => {
					const esc = frappe.utils.escape_html;
					const rows = r.rows
						.map(
							(row) => `<tr>
						<td>${esc(row.pvfss_customer_line_ref || "")}</td>
						<td>${esc(row.pvfss_specification || "")}</td>
						<td>${row.qty || ""}</td><td>${esc(row.uom || "")}</td>
						<td>${esc(row.matched_item || __("Generic"))}</td>
						<td><span class="indicator-pill ${row.status === "OK" ? "green" : "red"}">${esc(
								row.status === "OK" ? __("OK") : row.message
							)}</span></td></tr>`
						)
						.join("");
					d.fields_dict.preview.$wrapper.html(`
					<p>${__("{0} rows OK, {1} errors", [r.ok, r.errors])}</p>
					<div style="max-height:400px;overflow:auto"><table class="table table-bordered table-sm">
					<thead><tr><th>${__("Line ref")}</th><th>${__("Specification")}</th><th>${__("Qty")}</th>
					<th>${__("UOM")}</th><th>${__("Matched item")}</th><th>${__("Status")}</th></tr></thead>
					<tbody>${rows}</tbody></table></div>`);
					d.previewed = r.ok > 0;
					d.set_primary_action(__("Import OK rows"), d.primary_action);
					d.get_primary_btn().prop("disabled", !r.ok);
				});
		},
	});
	d.show();
};

pvfss.crm.close_dialog = function (frm) {
	const d = new frappe.ui.Dialog({
		title: __("Mark No Bid / Cancel"),
		fields: [
			{
				fieldname: "stage",
				label: __("New stage"),
				fieldtype: "Select",
				options: ["No Bid", "Cancelled"],
				reqd: 1,
			},
			{
				fieldname: "lost_reasons",
				label: __("Lost reason"),
				fieldtype: "MultiSelectList",
				reqd: 1,
				get_data: (txt) => frappe.db.get_link_options("Opportunity Lost Reason", txt),
			},
			{ fieldname: "detail", label: __("Detail"), fieldtype: "Small Text", reqd: 1 },
			{ fieldname: "competitor_name", label: __("Competitor name"), fieldtype: "Data" },
			{
				fieldname: "competitor_price",
				label: __("Competitor price (AED)"),
				fieldtype: "Currency",
			},
		],
		primary_action_label: __("Confirm"),
		primary_action(values) {
			frappe
				.xcall("pvfss.pvfss_crm.inquiry.mark_closed", { inquiry: frm.doc.name, ...values })
				.then(() => {
					d.hide();
					frm.reload_doc();
				});
		},
	});
	d.show();
};

// ---------------------------------------------------------------------------- 06-rfq (SCR-CRM-02 actions)
pvfss.crm.add_bid_buttons = function (frm, closed) {
	const stage = frm.doc.pvfss_stage || "New";
	const open_for_rfq = ["New", "RFQ Sent", "Quotes Received", "Under Evaluation"].includes(stage);
	if (!closed && open_for_rfq && (frm.doc.items || []).length) {
		frm.add_custom_button(
			__("RFQ"),
			() =>
				frappe
					.xcall("pvfss.pvfss_crm.rfq.make_rfq", { inquiry: frm.doc.name })
					.then((doc) => {
						frappe.model.sync(doc);
						frappe.set_route("Form", doc.doctype, doc.name);
					}),
			__("Create")
		);
	}
	frappe.db
		.count("Supplier Quotation", { filters: { opportunity: frm.doc.name, docstatus: ["<", 2] } })
		.then((count) => {
			if (!count) return;
			frm.add_custom_button(
				__("Competitive Statement"),
				() => frappe.set_route("query-report", "Competitive Statement", { inquiry: frm.doc.name }),
				__("View")
			);
			if (closed) return;
			frm.add_custom_button(
				__("Costing Sheet"),
				() =>
					frappe
						.xcall("pvfss.pvfss_crm.doctype.costing_sheet.costing_sheet.make_or_refresh", {
							inquiry: frm.doc.name,
						})
						.then((name) => frappe.set_route("Form", "Costing Sheet", name)),
				__("Create")
			);
			frm.add_custom_button(
				__("Technical Evaluation"),
				() => frappe.new_doc("Technical Evaluation", { inquiry: frm.doc.name }),
				__("Create")
			);
		});
};
