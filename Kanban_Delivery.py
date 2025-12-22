import streamlit as st
from supabase import create_client
import pandas as pd

# ===============================
# CONFIG
# ===============================
st.set_page_config(page_title="Kanban Delivery Tracking", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📦 Kanban Delivery - MIND Automotive Parts")

# ===============================
# SIDEBAR MENU
# ===============================
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
# 1) SCAN / CONFIRM KANBAN
# ==================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan / Confirm Kanban")

    def confirm_kanban():
        kanban = st.session_state.scan.strip()
        if not kanban:
            return

        # ตรวจใน lot_master
        lot = (
            supabase.table("lot_master")
            .select("kanban_no, model_name")
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
        )

        if not lot.data:
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban นี้ใน Lot Master")
            st.session_state.scan = ""
            return

        model = lot.data[0]["model_name"]

        # ตรวจซ้ำ
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

        # INSERT
        supabase.table("kanban_delivery").insert({
            "kanban_no": kanban,
            "model_name": model
        }).execute()

        st.session_state.msg = ("success", f"✅ ส่ง Kanban {kanban} | Model {model}")
        st.session_state.scan = ""

    st.text_input("Scan Kanban No.", key="scan", on_change=confirm_kanban)

    if "msg" in st.session_state:
        t, m = st.session_state.msg
        if t == "success":
            st.success(m)
        elif t == "warning":
            st.warning(m)
        else:
            st.error(m)
        del st.session_state.msg

# ==================================================
# 2) MODEL + LOT STATUS
# ==================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    col1, col2 = st.columns(2)
    model_filter = col1.text_input("ค้นหา Model")
    lot_filter = col2.text_input("ค้นหา Lot")

    lot_df = pd.DataFrame(
        supabase.table("lot_master")
        .select("kanban_no, model_name, lot_no")
        .execute()
        .data
    )

    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data
    )

    if lot_df.empty:
        st.info("ยังไม่มีข้อมูล Lot Master")
        st.stop()

    if model_filter:
        lot_df = lot_df[lot_df["model_name"].str.contains(model_filter, case=False, na=False)]

    if lot_filter:
        lot_df = lot_df[lot_df["lot_no"].astype(str).str.contains(lot_filter, na=False)]

    lot_df["sent"] = lot_df["kanban_no"].isin(
        del_df["kanban_no"] if not del_df.empty else []
    ).astype(int)

    summary = (
        lot_df.groupby(["model_name", "lot_no"])
        .agg(
            Total_Kanban=("kanban_no", "nunique"),
            Sent=("sent", "sum")
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total_Kanban"] - summary["Sent"]

    summary.rename(columns={
        "model_name": "Model",
        "lot_no": "Lot"
    }, inplace=True)

    st.dataframe(summary, use_container_width=True)

# ==================================================
# 3) TRACKING SEARCH
# ==================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    col1, col2, col3, col4, col5 = st.columns(5)

    model = col1.text_input("Model")
    wire = col2.text_input("Wire number")
    subpackage = col3.text_input("Subpackage")
    harness = col4.text_input("Wire Harness Code")
    lot = col5.text_input("Lot")

    query = supabase.table("lot_master").select(
        """
        kanban_no,
        model_name,
        wire_number,
        subpackage_number,
        wire_harness_code,
        lot_no
        """
    )

    if model:
        query = query.ilike("model_name", f"%{model}%")
    if wire:
        query = query.ilike("wire_number", f"%{wire}%")
    if subpackage:
        query = query.ilike("subpackage_number", f"%{subpackage}%")
    if harness:
        query = query.ilike("wire_harness_code", f"%{harness}%")
    if lot:
        query = query.ilike("lot_no", f"%{lot}%")

    lot_df = pd.DataFrame(query.execute().data)
    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at")
        .execute()
        .data
    )

    if lot_df.empty:
        st.info("ไม่พบข้อมูล")
        st.stop()

    df = lot_df.merge(del_df, on="kanban_no", how="left")

    df.rename(columns={
        "kanban_no": "Kanban no.",
        "model_name": "Model",
        "wire_number": "Wire number",
        "subpackage_number": "Subpackage number",
        "wire_harness_code": "Wire Harness Code",
        "lot_no": "Lot",
        "created_at": "Delivered at (GMT+7)"
    }, inplace=True)

    st.dataframe(df, use_container_width=True)

# ==================================================
# 4) UPLOAD LOT MASTER (PLANNER)
# ==================================================
elif mode == "🔐📤 Upload Lot Master":

    st.header("🔐 Upload Lot Master")

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("🔒 โหมดนี้สำหรับ Planner เท่านั้น")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx"])

    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)

        st.subheader("Preview")
        st.dataframe(df.head(), use_container_width=True)

        required_cols = {
            "lot_no",
            "kanban_no",
            "model_name",
            "wire_number",
            "subpackage_number",
            "wire_harness_code"
        }

        if not required_cols.issubset(df.columns):
            st.error(f"❌ ต้องมี column: {', '.join(required_cols)}")
            st.stop()

        if st.button("🚀 Upload to Supabase"):
            supabase.table("lot_master").upsert(
                df[list(required_cols)].dropna(subset=["kanban_no"]).to_dict("records")
            ).execute()

            st.success(f"✅ Upload สำเร็จ {len(df)} records")
