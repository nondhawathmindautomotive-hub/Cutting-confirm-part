import streamlit as st
from supabase import create_client
import socket
from datetime import date
import pandas as pd

# ================= CONFIG =================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="QR Confirm Part", layout="centered")

# ================= UTILS =================
def get_device_name():
    return socket.gethostname()

# ================= SCAN PROCESS =================
def process_scan():
    scan_text = st.session_state.scan
    if not scan_text:
        return

    try:
        part_no, lot_no = scan_text.strip().split("|")
    except:
        st.session_state.msg = "❌ QR Format ผิด (PART|LOT)"
        st.session_state.ok = False
        return

    master = supabase.table("master_parts") \
        .select("*") \
        .eq("part_no", part_no) \
        .eq("active", True) \
        .execute()

    if not master.data:
        st.session_state.msg = "❌ Part ไม่อยู่ใน Standard"
        st.session_state.ok = False
        return

    try:
        supabase.table("delivery_confirm").insert({
            "part_no": part_no,
            "lot_no": lot_no,
            "process_from": master.data[0]["process_from"],
            "process_to": master.data[0]["process_to"],
            "scan_by": get_device_name()
        }).execute()

        st.session_state.msg = "✅ Confirm สำเร็จ"
        st.session_state.ok = True

    except:
        st.session_state.msg = "❌ LOT นี้ถูก Confirm แล้ว"
        st.session_state.ok = False

    st.session_state.scan = ""

# ================= UI =================
st.title("📦 QR Scan Confirm Part")

st.text_input(
    "Scan QR Code",
    key="scan",
    on_change=process_scan,
    placeholder="PARTNO|LOTNO",
)

if "msg" in st.session_state:
    if st.session_state.ok:
        st.success(st.session_state.msg)
    else:
        st.error(st.session_state.msg)

st.divider()

# ================= REPORT =================
st.subheader("📊 Report")

col1, col2 = st.columns(2)
with col1:
    report_date = st.date_input("Date", value=date.today())
with col2:
    lot_filter = st.text_input("Lot (optional)")

query = supabase.table("delivery_confirm").select("*") \
    .eq("scan_date", report_date)

if lot_filter:
    query = query.eq("lot_no", lot_filter)

res = query.execute()

if res.data:
    df = pd.DataFrame(res.data)
    st.dataframe(df)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Export CSV", csv, "confirm_report.csv")
else:
    st.info("No data")


