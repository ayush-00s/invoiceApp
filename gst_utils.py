"""GST helpers: state codes, GSTIN checks, tax calculation, amount in words, invoice numbers."""
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

STATES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman & Nicobar Islands", "36": "Telangana",
    "37": "Andhra Pradesh", "38": "Ladakh",
}

_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def clean_gstin(g: str) -> str:
    return (g or "").strip().upper().replace(" ", "")


def gstin_format_ok(g: str) -> bool:
    g = clean_gstin(g)
    return bool(_GSTIN_RE.match(g)) and g[:2] in STATES


def gstin_checksum_ok(g: str) -> bool:
    g = clean_gstin(g)
    if len(g) != 15:
        return False
    total = 0
    for i, ch in enumerate(g[:14]):
        if ch not in _CHARS:
            return False
        v = _CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return _CHARS[(36 - total % 36) % 36] == g[14]


def state_from_gstin(g: str):
    g = clean_gstin(g)
    return g[:2] if len(g) >= 2 and g[:2] in STATES else None


def state_label(code: str) -> str:
    return f"{STATES.get(code, 'Unknown')} ({code})"


# ---------- money ----------
def D(x) -> Decimal:
    return Decimal(str(x if x not in (None, "") else 0))


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate(items, gst_rate, intra_state: bool):
    """items: list of dicts with qty, rate. Returns totals (all Decimal, 2 places)."""
    rate = D(gst_rate)
    lines = []
    taxable_total = Decimal("0")
    tax_total = Decimal("0")
    for it in items:
        taxable = q2(D(it["qty"]) * D(it["rate"]))
        tax = q2(taxable * rate / 100)
        lines.append({**it, "taxable": taxable, "tax": tax, "amount": taxable + tax})
        taxable_total += taxable
        tax_total += tax
    grand = taxable_total + tax_total
    rounded = grand.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    out = {
        "lines": lines,
        "taxable_total": taxable_total,
        "tax_total": tax_total,
        "round_off": rounded - grand,
        "total": rounded,
        "gst_rate": rate,
        "intra_state": intra_state,
    }
    if intra_state:
        cgst = q2(tax_total / 2)
        out["cgst"], out["sgst"], out["igst"] = cgst, tax_total - cgst, Decimal("0")
    else:
        out["cgst"] = out["sgst"] = Decimal("0")
        out["igst"] = tax_total
    return out


def inr(x, symbol=True) -> str:
    """Indian digit grouping: 318600 -> 3,18,600.00"""
    x = q2(D(x))
    neg = x < 0
    s = f"{abs(x):.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = f"{whole}.{frac}"
    if neg:
        out = "-" + out
    return ("₹ " + out) if symbol else out


# ---------- amount in words (Indian system) ----------
_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
         "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_100(n):
    return _ONES[n] if n < 20 else _TENS[n // 10] + ((" " + _ONES[n % 10]) if n % 10 else "")


def _below_1000(n):
    if n >= 100:
        rest = _below_100(n % 100)
        return _ONES[n // 100] + " Hundred" + ((" " + rest) if rest else "")
    return _below_100(n)


def int_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for div, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")):
        if n >= div:
            chunk, n = divmod(n, div)
            parts.append(int_to_words(chunk) + " " + name)
    if n:
        parts.append(_below_1000(n))
    return " ".join(parts)


def amount_in_words(amount) -> str:
    amount = q2(D(amount))
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    s = f"{int_to_words(rupees)} Rupees"
    if paise:
        s += f" and {int_to_words(paise)} Paise"
    return s + " Only"


# ---------- invoice numbering ----------
def financial_year(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def format_invoice_no(prefix: str, fy: str, seq: int) -> str:
    return f"{prefix}/{fy}/{seq:04d}"
