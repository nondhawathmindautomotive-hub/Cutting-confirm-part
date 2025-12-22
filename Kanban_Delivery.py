import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime

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
# 1) SCAN / CONFIRM KANBAN (JOINT LOGIC)
# ==================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan / Confirm Kanban (Joint A/B Supported)")

    scan_location = st.text_input("📍 Scan Location")

    def confirm_kanban():
        kanban = st.session_state.scan.strip()
        if not kanban:
            return

        if not scan_location:
            st.session_state.msg = ("error", "❌ กรุณา Scan Location ก่อน")
            st.session_state.scan = ""
            return

        # ===============================
        # LOAD LOT MASTER (KANBAN)
        # ===============================
        lot = (
            supabase.table("lot_master")
            .select("kanban_no, model_name, model_joint_stock")
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
        )

        if not lot.data:
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban นี้ใน Lot Master")
            st.session_state.scan = ""
            return

        model = lot.data[0]["model_name"]
        joint_key = lot.data[0]["model_joint_stock"]

        # ===============================
        # CASE 1: NON-JOINT
        # ===============================
        if not joint_key:
            exist = (
                supabase.table("kanban_delivery")
                .select("kanban_no")
                .eq("kanban_no", kanban)
                .execute()
            )

            if exist.data:
                st.session_state.msg = ("warning", "⚠️ Kanban นี้ถูกส่งแล้ว")
                st.session_state.scan = ""
                return

            supabase.table("kanban_delivery").insert({
                "kanban_no": kanban,
                "model_name": model,
                "scan_location": scan_location
            }).execute()

            st.session_state.msg = ("success", f"✅ ส่ง Kanban {kanban} (Non-Joint)")
            st.session_state.scan = ""
            return

        # ===============================
        # CASE 2: JOINT → SEND ALL SET
        # ===============================
        # ดึง Kanban ทั้งชุด
        joint_kanbans = (
            supabase.table("lot_master")
            .select("kanban_no, model_name, model_joint_stock")
            .eq("model_joint_stock", joint_key)
            .execute()
            .data
        )

        if not joint_kanbans:
            st.session_state.msg = ("error", "❌ ไม่พบชุด Joint")
            st.session_state.scan = ""
            return

        # ดึง Kanban ที่ส่งแล้ว
        sent = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .in_("kanban_no", [k["kanban_no"] for k in joint_kanbans])
            .execute()
            .data
        )

        sent_set = {s["kanban_no"] for s in sent}

        to_insert = []
        for k in joint_kanbans:
            if k["kanban_no"] not in sent_set:
                to_insert.append({
                    "kanban_no": k["kanban_no"],
                    "model_name": k["model_name"],
                    "model_joint_stock": joint_key,
                    "scan_location": scan_location
                })

        if not to_insert:
            st.session_state.msg = ("warning", "⚠️ ชุดนี้ถูกส่งครบแล้ว")
            st.session_state.scan = ""
            return

        supabase.table("kanban_delivery").insert(to_insert).execute()

        st.session_state.msg = (
            "success",
            f"✅ ส่งทั้งชุด Joint ({joint_key}) จำนวน {len(to_insert)} Kanban"
        )
        st.session_state.scan = ""

    st.text_input("📦 Scan Kanban No.", key="scan", on_change=confirm_kanban)

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
# 2) MODEL + LOT STATUS (JOINT AWARE)
# ==================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status (Joint Aware)")

    col1, col2 = st.columns(2)
    model_filter = col1.text_input("ค้นหา Model")
    lot_filter = col2.text_input("ค้นหา Lot")

    lot_df = pd.DataFrame(
        supabase.table("lot_master")
        .select("model_name, lot_no, kanban_no, model_joint_stock")
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
        st.info("ไม่มีข้อมูล")
        st.stop()

    if model_filter:
        lot_df = lot_df[lot_df["model_name"].str.contains(model_filter, case=False)]

    if lot_filter:
        lot_df = lot_df[lot_df["lot_no"].astype(str).str.contains(lot_filter)]

    lot_df["sent"] = lot_df["kanban_no"].isin(del_df["kanban_no"]).astype(int)

    summary = (
        lot_df.groupby(["model_name", "lot_no", "model_joint_stock"], dropna=False)
        .agg(
            Total=("kanban_no", "count"),
            Sent=("sent", "sum")
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total"] - summary["Sent"]

    st.dataframe(summary, use_container_width=True)

# ==================================================
# 3) TRACKING SEARCH
# ==================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    col1, col2, col3 = st.columns(3)
    model = col1.text_input("Model")
    lot = col2.text_input("Lot")
    joint = col3.text_input("Joint")

    query = supabase.table("lot_master").select("*")

    if model:
        query = query.ilike("model_name", f"%{model}%")
    if lot:
        query = query.ilike("lot_no", f"%{lot}%")
    if joint:
        query = query.ilike("model_joint_stock", f"%{joint}%")

    lot_df = pd.DataFrame(query.execute().data)
    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, scan_location")
        .execute()
        .data
    )

    if lot_df.empty:
        st.info("ไม่พบข้อมูล")
        st.stop()

    df = lot_df.merge(del_df, on="kanban_no", how="left")
    st.dataframe(df, use_container_width=True)

# ==================================================
# 4) UPLOAD LOT MASTER
# ==================================================
elif mode == "🔐📤 Upload Lot Master":

    st.header("🔐 Upload Lot Master")

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("🔒 เฉพาะ Planner")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", type=["csv", "xlsx"])

    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
        st.dataframe(df.head())

        if st.button("🚀 Upload"):
            supabase.table("lot_master").upsert(df.to_dict("records")).execute()
            st.success("✅ Upload สำเร็จ")
