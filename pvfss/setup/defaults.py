"""Default values seeded on install (requirements GEN-30, screens SCR-GEN-04).

These are starting values. PVFSS confirms them in week 1 and changes them in PVFSS Settings;
install and migrate never overwrite a table that already has rows.
"""

SYSTEM_SETTINGS = {
	"enable_two_factor_auth": 1,  # GEN-63
	"two_factor_method": "OTP App",
	"otp_issuer_name": "PVFSS ERP",
	"enable_password_policy": 1,  # NFR-04
	"minimum_password_score": "3",
	"session_expiry": "08:00",
	"login_with_email_link": 0,  # password + 2FA only (SCR-GEN-01)  # 8-hour idle session expiry (NFR-04)
}

# Minimum password length (NFR-04). Checked on User save by pvfss.overrides.user.before_validate.
MIN_PASSWORD_LENGTH = 10

SUPPLIER_EVALUATION_CRITERIA = [
	# SUP-05: criteria from the PVFSS workflow document. Weights total 100.
	("Price", 15),
	("Technical compliance", 15),
	("Approval status", 10),
	("Capability", 10),
	("Lead time / on-time delivery", 15),
	("Quality documents and traceability", 10),
	("Inspection readiness", 10),
	("Responsiveness", 5),
	("Commercial terms", 10),
]

HANDOVER_ITEMS = [
	# PRJ-02: (item, mandatory, backed by DocType)
	("Customer PO", 1, "Sales Order"),
	("Supplier PO", 1, "Purchase Order"),
	("Handover Checklist", 1, None),
	("Original inquiry folder", 1, "Opportunity"),
	("Technical Requirements File", 0, None),
	("Commercial offer", 1, "Quotation"),
	("Supplier quotations and comparison", 1, "Supplier Quotation"),
	("Technical evaluation", 1, "Technical Evaluation"),
	("Payment documents (proforma for LC)", 0, None),
	("Inspection and quality requirements", 1, None),
]

PO_REVIEW_ITEMS = [
	# SQ-08
	"Scope matches quotation",
	"Quantities",
	"Specification",
	"Price",
	"Delivery date and terms",
	"Payment terms",
	"Documents required",
	"Inspection requirements (ITP / TPI)",
	"Retention / warranty / LDs",
	"Incoterm and delivery point",
]

DISPATCH_DOCUMENTS = [
	# DSP-03: (delivery mode, document, required)
	("All", "Packing List", 1),
	("All", "Commercial Invoice", 1),
	("All", "IRN / MPQT documentation", 1),
	("All", "MTCs", 1),
	("Sea", "Certificate of Origin", 1),
	("Sea", "Bill of Lading", 1),
	("Air", "Certificate of Origin", 1),
	("Air", "Air Waybill", 1),
	("Road", "Delivery Note (signed)", 1),
]

MANUFACTURING_MILESTONES = [
	# PRJ-20
	"Drawing / document submission",
	"Customer approval",
	"Raw material",
	"Manufacturing start",
	"Manufacturing complete",
	"Inspection",
	"Ready for dispatch",
	"Shipped",
	"Delivered",
]

SMR_MILESTONES = [
	"Inspection",
	"Ready for dispatch",
	"Shipped",
	"Delivered",
]

CLOSURE_ITEMS = [
	# PRJ-40
	"All lines delivered",
	"All POD received",
	"All invoices raised",
	"Customer payment received (except retention)",
	"Supplier invoices settled",
	"NCRs closed",
	"Documents handed over (MDR / final dossier)",
	"Retention release dates recorded",
]

LC_EXPIRY_ALERT_DAYS = [30, 15, 7]  # FIN-41
ICV_EXPIRY_ALERT_DAYS = [90, 30]  # ICV-11

# PUR-12 / FIN-20: Purchase Order and Receipt before Invoice, no over-billing or over-receipt
# (the 3-way match). Applied on install only, so later changes on the site are kept.
OPERATING_SETTINGS = {
	"Buying Settings": {"po_required": "Yes", "pr_required": "Yes"},
	"Accounts Settings": {"over_billing_allowance": 0},
	# TRC-01 / TRC-02: heat traceability runs on batches
	"Stock Settings": {"over_delivery_receipt_allowance": 0, "enable_serial_and_batch_no_for_item": 1},
}

SETTINGS_TABLES = {
	"lc_expiry_alert_days": [{"days_before": d} for d in LC_EXPIRY_ALERT_DAYS],
	"icv_expiry_alert_days": [{"days_before": d} for d in ICV_EXPIRY_ALERT_DAYS],
	"supplier_evaluation_criteria": [
		{"criterion": c, "weight_pct": w} for c, w in SUPPLIER_EVALUATION_CRITERIA
	],
	"handover_item_template": [
		{"item": i, "mandatory": m, "backed_by_doctype": d} for i, m, d in HANDOVER_ITEMS
	],
	"po_review_template": [{"check_item": c} for c in PO_REVIEW_ITEMS],
	"dispatch_document_template": [
		{"delivery_mode": m, "document": d, "required": r} for m, d, r in DISPATCH_DOCUMENTS
	],
	"expediting_milestone_template": [
		{"supply_route": "Manufacturing", "milestone": m, "sequence": i}
		for i, m in enumerate(MANUFACTURING_MILESTONES, 1)
	]
	+ [
		{"supply_route": "Ready stock (SMR)", "milestone": m, "sequence": i}
		for i, m in enumerate(SMR_MILESTONES, 1)
	],
	"project_closure_template": [{"item": i} for i in CLOSURE_ITEMS],
}
