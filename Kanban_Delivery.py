import streamlit as st
from supabase import create_client
import pandas as pd

# ===============================
# CONNECT SUPABASE
# ===============================
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

st.set_page_config(page_title="Kanban Scan", layout="centered")
st.title("📦 Kanban Scan Confirm")

# ===============================
# FUNCTION : PROCESS SCAN
# ===============================
def process_scan():
    kanban = st.session_state.scan.strip()
    if kanban == "":
        return

    # ดึง Harness ของ Kanban นี้
    kh = supabase.table("kanban_harness") \
        .select("*") \
        .eq("kanban_no", kanban) \
        .execute()

    if not kh.data:
        st.session_state.error = "❌ ไม่พบ Kanban นี้"
        st.session_state.scan = ""
        return

    result = []

    for h in kh.data:
        harness = h["harness_name"]
        std = h["std_qty"]

        sent = supabase.table("delivery_confirm") \
            .select("id", count="exact") \
            .eq("kanban_no", kanban) \
            .eq("harness_name", harness) \
            .execute() \
            .count

        if sent < std:
            # บันทึกการส่ง 1 ชิ้น
            supabase.table("delivery_confirm").insert({
                "kanban_no": kanban,
                "harness_name": harness
            }).execute()

            sent += 1

        remain = std - sent

        result.append({
            "Harness": harness,
            "STD": std,
            "ส่งแล้ว": sent,
            "คงเหลือ": remain
        })

    st.session_state.result = result
    st.session_state.last_kanban = kanban
    st.session_state.scan = ""

# ===============================
# SCAN INPUT
# ===============================
st.text_input(
    "Scan Kanban No.",
    key="scan",
    on_change=process_scan
)

# ===============================
# MESSAGE
# ===============================
if "error" in st.session_state:
    st.error(st.session_state.error)
    del st.session_state.error

# ===============================
# RESULT TABLE
# ===============================
if "result" in st.session_state:
    df = pd.DataFrame(st.session_state.result)
    st.subheader("📊 สถานะการส่ง")
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
