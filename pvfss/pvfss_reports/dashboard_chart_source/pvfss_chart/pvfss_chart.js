// One chart source for every PVFSS workspace chart; the chart key is in the chart's filters.
frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["PVFSS Chart"] = {
	method: "pvfss.pvfss_reports.charts.get",
	filters: [{ fieldname: "chart", label: __("Chart"), fieldtype: "Data" }],
};
