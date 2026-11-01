// SCR-QA-07: RFI calendar on the scheduled date (falls back to the proposed date).
frappe.views.calendar["RFI"] = {
	field_map: {
		start: "event_date",
		end: "event_date",
		id: "name",
		title: "title",
		allDay: "all_day",
		status: "status",
	},
	style_map: {
		Raised: "info",
		Scheduled: "info",
		Rescheduled: "warning",
		Inspected: "warning",
		Closed: "success",
		Cancelled: "default",
	},
	get_events_method: "pvfss.pvfss_quality.doctype.rfi.rfi.get_events",
};
