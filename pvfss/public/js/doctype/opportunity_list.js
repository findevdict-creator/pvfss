// Inquiry list (SCR-CRM-01): stage pill, open inquiries by default, due-date colouring.

frappe.listview_settings["Opportunity"] = {
	add_fields: ["pvfss_stage", "pvfss_bid_due_date", "pvfss_contractor_ref"],
	filters: [["pvfss_stage", "not in", ["Won", "Lost", "No Bid", "Cancelled"]]],
	get_indicator(doc) {
		const stage = doc.pvfss_stage || "New";
		return [__(stage), (pvfss.crm.STAGE_COLOURS || {})[stage] || "gray", `pvfss_stage,=,${stage}`];
	},
	formatters: {
		pvfss_bid_due_date(value, df, doc) {
			if (!value) return "";
			const text = frappe.datetime.str_to_user(value);
			if ((pvfss.crm.CLOSED || []).includes(doc.pvfss_stage) || doc.pvfss_stage === "Quoted") return text;
			const days = frappe.datetime.get_day_diff(value, frappe.datetime.now_date());
			const color = days < 0 ? "var(--red-600)" : days <= 2 ? "var(--orange-600)" : "inherit";
			return `<span style="color:${color}">${text}</span>`;
		},
	},
};
