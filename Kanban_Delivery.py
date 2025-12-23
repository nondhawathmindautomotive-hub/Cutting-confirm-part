import streamlit as st
from supabase import create_client
import pandas as pd

# ==================================================
# CONFIG
# ==================================================
st.set_page_config(
    page_title="Kanban Delivery System",
    layout="wide"
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("📦 Kanban Delivery System")
st.caption("Joint A + B | One Scan = One Set")

# ==================================================
# SIDEBAR
# ==================================================
mode = st.sidebar.radio(
    "📌 Menu",
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

    st.subheader("📥 Scan Kanban (Confirm Whole Joint Set)")

    scan = st.text_input(
        "Scan Kanban No.",
        placeholder="Scan barcode here...",
        key="scan_input"
    )

    if scan:
        lot = supabase.table("lot_master") \
            .select("kanban_no, model_joint_key") \
            .eq("kanban_no", scan) \
            .execute().data

        if not lot:
            st.error("❌ Kanban ไม่อยู่ใน Lot Master")
            st.stop()

        joint_key = lot[0]["model_joint_key"]

        all_set = supabase.table("lot_master") \
            .select("kanban_no") \
            .eq("model_joint_key", joint_key) \
            .execute().data

        delivered = supabase.table("kanban_delivery") \
            .select("kanban_no") \
            .eq("model_joint_key", joint_key) \
            .execute().data

        delivered_set = {d["kanban_no"] for d in delivered}

        to_insert = [
            {
                "kanban_no": r["kanban_no"],
                "model_joint_key": joint_key
            }
            for r in all_set
            if r["kanban_no"] not in delivered_set
        ]

        if not to_insert:
            st.warning("⚠️ ชุดนี้ถูก Confirm แล้วทั้งหมด")
            st.stop()

        supabase.table("kanban_delivery").insert(to_insert).execute()

        st.success(f"✅ Confirmed {len(to_insert)} Kanban (Joint Set)")
        st.json(to_insert)

# ==================================================
# 2) MODEL STATUS
# ==================================================
elif mode == "📊 Model Kanban Status":

    st.subheader("📊 Model / Lot Summary")

    col1, col2 = st.columns(2)
    model = col1.text_input("Model")
    lot = col2.text_input("Lot")

    q = supabase.table("lot_master").select(
        "model_name, lot_no, kanban_no"
    )

    if model:
        q = q.ilike("model_name", f"%{model}%")
    if lot:
        q = q.eq("lot_no", lot)

    lot_df = pd.DataFrame(q.execute().data)
    if lot_df.empty:
        st.info("No data")
        st.stop()

    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute().data
    )

    if del_df.empty:
        del_df = pd.DataFrame(columns=["kanban_no"])
    del_df["sent"] = 1

    df = lot_df.merge(del_df, on="kanban_no", how="left")
    df["sent"] = df["sent"].fillna(0)

    summary = df.groupby(
        ["model_name", "lot_no"]
    ).agg(
        Total=("kanban_no", "count"),
        Sent=("sent", "sum")
    ).reset_index()

    summary["Remaining"] = summary["Total"] - summary["Sent"]

    st.dataframe(summary, use_container_width=True)

# ==================================================
# 3) TRACKING
# ==================================================
elif mode == "🔍 Tracking Search":

    st.subheader("🔍 Kanban Tracking")

    kanban = st.text_input("Kanban No.")
    q = supabase.table("lot_master").select("*")

    if kanban:
        q = q.eq("kanban_no", kanban)

    lot_df = pd.DataFrame(q.execute().data)
    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no, confirmed_at")
        .execute().data
    )

    if del_df.empty:
        del_df = pd.DataFrame(columns=["kanban_no", "confirmed_at"])

    df = lot_df.merge(del_df, on="kanban_no", how="left")
    st.dataframe(df, use_container_width=True)

# ==================================================
# 4) UPLOAD
# ==================================================
elif mode == "🔐📤 Upload Lot Master":

    st.subheader("🔐 Upload Lot Master")

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("Access denied")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])
    if file:
        df = pd.read_csv(file) if file.name.endswith("csv") else pd.read_excel(file)

        required = {
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

        if not required.issubset(df.columns):
            st.error("❌ Column ไม่ครบ")
            st.stop()

        st.dataframe(df.head(), use_container_width=True)

        if st.button("🚀 Upload"):
            supabase.table("lot_master").upsert(
                df.to_dict("records")
            ).execute()
            st.success("Upload complete")
