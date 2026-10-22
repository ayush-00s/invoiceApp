"""A2KT billing app (Streamlit). Run with: streamlit run app.py"""
import hmac
import time
from datetime import date, datetime
from decimal import Decimal

import streamlit as st

import config
import db as dbm
import gst_utils as g
from pdf_invoice import build_pdf

st.set_page_config(page_title="A2KT Billing", page_icon="🧾", layout="centered")

COMPANY_STATE = g.state_from_gstin(config.COMPANY["gstin"])
STATE_CODES = sorted(g.STATES)


# ------------------------------------------------------------------ login
def require_login():
    if "APP_PASSWORD" not in st.secrets or "MONGO_URI" not in st.secrets:
        st.error("The app is not set up yet: APP_PASSWORD and MONGO_URI are missing from Secrets.")
        st.stop()
    if st.session_state.get("auth"):
        return
    st.title("🧾 A2KT Billing")
    with st.form("login"):
        pw = st.text_input("Password", type="password")
        ok = st.form_submit_button("Log in", type="primary")
    if ok:
        if hmac.compare_digest(pw.encode(), str(st.secrets["APP_PASSWORD"]).encode()):
            st.session_state["auth"] = True
            st.rerun()
        time.sleep(1.5)  # slows down password guessing
        st.error("Wrong password.")
    st.stop()


def connect():
    try:
        db = dbm.get_db()
        if not st.session_state.get("indexes_ok"):
            dbm.ensure_indexes(db)
            st.session_state["indexes_ok"] = True
        return db
    except Exception:
        st.error(
            "Cannot connect to the database right now. Please wait a minute and press the button below. "
            "If it keeps failing, tell Ayush (the free database may need to be switched back on)."
        )
        if st.button("Try again"):
            st.rerun()
        st.stop()


# ------------------------------------------------------------------ helpers
def state_name(code):
    return g.state_label(code)


def customer_snapshot(c):
    return {k: c.get(k, "") for k in ("name", "address", "contact_person", "mobile", "email", "gstin", "state_code")}


