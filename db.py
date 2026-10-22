"""MongoDB access. All database work lives here."""
from datetime import datetime, timezone

import certifi
import streamlit as st
from pymongo import MongoClient, ReturnDocument, ASCENDING, DESCENDING

DB_NAME = "invoice_app"


@st.cache_resource(show_spinner=False)
def _client(uri: str) -> MongoClient:
    # A free Atlas cluster may need a few seconds to wake up, so allow a generous timeout.
    return MongoClient(uri, serverSelectionTimeoutMS=20000, tlsCAFile=certifi.where())


def get_db():
    client = _client(st.secrets["MONGO_URI"])
    client.admin.command("ping")  # raises if unreachable
    return client[DB_NAME]


def ensure_indexes(db):
    db.invoices.create_index([("invoice_no", ASCENDING)], unique=True)
    db.invoices.create_index([("created_at", DESCENDING)])
    db.customers.create_index([("name", ASCENDING)])


# ---------- customers ----------
def list_customers(db):
    return list(db.customers.find().sort("name", ASCENDING))


def save_customer(db, data: dict, customer_id=None):
    data = {**data, "updated_at": datetime.now(timezone.utc)}
    if customer_id:
        db.customers.update_one({"_id": customer_id}, {"$set": data})
        return customer_id
    data["created_at"] = data["updated_at"]
    return db.customers.insert_one(data).inserted_id


def delete_customer(db, customer_id):
    db.customers.delete_one({"_id": customer_id})


# ---------- invoices ----------
def next_sequence(db, key: str) -> int:
    """Atomic counter: two saves can never get the same number."""
    doc = db.counters.find_one_and_update(
        {"_id": key}, {"$inc": {"seq": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return doc["seq"]


def save_invoice(db, invoice: dict):
    invoice = {**invoice, "created_at": datetime.now(timezone.utc), "status": "active"}
    invoice["_id"] = db.invoices.insert_one(invoice).inserted_id
    return invoice


def list_invoices(db, search: str = "", limit: int = 200):
    q = {}
    if search.strip():
        rx = {"$regex": search.strip(), "$options": "i"}
        q = {"$or": [{"invoice_no": rx}, {"bill_to.name": rx}]}
    return list(db.invoices.find(q).sort("created_at", DESCENDING).limit(limit))


def set_invoice_status(db, invoice_id, status: str):
    db.invoices.update_one({"_id": invoice_id}, {"$set": {"status": status}})


def create_invoice(db, invoice: dict, prefix: str, fy: str):
    """Give the invoice the next number for its financial year and save it."""
    from gst_utils import format_invoice_no

    seq = next_sequence(db, f"invoice-{fy}")
    invoice = {**invoice, "fy": fy, "seq": seq, "invoice_no": format_invoice_no(prefix, fy, seq)}
    return save_invoice(db, invoice)
