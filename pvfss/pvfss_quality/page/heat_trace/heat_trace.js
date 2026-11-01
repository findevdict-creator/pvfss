// Copyright (c) 2026, Quantum-Electro Pvt Ltd and contributors
// SCR-TRC-03 Heat Trace: search, backward / forward chain, table view, PDF and certificate pack.

frappe.pages["heat-trace"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Heat Trace"),
		single_column: true,
	});
	wrapper.heat_trace = new pvfss.HeatTrace(page);
};

frappe.pages["heat-trace"].on_page_show = function (wrapper) {
	const opts = frappe.route_options || {};
	frappe.route_options = null;
	if (opts.key && wrapper.heat_trace) {
		wrapper.heat_trace.search(opts.type || "Heat Number", opts.key, opts.direction);
	}
};

frappe.provide("pvfss");

const SEARCH_LINKS = {
	"Heat Number": "Heat Number",
	Batch: "Batch",
	"MTC No": null,
	"Supplier PO": "Purchase Order",
	"Customer PO": "Sales Order",
	"Delivery Note": "Delivery Note",
	"Sales Invoice": "Sales Invoice",
};
const RECENT_KEY = "pvfss_heat_trace_recent";

pvfss.HeatTrace = class HeatTrace {
	constructor(page) {
		this.page = page;
		this.result = null;
		this.view = "chain";
		this.make_controls();
		this.$body = $(`<div class="pvfss-trace mt-3"></div>`).appendTo(page.main);
		this.render_empty();
		page.set_primary_action(__("Trace"), () => this.search());
		page.add_menu_item(__("Export Traceability Report (PDF)"), () =>
			this.download("download_report")
		);
		page.add_menu_item(__("Download certificate pack (ZIP)"), () =>
			this.download("download_certificate_pack")
		);
		page.add_menu_item(__("Copy link to this trace"), () => this.copy_link());
		page.add_inner_button(__("Table view"), () => this.toggle_view());
	}

	make_controls() {
		this.type = this.page.add_field({
			fieldname: "type",
			label: __("Search by"),
			fieldtype: "Select",
			options: Object.keys(SEARCH_LINKS).join("\n"),
			default: "Heat Number",
			change: () => this.set_key_type(),
		});
		this.key = this.page.add_field({
			fieldname: "key",
			label: __("Search"),
			fieldtype: "Link",
			options: "Heat Number",
		});
		this.direction = this.page.add_field({
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nForward\nBackward",
		});
	}

	set_key_type() {
		const doctype = SEARCH_LINKS[this.type.get_value()];
		this.key.df.fieldtype = doctype ? "Link" : "Data";
		this.key.df.options = doctype || "";
		this.key.refresh();
	}

	search(type, key, direction) {
		if (type) {
			this.type.set_value(type);
			this.key.set_value(key);
			if (direction) this.direction.set_value(direction);
		}
		const args = this.args();
		if (!args.key) {
			frappe.show_alert({ message: __("Enter a value to trace"), indicator: "orange" });
			return;
		}
		this.remember(args);
		frappe.xcall("pvfss.pvfss_quality.traceability.trace", args).then((r) => {
			this.result = r;
			this.render();
		});
	}

	args() {
		return {
			search_type: this.type.get_value(),
			key: this.key.get_value(),
			direction: (this.direction.get_value() || "").toLowerCase() || null,
		};
	}

	remember(args) {
		try {
			const recent = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]").filter(
				(r) => r.key !== args.key
			);
			recent.unshift(args);
			localStorage.setItem(RECENT_KEY, JSON.stringify(recent.slice(0, 8)));
		} catch (e) {
			// storage unavailable: recent searches are a convenience only
		}
	}

	recent() {
		try {
			return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
		} catch (e) {
			return [];
		}
	}

	render_empty() {
		const chips = this.recent()
			.map(
				(r) =>
					`<button class="btn btn-xs btn-default mr-1 mb-1" data-type="${frappe.utils.escape_html(
						r.search_type
					)}" data-key="${frappe.utils.escape_html(r.key)}">${frappe.utils.escape_html(
						r.key
					)}</button>`
			)
			.join("");
		this.$body.html(`<div class="text-muted">
			<p>${__(
				"Trace by heat number, batch, MTC no, Supplier PO, Customer PO, Delivery Note or Sales Invoice."
			)}</p>
			<p>${__(
				"Forward runs from a heat to every customer; backward runs from a delivery or invoice to the mill."
			)}</p>
			<div>${chips}</div></div>`);
		this.$body.find("button[data-key]").on("click", (e) => {
			const $b = $(e.currentTarget);
			this.search($b.attr("data-type"), $b.attr("data-key"));
		});
	}

	render() {
		const r = this.result;
		const esc = frappe.utils.escape_html;
		const header = `<div class="mb-3"><b>${esc(r.search_type)}: ${esc(r.key)}</b>
			<span class="text-muted"> · ${__("{0} heats, {1} lots, {2} deliveries", [
				r.heats,
				r.lots,
				r.deliveries,
			])}
			· ${__("{0} s", [r.seconds.toFixed(2)])}</span></div>`;
		if (this.view === "table") {
			this.$body.html(header + this.table_html(r));
			return;
		}
		const columns = r.columns
			.map((c) => {
				const nodes = c.nodes.length
					? c.nodes.map((n) => this.node_html(n)).join("")
					: `<div class="pvfss-trace-node pvfss-trace-missing">${__("No {0} found", [
							__(c.stage),
					  ])}</div>`;
				return `<div class="pvfss-trace-col"><div class="pvfss-trace-stage">${__(
					c.stage
				)}</div>${nodes}</div>`;
			})
			.join("");
		this.$body.html(`${header}<div class="pvfss-trace-chain">${columns}</div>`);
	}

	node_html(n) {
		const esc = frappe.utils.escape_html;
		const facts = Object.entries(n.facts || {})
			.filter(([, v]) => v !== null && v !== undefined && v !== "")
			.map(
				([k, v]) => `<div class="small text-muted">${esc(__(k))}: ${esc(String(v))}</div>`
			)
			.join("");
		const route = n.doctype === "Warehouse" ? "warehouse" : frappe.router.slug(n.doctype);
		const pill = n.status
			? `<span class="indicator-pill ${this.colour(n.status)}">${esc(__(n.status))}</span>`
			: "";
		return `<div class="pvfss-trace-node">
			<a class="pvfss-mono" href="/app/${route}/${encodeURIComponent(n.name)}">${esc(
			n.label || n.name
		)}</a> ${pill}
			${facts}</div>`;
	}

	colour(status) {
		return (
			{
				Active: "green",
				"On hold": "orange",
				Rejected: "red",
				Completed: "green",
				Cancelled: "red",
			}[status] || "blue"
		);
	}

	table_html(r) {
		const esc = frappe.utils.escape_html;
		const cols = [
			"heat",
			"lot",
			"mtc",
			"mtc_date",
			"delivery",
			"customer",
			"customer_po",
			"invoice",
			"qty",
		];
		const labels = [
			__("Heat"),
			__("Lot"),
			__("MTC"),
			__("MTC date"),
			__("Delivery Note"),
			__("Customer"),
			__("Customer PO"),
			__("Invoice"),
			__("Qty"),
		];
		const rows = r.table
			.map(
				(row) =>
					`<tr>${cols
						.map((c) => `<td>${esc(row[c] == null ? "" : String(row[c]))}</td>`)
						.join("")}</tr>`
			)
			.join("");
		return `<table class="table table-bordered table-sm"><thead><tr>${labels
			.map((l) => `<th>${l}</th>`)
			.join("")}</tr></thead><tbody>${rows}</tbody></table>`;
	}

	toggle_view() {
		this.view = this.view === "chain" ? "table" : "chain";
		if (this.result) this.render();
	}

	download(method) {
		const args = this.args();
		if (!args.key) return;
		const query = new URLSearchParams({ ...args, direction: args.direction || "" }).toString();
		window.open(`/api/method/pvfss.pvfss_quality.traceability.${method}?${query}`);
	}

	copy_link() {
		const args = this.args();
		const url = `${window.location.origin}/app/heat-trace?${new URLSearchParams({
			type: args.search_type,
			key: args.key || "",
		}).toString()}`;
		frappe.utils.copy_to_clipboard(url);
	}
};