def fmt_date(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d/%m/%Y")


# ------------------------------------------------------------------ customers tab
def customers_tab(db):
    customers = dbm.list_customers(db)
    NEW = "➕ Add a new customer"
    options = [NEW] + [str(c["_id"]) for c in customers]
    by_id = {str(c["_id"]): c for c in customers}
    choice = st.selectbox("Customer", options, format_func=lambda v: NEW if v == NEW else by_id[v]["name"],
                          key="cust_pick")
    cur = by_id.get(choice, {})
    k = choice  # widget keys include the customer id so the form refreshes when you switch

    with st.form(f"cust_form_{k}"):
        name = st.text_input("Company / customer name *", cur.get("name", ""))
        address = st.text_area("Address *", cur.get("address", ""), height=100)
        c1, c2 = st.columns(2)
        contact = c1.text_input("Contact person", cur.get("contact_person", ""))
        mobile = c2.text_input("Mobile", cur.get("mobile", ""))
        email = st.text_input("Email", cur.get("email", ""))
        gstin = st.text_input("GSTIN (leave empty if the customer has none)", cur.get("gstin", ""))
        AUTO = "Automatic (from GSTIN)"
        state_opts = [AUTO] + STATE_CODES
        default_idx = 0
        if cur.get("state_code") and not cur.get("gstin"):
            default_idx = state_opts.index(cur["state_code"])
        state_pick = st.selectbox("State (only needed if no GSTIN)", state_opts, index=default_idx,
                                  format_func=lambda v: v if v == AUTO else state_name(v))
        saved = st.form_submit_button("Save customer", type="primary")

    if saved:
        gstin = g.clean_gstin(gstin)
        errs = []
        if not name.strip():
            errs.append("Customer name is required.")
        if not address.strip():
            errs.append("Address is required.")
        state_code = None
        if gstin:
            if not g.gstin_format_ok(gstin):
                errs.append("GSTIN format is not correct. It must be 15 characters, e.g. 06ABEFB0483H1ZO.")
            elif not g.gstin_checksum_ok(gstin):
                errs.append("GSTIN looks mistyped (last character does not match). Please check every character.")
            else:
                state_code = g.state_from_gstin(gstin)
        else:
            state_code = None if state_pick == AUTO else state_pick
            if not state_code:
                errs.append("Please choose the customer's state (needed to decide IGST or CGST+SGST).")
        if errs:
            for e in errs:
                st.error(e)
        else:
            data = {"name": name.strip(), "address": address.strip(), "contact_person": contact.strip(),
                    "mobile": mobile.strip(), "email": email.strip(), "gstin": gstin, "state_code": state_code}
            dbm.save_customer(db, data, cur.get("_id"))
            st.success("Customer saved.")
            st.session_state.pop("cust_pick", None)
            time.sleep(0.6)
            st.rerun()

    if cur:
        with st.expander("Delete this customer"):
            st.caption("Old invoices are not affected. Their customer details stay saved on the invoice.")
            sure = st.checkbox("Yes, delete this customer", key=f"del_ok_{k}")
            if st.button("Delete customer", disabled=not sure):
                dbm.delete_customer(db, cur["_id"])
                st.session_state.pop("cust_pick", None)
                st.rerun()


# ------------------------------------------------------------------ new invoice tab
ITEM_KEYS = ("it_desc_", "it_hsn_", "it_qty_", "it_unit_", "it_rate_")


def reset_invoice_form():
    for key in list(st.session_state.keys()):
        if key.startswith(ITEM_KEYS) or key in ("n_items", "saved_invoice", "inv_customer", "diff_ship",
                                                "ship_name", "ship_addr", "ship_gstin", "ship_state",
                                                "gst_rate", "received"):
            st.session_state.pop(key, None)


def invoice_tab(db):
    saved = st.session_state.get("saved_invoice")
    if saved:
        st.success(f"Invoice {saved['invoice_no']} created and saved.")
        st.download_button("⬇️ Download invoice PDF", build_pdf(saved),
                           file_name=saved["invoice_no"].replace("/", "-") + ".pdf",
                           mime="application/pdf", type="primary", width="stretch")
        st.caption("You can find this invoice again anytime in the 'Past invoices' tab.")
        if st.button("➕ Make another invoice", width="stretch"):
            reset_invoice_form()
            st.rerun()
        return

    customers = dbm.list_customers(db)
    if not customers:
        st.info("Please add your first customer in the 'Customers' tab. Then come back here.")
        return
    by_id = {str(c["_id"]): c for c in customers}

    st.subheader("1. Customer")
    cid = st.selectbox("Who is this invoice for?", list(by_id), format_func=lambda v: by_id[v]["name"],
                       key="inv_customer")
    cust = by_id[cid]
    inv_date = st.date_input("Invoice date", value=date.today(), format="DD/MM/YYYY")
    st.caption(f"{cust['address']}  \nGSTIN: {cust.get('gstin') or '—'}  |  State: {state_name(cust['state_code'])}")

    diff = st.checkbox("Goods are being sent to a different address", key="diff_ship")
    if diff:
        ship = {
            "name": st.text_input("Ship-to name", cust["name"], key="ship_name"),
            "address": st.text_area("Ship-to address", cust["address"], key="ship_addr", height=90),
            "contact_person": cust.get("contact_person", ""), "mobile": cust.get("mobile", ""),
            "email": cust.get("email", ""),
            "gstin": g.clean_gstin(st.text_input("Ship-to GSTIN (optional)", key="ship_gstin")),
            "state_code": st.selectbox("Ship-to state", STATE_CODES, key="ship_state",
                                       index=STATE_CODES.index(cust["state_code"]), format_func=state_name),
        }
    else:
        ship = customer_snapshot(cust)
    place_of_supply = ship["state_code"]
    intra = place_of_supply == COMPANY_STATE
    if intra:
        st.info(f"Goods go to {state_name(place_of_supply)}, same state as you → **CGST + SGST** will be charged.")
    else:
        st.info(f"Goods go to {state_name(place_of_supply)}, a different state → **IGST** will be charged.")

    st.subheader("2. Items")
    if "n_items" not in st.session_state:
        st.session_state["n_items"] = 1
    n = st.session_state["n_items"]
    items, errors = [], []
    for i in range(n):
        with st.container(border=True):
            st.markdown(f"**Item {i + 1}**")
            desc = st.text_input("Description", key=f"it_desc_{i}", placeholder="e.g. Screw & Barrel with Bi-Metallic 50% GF")
            c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1.4])
            hsn = c1.text_input("HSN code", key=f"it_hsn_{i}", placeholder="e.g. 8477")
            qty = c2.number_input("Quantity", min_value=0.0, value=1.0, step=1.0, key=f"it_qty_{i}")
            unit = c3.text_input("Unit", value="pcs", key=f"it_unit_{i}")
            rate = c4.number_input("Rate (₹)", min_value=0.0, value=0.0, step=100.0, format="%.2f", key=f"it_rate_{i}")
            if desc.strip() or rate > 0:
                if not desc.strip():
                    errors.append(f"Item {i + 1}: please write the description.")
                elif rate <= 0:
                    errors.append(f"Item {i + 1}: please enter the rate.")
                elif qty <= 0:
                    errors.append(f"Item {i + 1}: quantity must be more than 0.")
                else:
                    items.append({"description": desc.strip(), "hsn": hsn.strip(), "qty": qty,
                                  "unit": unit.strip(), "rate": rate})
    b1, b2 = st.columns(2)
    if b1.button("➕ Add another item", width="stretch"):
        st.session_state["n_items"] = n + 1
        st.rerun()
    if n > 1 and b2.button("➖ Remove last item", width="stretch"):
        st.session_state["n_items"] = n - 1
        st.rerun()

    st.subheader("3. Tax and payment")
    c1, c2 = st.columns(2)
    gst_rate = c1.selectbox("GST rate", config.GST_RATES, key="gst_rate",
                            index=config.GST_RATES.index(config.DEFAULT_GST_RATE), format_func=lambda r: f"{r}%")
    received = c2.number_input("Amount received so far (₹)", min_value=0.0, value=0.0, step=1000.0,
                               format="%.2f", key="received")

    if not items and not errors:
        errors.append("Add at least one item (description and rate).")
    if any(not it["hsn"] for it in items):
        st.warning("HSN code is empty for some items. It is required on a GST tax invoice.")

    if items:
        calc = g.calculate(items, gst_rate, intra)
        if Decimal(str(received)) > calc["total"]:
            errors.append("Received amount is more than the invoice total.")
        st.subheader("4. Check and create")
        for ln in calc["lines"]:
            st.write(f"• {ln['description']} — {ln['qty']:g} {ln['unit']} × {g.inr(ln['rate'])} "
                     f"= **{g.inr(ln['taxable'])}**")
        st.write(f"Taxable amount: **{g.inr(calc['taxable_total'])}**")
        if intra:
            st.write(f"CGST {gst_rate / 2:g}%: {g.inr(calc['cgst'])}  |  SGST {gst_rate / 2:g}%: {g.inr(calc['sgst'])}")
        else:
            st.write(f"IGST {gst_rate}%: {g.inr(calc['igst'])}")
        if calc["round_off"] != 0:
            st.write(f"Round off: {g.inr(calc['round_off'])}")
        st.metric("Total amount", g.inr(calc["total"]))
        st.caption(g.amount_in_words(calc["total"]))

    for e in errors:
        st.error(e)

    if st.button("✅ Create invoice", type="primary", width="stretch", disabled=bool(errors)):
        invoice = {
            "date": inv_date.isoformat(),
            "bill_to": customer_snapshot(cust),
            "ship_to": ship,
            "place_of_supply": place_of_supply,
            "intra_state": intra,
            "gst_rate": gst_rate,
            "items": items,
            "received": float(received),
            "total": float(calc["total"]),
            "customer_id": cust["_id"],
        }
        try:
            doc = dbm.create_invoice(db, invoice, config.COMPANY["invoice_prefix"], g.financial_year(inv_date))
        except Exception:
            st.error("Could not save the invoice. Nothing was created. Please try again.")
            st.stop()
        st.session_state["saved_invoice"] = doc
        st.rerun()


