import streamlit as st
from supabase import create_client
import pandas as pd

# ===== CONNECT SUPABASE =====
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

st.set_page_config(page_title="Kanban Scan", layout="centered")
st.title("📦 Kanban Scan Confirm")

# ===== SCAN FUNCTION =====
def process_scan():
    kb = st.session_state.scan.strip()
    if kb == "":
        return

    # หา Kanban
    master = supabase.table("master_kanban") \
        .select("*") \
        .eq("kanban_no", kb) \
        .execute()

    if not master.data:
        st.session_state.error = "❌ ไม่พบ Kanban นี้"
        st.session_state.scan = ""
        return

    mk = master.data[0]

    # นับจำนวนที่ส่งแล้ว
    used = supabase.table("delivery_confirm") \
        .select("id", count="exact") \
        .eq("kanban_no", kb) \
        .execute() \
        .count

    # เช็คว่าส่งครบหรือยัง
    if used >= mk["std_qty"]:
        st.session_state.error = "❌ Kanban นี้ส่งครบแล้ว"
        st.session_state.scan = ""
        return

    # บันทึกการ Scan
    supabase.table("delivery_confirm").insert({
        "kanban_no": kb,
        "part_no": mk["part_no"],
        "harness_group": mk["harness_group"]
    }).execute()

    remaining = mk["std_qty"] - (used + 1)
    st.session_state.success = (
        f"KANBAN : {kb}\n"
        f"{mk['harness_group']}\n"
        f"ส่งแล้ว {used + 1} เหลือ {remaining}"
    )

    st.session_state.last_kanban = kb
    st.session_state.scan = ""

# ===== SCAN INPUT =====
st.text_input(
    "Scan Kanban No.",
    key="scan",
    on_change=process_scan
)

# ===== MESSAGE =====
if "error" in st.session_state:
    st.error(st.session_state.error)
    del st.session_state.error

if "success" in st.session_state:
    st.success(st.session_state.success)

st.divider()

# ===== TRACKING TABLE =====
if "last_kanban" in st.session_state:
    kb = st.session_state.last_kanban

    track = supabase.table("delivery_confirm") \
        .select("scan_time") \
        .eq("kanban_no", kb) \
        .order("scan_time") \
        .execute()

    if track.data:
        df = pd.DataFrame(track.data)
        st.subheader("📊 Tracking History")
        st.dataframe(df, use_container_width=True)
