// Shared PVFSS client utilities, loaded on every desk page (hooks.app_include_js).

frappe.provide("pvfss.gate");

/**
 * Render a gate check result (GateResult.as_dict on the server) as a live panel.
 * Used by forms that show a gate checklist before submit, e.g. the IRN gate check
 * panel (SCR-QA-19) and the PO compliance table (SCR-PUR-02).
 *
 * @param {HTMLElement|jQuery} wrapper  element to render into
 * @param {Object} result               { title, ok, failures: [{message, url, rule}], passes: [...] }
 */
pvfss.gate.render_panel = function (wrapper, result) {
	const $wrapper = $(wrapper).empty();
	if (!result) return;

	const esc = frappe.utils.escape_html;
	const row = (item, ok) => {
		const icon = ok ? "✓" : "✕";
		const color = ok ? "var(--green-600)" : "var(--red-600)";
		const link = item.url ? ` <a href="${esc(item.url)}">${__("Open")}</a>` : "";
		const rule = item.rule ? ` <span class="text-muted small">(${esc(item.rule)})</span>` : "";
		return `<li style="list-style:none;margin:2px 0">
			<span style="color:${color};font-weight:600">${icon}</span> ${esc(item.message)}${link}${rule}
		</li>`;
	};

	const indicator = result.ok ? "green" : "red";
	const heading = result.ok ? __("All gate checks pass") : esc(result.title);
	$wrapper.html(`
		<div class="pvfss-gate-panel">
			<div class="indicator-pill ${indicator}" style="margin-bottom:8px">${heading}</div>
			<ul style="padding-left:0;margin:0">
				${(result.failures || []).map((f) => row(f, false)).join("")}
				${(result.passes || []).map((p) => row(p, true)).join("")}
			</ul>
		</div>`);
};

/**
 * Call a whitelisted gate "check" endpoint and render the result into a form HTML field.
 */
pvfss.gate.refresh_panel = function (frm, method, html_fieldname) {
	if (frm.is_new()) return Promise.resolve();
	return frappe.xcall(method, { doctype: frm.doctype, name: frm.doc.name }).then((result) => {
		pvfss.gate.render_panel(frm.fields_dict[html_fieldname].$wrapper, result);
		return result;
	});
};

// ---------------------------------------------------------------------------- CRM (04-crm)
frappe.provide("pvfss.crm");

pvfss.crm.STAGES = [
	"New",
	"RFQ Sent",
	"Quotes Received",
	"Under Evaluation",
	"Quoted",
	"Won",
	"Lost",
	"No Bid",
	"Cancelled",
];

// screens SCR-CRM-01 stage colours
pvfss.crm.STAGE_COLOURS = {
	New: "blue",
	"RFQ Sent": "blue",
	"Quotes Received": "blue",
	"Under Evaluation": "orange",
	Quoted: "orange",
	Won: "green",
	Lost: "red",
	"No Bid": "gray",
	Cancelled: "gray",
};

pvfss.crm.CLOSED = ["Won", "Lost", "No Bid", "Cancelled"];