# ------------------------------------------------------------------ past invoices tab
def history_tab(db):
    search = st.text_input("Search by invoice number or customer name")
    invoices = dbm.list_invoices(db, search)
    if not invoices:
        st.info("No invoices found.")
        return
    st.dataframe(
        [{"Invoice": i["invoice_no"], "Date": fmt_date(i["date"]), "Customer": i["bill_to"]["name"],
          "Total": g.inr(i["total"]), "Status": "Cancelled" if i.get("status") == "cancelled" else "OK"}
         for i in invoices],
        hide_index=True, width="stretch")
    by_id = {str(i["_id"]): i for i in invoices}
    pick = st.selectbox("Open an invoice", list(by_id),
                        format_func=lambda v: f"{by_id[v]['invoice_no']} — {by_id[v]['bill_to']['name']}")
    inv = by_id[pick]
    st.download_button("⬇️ Download PDF", build_pdf(inv), file_name=inv["invoice_no"].replace("/", "-") + ".pdf",
                       mime="application/pdf", type="primary", width="stretch")
    with st.expander("Cancel / restore this invoice"):
        if inv.get("status") == "cancelled":
            if st.button("Restore invoice"):
                dbm.set_invoice_status(db, inv["_id"], "active")
                st.rerun()
        else:
            st.caption("A cancelled invoice keeps its number and shows a CANCELLED stamp. "
                       "Numbers are never reused.")
            sure = st.checkbox("Yes, cancel this invoice", key=f"cancel_ok_{pick}")
            if st.button("Cancel invoice", disabled=not sure):
                dbm.set_invoice_status(db, inv["_id"], "cancelled")
                st.rerun()


# ------------------------------------------------------------------ main
require_login()
db = connect()
st.title("🧾 A2KT Billing")
with st.sidebar:
    if st.button("Log out"):
        st.session_state.clear()
        st.rerun()

t1, t2, t3 = st.tabs(["New invoice", "Customers", "Past invoices"])
with t1:
    invoice_tab(db)
with t2:
    customers_tab(db)
with t3:
    history_tab(db)
