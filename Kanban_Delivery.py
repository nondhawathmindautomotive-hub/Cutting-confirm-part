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
# SIDEBAR
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
# 1) SCAN KANBAN (JOINT A / B LOGIC)
# ==================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan / Confirm Kanban")

    def confirm_kanban():
        kanban = st.session_state.scan.strip()
        if not kanban:
            return

        lot = (
            supabase.table("lot_master")
            .select(
                "kanban_no, model_name, lot_no, model_joint_group"
            )
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
        )

        if not lot.data:
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban ใน Lot Master")
            st.session_state.scan = ""
            return

        row = lot.data[0]
        model = row["model_name"]
        lot_no = row["lot_no"]
        group = row["model_joint_group"]

        # ===== NO JOINT (เดี่ยว) =====
        if not group:
            exist = supabase.table("kanban_delivery") \
                .select("kanban_no") \
                .eq("kanban_no", kanban) \
                .execute()

            if exist.data:
                st.session_state.msg = ("warning", "⚠️ Kanban นี้ถูกส่งแล้ว")
            else:
                supabase.table("kanban_delivery").insert({
                    "kanban_no": kanban,
                    "model_name": model,
                    "lot_no": lot_no,
                    "joint_group": None
                }).execute()
                st.session_state.msg = ("success", f"✅ ส่ง Kanban {kanban}")

            st.session_state.scan = ""
            return

        # ===== JOINT GROUP =====
        group_rows = (
            supabase.table("lot_master")
            .select("kanban_no")
            .eq("model_joint_group", group)
            .execute()
            .data
        )

        kanbans = [r["kanban_no"] for r in group_rows]

        sent = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .in_("kanban_no", kanbans)
            .execute()
            .data
        )

        sent_set = {r["kanban_no"] for r in sent}
        to_insert = []

        for k in kanbans:
            if k not in sent_set:
                to_insert.append({
                    "kanban_no": k,
                    "model_name": model,
                    "lot_no": lot_no,
                    "joint_group": group
                })

        if not to_insert:
            st.session_state.msg = ("warning", "⚠️ Joint ชุดนี้ถูกส่งครบแล้ว")
        else:
            supabase.table("kanban_delivery").insert(to_insert).execute()
            st.session_state.msg = (
                "success",
                f"✅ ส่ง Joint Group สำเร็จ {len(to_insert)} Kanban"
            )

        st.session_state.scan = ""

    st.text_input("Scan Kanban No.", key="scan", on_change=confirm_kanban)

    if "msg" in st.session_state:
        t, m = st.session_state.msg
        getattr(st, t)(m)
        del st.session_state.msg

# ==================================================
# 2) MODEL KANBAN STATUS
# ==================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    model_filter = st.text_input("Model")
    lot_filter = st.text_input("Lot")

    lot_q = supabase.table("lot_master").select(
        "model_name, lot_no, kanban_no"
    )

    if model_filter:
        lot_q = lot_q.ilike("model_name", f"%{model_filter}%")
    if lot_filter:
        lot_q = lot_q.eq("lot_no", lot_filter)

    lot_df = pd.DataFrame(lot_q.execute().data)

    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data
    )

    if lot_df.empty:
        st.info("ไม่พบข้อมูล")
        st.stop()

    del_df["sent"] = 1
    df = lot_df.merge(del_df, on="kanban_no", how="left").fillna(0)

    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(
            Total_Kanban=("kanban_no", "nunique"),
            Sent=("sent", "sum")
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total_Kanban"] - summary["Sent"]
    st.dataframe(summary, use_container_width=True)

# ==================================================
# 3) TRACKING SEARCH
# ==================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    model = st.text_input("Model")
    wire = st.text_input("Wire number")
    lot = st.text_input("Lot")

    q = supabase.table("lot_master").select(
        "kanban_no, model_name, wire_number, lot_no"
    )

    if model:
        q = q.ilike("model_name", f"%{model}%")
    if wire:
        q = q.ilike("wire_number", f"%{wire}%")
    if lot:
        q = q.eq("lot_no", lot)

    lot_df = pd.DataFrame(q.execute().data)
    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at")
        .execute()
        .data
    )

    df = lot_df.merge(del_df, on="kanban_no", how="left")
    st.dataframe(df, use_container_width=True)

# ==================================================
# 4) UPLOAD LOT MASTER
# ==================================================
elif mode == "🔐📤 Upload Lot Master":

    st.header("🔐 Upload Lot Master")

    if st.text_input("Planner Password", type="password") != "planner":
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])

    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)

        required = {
            "lot_no",
            "kanban_no",
            "model_name",
            "joint_stock_a",
            "joint_stock_b"
        }

        if not required.issubset(df.columns):
            st.error(f"ต้องมี column: {required}")
            st.stop()

        # ===== BUILD model_joint_group =====
        def build_group(r):
            if pd.notna(r["joint_stock_a"]):
                return f"{r['lot_no']}_{r['model_name']}_{r['joint_stock_a']}"
            if pd.notna(r["joint_stock_b"]):
                return f"{r['lot_no']}_{r['model_name']}_{r['joint_stock_b']}"
            return None

        df["model_joint_group"] = df.apply(build_group, axis=1)

        if st.button("🚀 Upload"):
            supabase.table("lot_master").upsert(
                df.to_dict("records")
            ).execute()

            st.success(f"✅ Upload สำเร็จ {len(df)} records")
