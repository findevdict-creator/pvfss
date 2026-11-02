// Quotation form (SCR-SQ-02): margin badge, approval route, revision.

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.pvfss_costing_sheet || frm.doc.pvfss_approver_role) {
			const route = frm.doc.__onload?.pvfss_approval_route || "";
			const low = frm.doc.pvfss_approver_role === "PVFSS Director";
			frm.dashboard.set_headline_alert(
				`${__("Margin")} ${format_number(
					frm.doc.pvfss_margin_pct || 0,
					null,
					2
				)}% · ${frappe.utils.escape_html(route)}`,
				low ? "orange" : "green"
			);
		}
		if (frm.doc.docstatus === 1 && frm.doc.status !== "Lost" && frm.doc.status !== "Ordered") {
			frm.add_custom_button(__("Revise"), () =>
				frappe.confirm(
					__("Cancel {0} and create the next revision?", [frm.doc.name]),
					() =>
						frappe
							.xcall("pvfss.pvfss_crm.quotation.make_revision", {
								quotation: frm.doc.name,
							})
							.then((name) => frappe.set_route("Form", "Quotation", name))
				)
			);
		}
		if (frm.doc.pvfss_costing_sheet) {
			frm.add_custom_button(
				__("Costing Sheet"),
				() => frappe.set_route("Form", "Costing Sheet", frm.doc.pvfss_costing_sheet),
				__("View")
			);
		}
	},
	pvfss_icv_score_used(frm) {
		frm.trigger("pvfss_recalc_icv");
	},
	pvfss_icv_weightage_pct(frm) {
		frm.trigger("pvfss_recalc_icv");
	},
	pvfss_recalc_icv(frm) {
		const s = (frm.doc.pvfss_icv_score_used || 0) / 100;
		const w = (frm.doc.pvfss_icv_weightage_pct || 0) / 100;
		frm.set_value("pvfss_evaluated_price", (frm.doc.grand_total || 0) * (1 - s * w));
	},
});

// SCR-ICV-07: evaluated price comparison with a competitor.
frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("Compare with competitor"),
			() =>
				window.pvfss_icv_compare({
					bid_price: frm.doc.grand_total,
					icv_score: frm.doc.pvfss_icv_score_used,
					weightage: frm.doc.pvfss_icv_weightage_pct,
				}),
			__("ICV")
		);
	},
});

window.pvfss_icv_compare = function (values) {
	const d = new frappe.ui.Dialog({
		title: __("Evaluated price comparison"),
		fields: [
			{
				fieldname: "bid_price",
				fieldtype: "Currency",
				label: __("PVFSS bid price"),
				reqd: 1,
			},
			{ fieldname: "icv_score", fieldtype: "Percent", label: __("PVFSS ICV score %") },
			{ fieldname: "weightage", fieldtype: "Percent", label: __("Tender ICV weightage %") },
			{ fieldtype: "Column Break" },
			{ fieldname: "competitor", fieldtype: "Data", label: __("Competitor") },
			{
				fieldname: "competitor_bid",
				fieldtype: "Currency",
				label: __("Competitor bid price"),
			},
			{
				fieldname: "competitor_score",
				fieldtype: "Percent",
				label: __("Competitor ICV score %"),
			},
			{ fieldtype: "Section Break" },
			{ fieldname: "result", fieldtype: "HTML" },
		],
	});
	const update = () => {
		const v = d.get_values(true);
		if (!v.bid_price) return;
		frappe.xcall("pvfss.pvfss_icv.icv.compare", v).then((r) => {
			const money = (x) => format_currency(x, "AED");
			let text = `<p>${__("PVFSS evaluated price")}: <b>${money(r.pvfss_evaluated)}</b></p>`;
			if (r.competitor_evaluated) {
				text += `<p>${__("Competitor evaluated price")}: <b>${money(
					r.competitor_evaluated
				)}</b></p>`;
				text +=
					r.difference <= 0
						? `<p class="text-success">${__("PVFSS is lower by {0}", [
								money(-r.difference),
						  ])}</p>`
						: `<p class="text-danger">${__("PVFSS is higher by {0}", [
								money(r.difference),
						  ])}</p>`;
				text += `<p>${__(
					"Bid price to match the competitor's evaluated price"
				)}: <b>${money(r.matching_bid)}</b></p>`;
			}
			d.fields_dict.result.$wrapper.html(text);
		});
	};
	d.fields.forEach(
		(f) =>
			f.fieldname &&
			f.fieldname !== "result" &&
			(d.fields_dict[f.fieldname].df.onchange = update)
	);
	d.show();
	const fill = (v) => {
		d.set_values(v);
		update();
	};
	if (values.icv_score === undefined)
		frappe.xcall("pvfss.pvfss_icv.icv.defaults").then((r) => fill({ ...r, ...values }));
	else fill(values);
};
