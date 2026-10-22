"""Business details and settings. Edit this file to change what appears on invoices."""

COMPANY = {
    "name": "A2KT PLASTIC INDUSTRIES",
    "gstin": "09AZKPT3192M1ZH",
    "phone": "8368709038",
    "address": (
        "1st Floor, J-81, UPSIDC Site C, Surajpur Industrial Area, Surajpur, "
        "Greater Noida, Gautam Buddha Nagar, Uttar Pradesh - 201306"
    ),
    # Prefix used in invoice numbers, e.g. A2KT/2026-27/0001
    "invoice_prefix": "A2KT",
}

# Optional. Leave a value empty ("") to hide that line on the invoice.
BANK = {
    "account_name": "",
    "bank_name": "",
    "account_no": "",
    "ifsc": "",
}

TERMS = [
    "Goods once sold will not be taken back or exchanged.",
    "All disputes are subject to Noida jurisdiction only.",
    "Freight charges extra.",
    "GST extra as applicable.",
]

GST_RATES = [0, 5, 12, 18, 28]
DEFAULT_GST_RATE = 18
