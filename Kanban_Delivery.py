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
        "🔐📤 Upload Lot Master "
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

        # ตรวจใน lot_master
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

        # INSERT (เวลาใช้ default DB = GMT+7)
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
        if t == "success":
            st.success(m)
        elif t == "warning":
            st.warning(m)
        else:
            st.error(m)
        del st.session_state.msg

# ==================================================
# 2) MODEL KANBAN STATUS
# ==================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    try:
        # ดึง lot_master
        lot_df = pd.DataFrame(
            supabase.table("lot_master")
            .select("model_name, kanban_no")
            .execute()
            .data
        )

        # ดึง kanban_delivery
        delivery_df = pd.DataFrame(
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .execute()
            .data
        )

        if lot_df.empty:
            st.info("ยังไม่มีข้อมูล Lot master")
            st.stop()

        # 🔥 แยก Lot จาก kanban_no (1612951-251201)
        lot_df["lot"] = lot_df["kanban_no"].str.split("-").str[-1]

        if not delivery_df.empty:
            delivery_df["sent"] = 1
        else:
            delivery_df = pd.DataFrame(columns=["kanban_no", "sent"])

        # merge
        df = lot_df.merge(delivery_df, on="kanban_no", how="left")
        df["sent"] = df["sent"].fillna(0)

        # group by Model + Lot
        summary = (
            df.groupby(["model_name", "lot"])
            .agg(
                Total_Kanban=("kanban_no", "nunique"),
                Sent=("sent", "sum")
            )
            .reset_index()
        )

        summary["Remaining"] = summary["Total_Kanban"] - summary["Sent"]

        # rename สำหรับแสดงผล
        summary.rename(columns={
            "model_name": "Model",
            "lot": "Lot",
            "Total_Kanban": "Total Kanban"
        }, inplace=True)

        st.dataframe(summary, use_container_width=True)

    except Exception as e:
        st.error("❌ สรุป Model + Lot ผิดพลาด")
        st.exception(e)

# ==================================================
# 3) TRACKING SEARCH
# ==================================================
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

    # 🔥 SEARCH BY LOT (ท้าย Kanban)
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
# 4) UPLOAD LOT MASTER 
# ==================================================
elif mode == "🔐📤 Upload Lot Master ":

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

        if st.button("🚀 Upload to Data Base"):
            data = (
                df[list(required_cols)]
                .dropna(subset=["kanban_no"])
                .to_dict("records")
            )

            supabase.table("lot_master").insert(
                data,
                count="exact"
            ).execute()

            st.success(f"✅ Upload สำเร็จ {len(data)} records")




