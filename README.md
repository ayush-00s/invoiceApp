# A2KT Billing App

A simple invoice maker: pick a customer, add items, press one button, download the PDF.

Files
- app.py            the screens
- db.py             database (MongoDB Atlas)
- gst_utils.py      GST maths, amount in words, GSTIN checks
- pdf_invoice.py    the invoice PDF layout
- config.py         company name, GSTIN, address, terms, bank details (edit here)
- fonts/            fonts used in the PDF (needed for the ₹ sign)

Secrets (set in Streamlit Cloud, never in GitHub):
    MONGO_URI    = "mongodb+srv://invoiceuser:PASSWORD@cluster0.7y0t3jn.mongodb.net/"
    APP_PASSWORD = "the password for your app"
