from __future__ import annotations

LIFE_SECTORS: list[dict[str, str]] = [
    {"slug": "sales_income", "label": "Sales / Income"},
    {"slug": "inventory_parts", "label": "Inventory / Parts"},
    {"slug": "payroll_team", "label": "Payroll / Team"},
    {"slug": "rent_utilities", "label": "Rent / Utilities"},
    {"slug": "logistics_transport", "label": "Logistics / Transport"},
    {"slug": "marketing_growth", "label": "Marketing / Growth"},
    {"slug": "taxes_fees", "label": "Taxes / Fees"},
    {"slug": "tools_software", "label": "Tools / Software"},
    {"slug": "owner_draw", "label": "Owner Draw"},
    {"slug": "family_living", "label": "Family / Living"},
    {"slug": "savings_debt", "label": "Savings / Debt"},
]

LIFE_SECTOR_SLUGS = {item["slug"] for item in LIFE_SECTORS}
LIFE_SECTOR_LABELS = {item["slug"]: item["label"] for item in LIFE_SECTORS}

CLARIFICATION_BUTTON_CHOICES: list[tuple[str, str, str]] = [
    ("Sales / Income", "business", "sales_income"),
    ("Inventory / Parts", "business", "inventory_parts"),
    ("Rent / Utilities", "business", "rent_utilities"),
    ("Taxes / Fees", "business", "taxes_fees"),
    ("Family / Living", "personal", "family_living"),
    ("Savings / Debt", "personal", "savings_debt"),
    ("Owner Draw", "personal", "owner_draw"),
]
