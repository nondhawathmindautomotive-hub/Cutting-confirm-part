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

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📦 Kanban Delivery Tracking (GMT+7)")

# ===============================
# SCAN / CONFIRM KANBAN
# ===============================
st.header("✅ Scan / Confirm Kanban")

def confirm_kanban():
    kanban = st.session_state.scan.strip()
    if kanban == "":
        return

    # ตรวจว่า Kanban มีอยู่ใน lot_master
    lot = (
        supabase.table("lot_master")
        .select("kanban_no, model_name")
        .eq("kanban_no", kanban)
        .limit(1)
        .execute()
    )

    if not lot.data:
        st.session_state.msg = ("error", "❌ ไม่พบ Kanban นี้ใน Lot master")
        st.session_state.scan = ""
        return

    model = lot.data[0]["model_name"]

    # ตรวจว่าเคยส่งแล้วหรือยัง
    exist = (
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .eq("kanban_no", kanban)
        .execute()
    )

    if exist.data:
        st.session_state.msg = ("warning", "⚠️ Kanban นี้ถูกส่งไปแล้ว")
        st.session_state.scan = ""
        return

    # Insert (ใช้เวลาจาก DB = GMT+7)
    supabase.table("kanban_delivery").insert({
        "kanban_no": kanban,
        "delivered_at": "now()"
    }).execute()

    st.session_state.msg = (
        "success",
        f"✅ ส่ง Kanban {kanban} (Model {model}) เรียบร้อย"
    )
    st.session_state.scan = ""

st.text_input(
    "Scan Kanban No.",
    key="scan",
    on_change=confirm_kanban
)

if "msg" in st.session_state:
    t, m = st.session_state.msg
    if t == "success":
        st.success(m)
    elif t == "warning":
        st.warning(m)
    else:
        st.error(m)
    del st.session_state.msg

st.divider()

# ===============================
# MODEL STATUS SUMMARY
# ===============================
st.header("📊 Model Kanban Status")

try:
    lot_data = (
        supabase.table("lot_master")
        .select("model_name, kanban_no")
        .execute()
        .data
    )

    delivery_data = (
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data
    )

    df_lot = pd.DataFrame(lot_data)
    df_del = pd.DataFrame(delivery_data)

    if not df_lot.empty:
        total = df_lot.groupby("model_name")["kanban_no"].nunique()

        sent = (
            df_lot.merge(df_del, on="kanban_no", how="inner")
            .groupby("model_name")["kanban_no"]
            .nunique()
        )

        summary = pd.DataFrame({
            "Total Kanban": total,
            "Sent": sent
        }).fillna(0)

        summary["Remaining"] = summary["Total Kanban"] - summary["Sent"]

        st.dataframe(summary.reset_index(), use_container_width=True)
    else:
        st.info("ยังไม่มีข้อมูล Lot master")

except Exception as e:
    st.error("❌ ไม่สามารถสรุป Model ได้")
    st.exception(e)

st.divider()

# ===============================
# TRACKING SEARCH
# ===============================
st.header("🔍 Tracking Search")

col1, col2 = st.columns(2)

model_search = col1.text_input("ค้นหาด้วย Model name")
wire_search = col2.text_input("ค้นหาด้วย Wire number")

query = supabase.table("lot_master").select(
    "kanban_no, model_name, wire_number"
)

if model_search:
    query = query.ilike("model_name", f"%{model_search}%")

if wire_search:
    query = query.ilike("wire_number", f"%{wire_search}%")

try:
    lot_data = query.execute().data
    delivery_data = (
        supabase.table("kanban_delivery")
        .select("kanban_no, delivered_at")
        .execute()
        .data
    )

    df_lot = pd.DataFrame(lot_data)
    df_del = pd.DataFrame(delivery_data)

    if not df_lot.empty:
        df = df_lot.merge(
            df_del,
            on="kanban_no",
            how="left"
        )

        df.rename(columns={
            "kanban_no": "Kanban no.",
            "model_name": "Model",
            "wire_number": "Wire number",
            "delivered_at": "Delivered at (GMT+7)"
        }, inplace=True)

        st.dataframe(df, use_container_width=True)
    else:
        st.info("ไม่พบข้อมูล")

except Exception as e:
    st.error("❌ Tracking error")
    st.exception(e)
