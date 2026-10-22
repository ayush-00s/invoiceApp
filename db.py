"""MongoDB access. All database work lives here."""
from datetime import datetime, timezone

import certifi
import streamlit as st
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

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
    # An invoice number must be unique within a financial year (so "2" can be used again next year).
    if "invoice_no_1" in db.invoices.index_information():
        db.invoices.drop_index("invoice_no_1")  # old rule: unique across all years
    db.invoices.create_index([("fy", ASCENDING), ("invoice_no", ASCENDING)], unique=True)
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


def suggest_invoice_no(db, fy: str) -> str:
    """Next plain number for this financial year: highest number used so far + 1."""
    used = [int(d["invoice_no"]) for d in db.invoices.find({"fy": fy}, {"invoice_no": 1})
            if str(d["invoice_no"]).isdigit()]
    return str(max(used) + 1) if used else "1"


def create_invoice(db, invoice: dict, fy: str, invoice_no: str):
    """Save the invoice. Raises DuplicateKeyError if this number is already used in this financial year."""
    return save_invoice(db, {**invoice, "fy": fy, "invoice_no": invoice_no.strip()})