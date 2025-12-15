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
# SIDEBAR MENU
# ===============================
mode = st.sidebar.radio(
    "📌 เลือกโหมด",
    [
        "✅ Scan Kanban",
        "📊 Model Kanban Status",
        "🔍 Tracking Search",
        "🔐📤 Upload Lot Master (Planner)"
    ]
)

# ==================================================
# 1) SCAN KANBAN
# ==================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan / Confirm Kanban")

    def confirm_kanban():
        kanban = st.session_state.scan.strip()
        if kanban == "":
            return

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

        supabase.table("kanban_delivery").insert({
            "kanban_no": kanban,
            "model_name": model
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
        {"success": st.success, "warning": st.warning, "error": st.error}[t](m)
        del st.session_state.msg

# ==================================================
# 2) MODEL STATUS
# ==================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    lot_df = pd.DataFrame(
        supabase.table("lot_master")
        .select("model_name, kanban_no")
        .execute()
        .data
    )

    delivery_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data
    )

    if not lot_df.empty:
        total = lot_df.groupby("model_name")["kanban_no"].nunique()
        sent = (
            lot_df.merge(delivery_df, on="kanban_no", how="inner")
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
        st.info("ยังไม่มี Lot master")

elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    col1, col2, col3, col4 = st.columns(4)

    model = col1.text_input("Model name")
    wire = col2.text_input("Wire number")
    subpackage = col3.text_input("Subpackage number")
    lot = col4.text_input("Lot (เช่น 251201)")

    query = supabase.table("lot_master").select(
        "kanban_no, model_name, wire_number, subpackage_number"
    )

    if model:
        query = query.ilike("model_name", f"%{model}%")

    if wire:
        query = query.ilike("wire_number", f"%{wire}%")

    if subpackage:
        query = query.ilike("subpackage_number", f"%{subpackage}%")

    # 🔥 SEARCH BY LOT (kanban suffix)
    if lot:
        query = query.ilike("kanban_no", f"%-{lot}%")

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
            df = df_lot.merge(df_del, on="kanban_no", how="left")

            df.rename(columns={
                "kanban_no": "Kanban no.",
                "model_name": "Model",
                "wire_number": "Wire number",
                "subpackage_number": "Subpackage number",
                "delivered_at": "Delivered at (GMT+7)"
            }, inplace=True)

            st.dataframe(df, use_container_width=True)
        else:
            st.info("ไม่พบข้อมูล")

    except Exception as e:
        st.error("❌ Tracking error")
        st.exception(e)

# ==================================================
# 4) UPLOAD LOT MASTER (PLANNER)
# ==================================================
elif mode == "🔐📤 Upload Lot Master (Planner)":

    st.header("🔐 Upload Lot Master (Planner Only)")

    password = st.text_input("Planner Password", type="password")

    if password != "planner":
        st.warning("🔒 โหมดนี้สำหรับ Planner เท่านั้น")
        st.stop()

    st.success("✅ Authorized")

    file = st.file_uploader(
        "Upload Lot Master (CSV / Excel)",
        type=["csv", "xlsx"]
    )

    if file:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        st.subheader("📋 Preview")
        st.dataframe(df.head(), use_container_width=True)

        required_cols = {
            "kanban_no",
            "model_name",
            "wire_number",
            "subpackage_number"
        }

        if not required_cols.issubset(df.columns):
            st.error(f"❌ ต้องมี column: {', '.join(required_cols)}")
            st.stop()

        if st.button("🚀 Upload to Supabase"):
            data = df[list(required_cols)].dropna().to_dict("records")

            supabase.table("lot_master").insert(
                data,
                count="exact"
            ).execute()

            st.success(f"✅ Upload สำเร็จ {len(data)} records")
