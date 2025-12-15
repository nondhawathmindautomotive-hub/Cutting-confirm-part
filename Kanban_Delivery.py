import streamlit as st
from supabase import create_client
import pandas as pd

# ===============================
# SUPABASE CONNECTION
# ===============================
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

st.set_page_config(page_title="Kanban Delivery Confirm", layout="centered")
st.title("📦 Kanban Scan Confirm (CUTTING ➜ ASSEMBLY)")

# ===============================
# PROCESS SCAN
# ===============================
def process_scan():
    kanban_no = st.session_state.scan.strip()
    if kanban_no == "":
        return

    # 1) ดึง Harness + STD จากไฟล์ Test Kanban (kanban_harness)
    kh = supabase.table("kanban_harness") \
        .select("harness_name, std_qty") \
        .eq("kanban_no", kanban_no) \
        .execute()

    if not kh.data:
        st.session_state.error = "❌ ไม่พบ Kanban นี้ใน Master"
        st.session_state.scan = ""
        return

    result = []

    for row in kh.data:
        harness = row["harness_name"]
        std_qty = row["std_qty"]

        # 2) นับจำนวนที่ส่งแล้ว
        sent = supabase.table("delivery_confirm") \
            .select("id", count="exact") \
            .eq("kanban_no", kanban_no) \
            .eq("harness_name", harness) \
            .execute() \
            .count

        # 3) Insert ถ้ายังไม่ครบ STD
        if sent < std_qty:
            supabase.table("delivery_confirm").insert({
                "kanban_no": kanban_no,
                "harness_name": harness
            }).execute()
            sent += 1

        remain = std_qty - sent

        result.append({
            "Harness": harness,
            "STD": std_qty,
            "ส่งแล้ว": sent,
            "คงเหลือ": remain
        })

    st.session_state.result = result
    st.session_state.last_kanban = kanban_no
    st.session_state.scan = ""

# ===============================
# SCAN INPUT
# ===============================
st.text_input(
    "Scan Kanban No. (Cutting)",
    key="scan",
    on_change=process_scan
)

# ===============================
# ERROR MESSAGE
# ===============================
if "error" in st.session_state:
    st.error(st.session_state.error)
    del st.session_state.error

# ===============================
# RESULT TABLE
# ===============================
if "result" in st.session_state:
    df = pd.DataFrame(st.session_state.result)
    st.subheader("📊 สถานะการส่ง (จาก Test Kanban)")
    st.dataframe(df, use_container_width=True)

st.divider()

# ===============================
# TRACKING HISTORY
# ===============================
if "last_kanban" in st.session_state:
    track = supabase.table("delivery_confirm") \
        .select("harness_name, scan_time") \
        .eq("kanban_no", st.session_state.last_kanban) \
        .order("scan_time") \
        .execute()

    if track.data:
        df2 = pd.DataFrame(track.data)
        st.subheader("🕒 Tracking History")
        st.dataframe(df2, use_container_width=True)
