import streamlit as st
from supabase import create_client
import pandas as pd

# ==================================================
# CONFIG
# ==================================================
st.set_page_config(page_title="Kanban Delivery Tracking", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📦 Kanban Delivery – Joint A+B System")

# ==================================================
# SIDEBAR
# ==================================================
mode = st.sidebar.radio(
    "📌 เลือกโหมด",
    [
        "✅ Scan Kanban",
        "📊 Model Kanban Status",
        "🔍 Tracking Search",
        "🔐📤 Upload Lot Master"
    ]
)

# ==================================================
# 1) SCAN KANBAN
# ==================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan / Confirm Kanban (Joint A+B)")

    def confirm_kanban():
        kanban = st.session_state.scan.strip()
        if not kanban:
            return

        lot = (
            supabase.table("lot_master")
            .select("kanban_no, model_name")
            .eq("kanban_no", kanban)
            .execute()
        )

        if not lot.data:
            st.error("❌ ไม่พบ Kanban ใน Lot Master")
            st.session_state.scan = ""
            return

        exist = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .eq("kanban_no", kanban)
            .execute()
        )

        if exist.data:
            st.warning("⚠️ Kanban นี้ Confirm แล้ว")
            st.session_state.scan = ""
            return

        supabase.table("kanban_delivery").insert({
            "kanban_no": kanban,
            "model_name": lot.data[0]["model_name"]
        }).execute()

        st.success(f"✅ Confirm Kanban {kanban} (A+B)")
        st.session_state.scan = ""

    st.text_input("📥 Scan Kanban No.", key="scan", on_change=confirm_kanban)

# ==================================================
# 2) MODEL KANBAN STATUS  (🔥 FIXED)
# ==================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model / Lot Status")

    model_filter = st.text_input("ค้นหา Model")
    lot_filter = st.text_input("ค้นหา Lot")

    query = supabase.table("lot_master").select(
        "model_name, lot_no, kanban_no"
    )

    if model_filter:
        query = query.ilike("model_name", f"%{model_filter}%")
    if lot_filter:
        query = query.eq("lot_no", lot_filter)

    lot_data = query.execute().data
    if not lot_data:
        st.warning("ไม่พบข้อมูล")
        st.stop()

    lot_df = pd.DataFrame(lot_data)

    # ===== DELIVERY TABLE (SAFE) =====
    delivery_data = supabase.table("kanban_delivery").select(
        "kanban_no"
    ).execute().data

    del_df = pd.DataFrame(delivery_data)

    # 🔥 CRITICAL FIX
    if del_df.empty:
        del_df = pd.DataFrame(columns=["kanban_no", "sent"])
    else:
        del_df["sent"] = 1

    # ===== MERGE SAFE =====
    df = lot_df.merge(del_df, on="kanban_no", how="left")
    df["sent"] = df["sent"].fillna(0)

    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(
            Total_Kanban=("kanban_no", "count"),
            Confirmed=("sent", "sum")
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total_Kanban"] - summary["Confirmed"]

    st.dataframe(summary, use_container_width=True)

# ==================================================
# 3) TRACKING SEARCH (SAFE)
# ==================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    kanban = st.text_input("Kanban No.")
    model = st.text_input("Model")
    lot = st.text_input("Lot")

    query = supabase.table("lot_master").select(
        """
        kanban_no,
        model_name,
        lot_no,
        joint_a,
        joint_b,
        wire_number,
        wire_harness_code
        """
    )

    if kanban:
        query = query.eq("kanban_no", kanban)
    if model:
        query = query.ilike("model_name", f"%{model}%")
    if lot:
        query = query.eq("lot_no", lot)

    lot_df = pd.DataFrame(query.execute().data)

    del_data = supabase.table("kanban_delivery").select(
        "kanban_no, confirmed_at"
    ).execute().data

    del_df = pd.DataFrame(del_data)

    if del_df.empty:
        del_df = pd.DataFrame(columns=["kanban_no", "confirmed_at"])

    df = lot_df.merge(del_df, on="kanban_no", how="left")

    st.dataframe(df, use_container_width=True)

# ==================================================
# 4) UPLOAD LOT MASTER
# ==================================================
elif mode == "🔐📤 Upload Lot Master":

    st.header("🔐 Upload Lot Master")

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("เฉพาะ Planner")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx"])

    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)

        required_cols = {
            "lot_no",
            "kanban_no",
            "model_name",
            "joint_a",
            "joint_b",
            "model_joint_key",
            "wire_number",
            "subpackage_number",
            "wire_harness_code"
        }

        if not required_cols.issubset(df.columns):
            st.error(f"❌ ต้องมี column: {', '.join(required_cols)}")
            st.stop()

        st.dataframe(df.head(), use_container_width=True)

        if st.button("🚀 Upload"):
            supabase.table("lot_master").upsert(
                df[list(required_cols)].to_dict("records")
            ).execute()

            st.success(f"✅ Upload {len(df)} records")
