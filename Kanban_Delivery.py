import streamlit as st
from supabase import create_client
import pandas as pd

# ===============================
# CONFIG
# ===============================
st.set_page_config(
    page_title="Kanban Delivery Tracking",
    layout="wide"
)

# ===============================
# SUPABASE CONNECTION
# ===============================
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

st.title("📦 Kanban Delivery Tracking (GMT+7)")

# ===============================
# SCAN CONFIRM SECTION
# ===============================
st.header("✅ Scan / Confirm Kanban")

def confirm_kanban():
    kanban = st.session_state.kanban_scan.strip()
    if kanban == "":
        return

    # ดึงข้อมูลจาก lot_master
    lot = supabase.table("lot_master") \
        .select("kanban_no, model_name") \
        .eq("kanban_no", kanban) \
        .limit(1) \
        .execute()

    if not lot.data:
        st.session_state.error = "❌ ไม่พบ Kanban นี้ใน Lot master"
        st.session_state.kanban_scan = ""
        return

    model = lot.data[0]["model_name"]

    # เช็คว่าส่งไปแล้วหรือยัง
    exist = supabase.table("kanban_delivery") \
        .select("id") \
        .eq("kanban_no", kanban) \
        .execute()

    if exist.data:
        st.session_state.error = "⚠️ Kanban นี้ถูกส่งไปแล้ว"
        st.session_state.kanban_scan = ""
        return

    # Insert (timestamp = GMT+7 จาก database)
    supabase.table("kanban_delivery").insert({
        "kanban_no": kanban,
        "model_name": model
    }).execute()

    st.session_state.success = f"✅ ส่ง Kanban {kanban} (Model {model}) เรียบร้อย"
    st.session_state.kanban_scan = ""

st.text_input(
    "Scan Kanban No.",
    key="kanban_scan",
    on_change=confirm_kanban
)

if "error" in st.session_state:
    st.error(st.session_state.error)
    del st.session_state.error

if "success" in st.session_state:
    st.success(st.session_state.success)
    del st.session_state.success

st.divider()

# ===============================
# MODEL STATUS SUMMARY
# ===============================
st.header("📊 Model Kanban Status")

status = supabase.rpc("model_kanban_status").execute()

if status.data:
    df_status = pd.DataFrame(status.data)
    st.dataframe(df_status, use_container_width=True)
else:
    st.info("ยังไม่มีข้อมูลสรุป")

st.divider()

# ===============================
# TRACKING SEARCH
# ===============================
st.header("🔍 Tracking Search")

col1, col2 = st.columns(2)

with col1:
    model_search = st.text_input("ค้นหาด้วย Model name")

with col2:
    wire_search = st.text_input("ค้นหาด้วย Wire number")

query = supabase.table("lot_master") \
    .select("""
        kanban_no,
        model_name,
        wire_number,
        kanban_delivery(delivered_at)
    """, count="exact")

if model_search:
    query = query.ilike("model_name", f"%{model_search}%")

if wire_search:
    query = query.ilike("wire_number", f"%{wire_search}%")

result = query.execute()

if result.data:
    rows = []
    for r in result.data:
        rows.append({
            "Kanban no.": r["kanban_no"],
            "Model": r["model_name"],
            "Wire number": r["wire_number"],
            "Delivered at (GMT+7)": (
                r["kanban_delivery"][0]["delivered_at"]
                if r.get("kanban_delivery") else None
            )
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("ไม่พบข้อมูล")
