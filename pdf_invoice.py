"""Builds the invoice PDF (A4) in the A2KT layout."""
import io
import os
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer,
                                KeepTogether, HRFlowable)

import config
from gst_utils import calculate, inr, amount_in_words, state_label

_HERE = os.path.dirname(os.path.abspath(__file__))
pdfmetrics.registerFont(TTFont("Body", os.path.join(_HERE, "fonts", "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Body-Bold", os.path.join(_HERE, "fonts", "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold")

NAVY = colors.HexColor("#1F2A56")
GOLD = colors.HexColor("#C9A227")
CREAM = colors.HexColor("#F6EFE0")
GREY = colors.HexColor("#555555")


def S(name, size=8.5, bold=False, color=colors.HexColor("#222222"), align=TA_LEFT, leading=None, **kw):
    return ParagraphStyle(name, fontName="Body-Bold" if bold else "Body", fontSize=size,
                          leading=leading or size * 1.35, textColor=color, alignment=align, **kw)


def P(text, style):
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _qty(q):
    q = float(q)
    return str(int(q)) if q == int(q) else f"{q:g}"


def _fmt_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return date(y, m, d).strftime("%d/%m/%Y")


def build_pdf(inv: dict) -> bytes:
    calc = calculate(inv["items"], inv["gst_rate"], inv["intra_state"])
    cancelled = inv.get("status") == "cancelled"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Invoice {inv['invoice_no']}", author=config.COMPANY["name"])
    W = A4[0] - 30 * mm
    st_ = {
        "co": S("co", 17, True, NAVY, leading=21),
        "coline": S("coline", 8.5, color=NAVY),
        "coaddr": S("coaddr", 8, color=GREY),
        "title": S("title", 14, True, NAVY, TA_RIGHT),
        "label": S("label", 8.5, color=GREY),
        "meta": S("meta", 9, True, NAVY),
        "metar": S("metar", 9, True, NAVY, TA_RIGHT),
        "h": S("h", 10, True, NAVY),
        "b": S("b", 8.5),
        "bb": S("bb", 8.5, True),
        "th": S("th", 8, True, NAVY, TA_CENTER),
        "thl": S("thl", 8, True, NAVY, TA_LEFT),
        "thr": S("thr", 8, True, NAVY, TA_RIGHT),
        "c": S("c", 8.5, align=TA_CENTER),
        "r": S("r", 8.5, align=TA_RIGHT),
        "rb": S("rb", 8.5, True, align=TA_RIGHT),
        "small": S("small", 7.5, color=GREY),
        "tot": S("tot", 11, True, NAVY),
        "totr": S("totr", 11, True, NAVY, TA_RIGHT),
    }
    story = []

    # ---- header ----
    co = config.COMPANY
    left = [P(co["name"], st_["co"]), Spacer(1, 2),
            P(f"GSTIN: {co['gstin']}", S("g", 8.5, True, NAVY)),
            P(f"Phone: {co['phone']}", st_["coline"]),
            P(co["address"], st_["coaddr"])]
    head = Table([[left, P("TAX INVOICE", st_["title"])]], colWidths=[W * 0.7, W * 0.3])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [head, Spacer(1, 3), HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=4)]

    # ---- meta ----
    meta = Table([[Paragraph(f'<font color="#555555">Invoice No.:</font>  {escape(inv["invoice_no"])}', st_["meta"]),
                   Paragraph(f'<font color="#555555">Date:</font>  {_fmt_date(inv["date"])}', st_["metar"])]],
                 colWidths=[W * 0.6, W * 0.4])
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(meta)

    # ---- parties ----
    def party(title, p, show_pos=False):
        rows = [P(title, st_["h"]), Spacer(1, 2), P(p["name"], st_["bb"])]
        if p.get("address"):
            rows.append(P(p["address"], st_["b"]))
        if p.get("contact_person"):
            rows.append(P(f"Contact Person: {p['contact_person']}", st_["b"]))
        if p.get("mobile"):
            rows.append(P(f"Mobile: {p['mobile']}", st_["b"]))
        if p.get("email"):
            rows.append(P(f"Email: {p['email']}", st_["b"]))
        if p.get("gstin"):
            rows.append(Paragraph(f'<font color="#555555">GSTIN:</font> <b>{escape(p["gstin"])}</b>', st_["b"]))
        if show_pos:
            rows.append(Paragraph(f'<font color="#555555">Place of Supply:</font> '
                                  f'{escape(state_label(inv["place_of_supply"]))}', st_["b"]))
        return rows

    parties = Table([[party("Bill To", inv["bill_to"]), party("Ship To", inv["ship_to"], True)]],
                    colWidths=[W / 2, W / 2])
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, GOLD), ("LINEBELOW", (0, 0), (-1, 0), 0.8, GOLD),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, GOLD),
        ("LEFTPADDING", (0, 0), (0, 0), 2), ("LEFTPADDING", (1, 0), (1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [parties, Spacer(1, 10)]

    # ---- items ----
    cw = [9 * mm, 0, 19 * mm, 16 * mm, 24 * mm, 26 * mm, 22 * mm, 27 * mm]
    cw[1] = W - sum(cw)
    gst_head = f"GST {calc['gst_rate'].normalize():f}%"
    rows = [[P("No.", st_["th"]), P("Description of Goods", st_["thl"]), P("HSN Code", st_["th"]),
             P("Qty.", st_["th"]), P("Rate (₹)", st_["thr"]), P("Taxable Value (₹)", st_["thr"]),
             P(f"{gst_head} (₹)", st_["thr"]), P("Amount (₹)", st_["thr"])]]
    for i, ln in enumerate(calc["lines"], 1):
        rows.append([P(i, st_["c"]), P(ln["description"], st_["b"]), P(ln.get("hsn") or "-", st_["c"]),
                     P(f"{_qty(ln['qty'])} {ln.get('unit') or ''}".strip(), st_["c"]),
                     P(inr(ln["rate"], False), st_["r"]), P(inr(ln["taxable"], False), st_["r"]),
                     P(inr(ln["tax"], False), st_["r"]), P(inr(ln["amount"], False), st_["rb"])])
    items = Table(rows, colWidths=cw, repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), CREAM), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, GOLD), ("LINEBELOW", (0, -1), (-1, -1), 1.2, GOLD),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story += [items, Spacer(1, 8)]

    # ---- totals ----
    tl = []
    def trow(a, b, strong=False):
        tl.append([P(a, st_["tot"] if strong else st_["b"]), P(b, st_["totr"] if strong else st_["r"])])
    trow("Taxable Amount", inr(calc["taxable_total"]))
    rate_txt = f"{calc['gst_rate'].normalize():f}"
    if calc["intra_state"]:
        half = f"{(calc['gst_rate'] / 2).normalize():f}"
        trow(f"CGST @ {half}%", inr(calc["cgst"]))
        trow(f"SGST @ {half}%", inr(calc["sgst"]))
    else:
        trow(f"IGST @ {rate_txt}%", inr(calc["igst"]))
    if calc["round_off"] != 0:
        trow("Round off", inr(calc["round_off"]))
    strong_idx = len(tl)
    trow("Total Amount", inr(calc["total"]), True)
    received = float(inv.get("received") or 0)
    trow("Received Amount", inr(received))
    trow("Balance Due", inr(calc["total"] - __import__("decimal").Decimal(str(received))))
    totals = Table(tl, colWidths=[W * 0.22, W * 0.2])
    totals.setStyle(TableStyle([("LINEABOVE", (0, strong_idx), (-1, strong_idx), 0.8, GOLD),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    terms = [P("Terms & Conditions", st_["h"]), Spacer(1, 3)]
    for i, t in enumerate(config.TERMS, 1):
        terms.append(P(f"{i}.  {t}", S(f"t{i}", 8, leading=11)))
    bank = {k: v for k, v in config.BANK.items() if v}
    if bank:
        terms += [Spacer(1, 8), P("Bank Details", st_["h"]), Spacer(1, 3)]
        labels = {"account_name": "A/c Name", "bank_name": "Bank", "account_no": "A/c No.", "ifsc": "IFSC"}
        for k, v in bank.items():
            terms.append(P(f"{labels[k]}: {v}", S(f"bk{k}", 8, leading=11)))
    words = [Spacer(1, 6), P("Total Amount (in words)", st_["small"]),
             P(amount_in_words(calc["total"]), S("w", 9, True, NAVY))]
    right = [totals] + words
    bottom = Table([[terms, right]], colWidths=[W * 0.52, W * 0.48])
    bottom.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("LINEABOVE", (0, 0), (-1, 0), 1.2, GOLD),
                                ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    sign = Table([[P("", st_["b"]), [P(f"For {co['name']}", st_["bb"]), Spacer(1, 30),
                                     P("Authorised Signatory", st_["b"])]]], colWidths=[W * 0.6, W * 0.4])
    sign.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether([bottom, Spacer(1, 14), sign,
                               Spacer(1, 8), P("This is a computer generated invoice.", st_["small"])]))

    def watermark(canvas, _doc):
        if cancelled:
            canvas.saveState()
            canvas.setFont("Body-Bold", 80)
            canvas.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.18))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, "CANCELLED")
            canvas.restoreState()

    doc.build(story, onFirstPage=watermark, onLaterPages=watermark)
    return buf.getvalue()
