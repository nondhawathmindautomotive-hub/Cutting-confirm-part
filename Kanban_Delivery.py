import streamlit as st
from supabase import create_client
import pandas as pd

# ===============================
# CONFIG
# ===============================
st.set_page_config("Kanban Delivery Tracking", layout="wide")

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

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

# =====================================================
# 1) SCAN KANBAN
# =====================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan / Confirm Kanban")

    joint_mode = st.toggle(
        "🔗 Joint Delivery (ส่งทั้งชุด Lot + Model)",
        value=False
    )

    def confirm_kanban():
        kanban = st.session_state.scan.strip()
        if not kanban:
            return

        lot = (
            supabase.table("lot_master")
            .select("kanban_no, model_name, lot_no")
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
        )

        if not lot.data:
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban ใน Lot Master")
            st.session_state.scan = ""
            return

        model = lot.data[0]["model_name"]
        lot_no = lot.data[0]["lot_no"]

        # ================= JOINT =================
        if joint_mode:
            all_k = (
                supabase.table("lot_master")
                .select("kanban_no")
                .eq("model_name", model)
                .eq("lot_no", lot_no)
                .execute()
                .data
            )

            all_list = [k["kanban_no"] for k in all_k]

            sent = (
                supabase.table("kanban_delivery")
                .select("kanban_no")
                .in_("kanban_no", all_list)
                .execute()
                .data
            )

            sent_set = {s["kanban_no"] for s in sent}

            insert_rows = [
                {
                    "kanban_no": k,
                    "model_name": model,
                    "lot_no": lot_no
                }
                for k in all_list if k not in sent_set
            ]

            if not insert_rows:
                st.session_state.msg = ("warning", "⚠️ Lot นี้ถูกส่งครบแล้ว")
                st.session_state.scan = ""
                return

            supabase.table("kanban_delivery").insert(insert_rows).execute()

            st.session_state.msg = (
                "success",
                f"✅ Joint ส่งแล้ว {len(insert_rows)} ใบ | Model {model} | Lot {lot_no}"
            )
            st.session_state.scan = ""
            return

        # ================= NORMAL =================
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
            "lot_no": lot_no
        }).execute()

        st.session_state.msg = ("success", f"✅ ส่ง Kanban {kanban}")
        st.session_state.scan = ""

    st.text_input("Scan Kanban No.", key="scan", on_change=confirm_kanban)

    if "msg" in st.session_state:
        t, m = st.session_state.msg
        getattr(st, t)(m)
        del st.session_state.msg

# =====================================================
# 2) MODEL STATUS
# =====================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    c1, c2 = st.columns(2)
    model = c1.text_input("Model")
    lot = c2.text_input("Lot")

    lot_df = pd.DataFrame(
        supabase.table("lot_master")
        .select("model_name, kanban_no, lot_no")
        .execute()
        .data
    )

    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data
    )

    del_df["sent"] = 1

    df = lot_df.merge(del_df, on="kanban_no", how="left")
    df["sent"] = df["sent"].fillna(0)

    if model:
        df = df[df["model_name"].str.contains(model, case=False)]

    if lot:
        df = df[df["lot_no"] == lot]

    if df.empty:
        st.warning("ไม่พบข้อมูล")
        st.stop()

    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(
            Total_Kanban=("kanban_no", "count"),
            Sent=("sent", "sum")
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total_Kanban"] - summary["Sent"]

    st.dataframe(summary, use_container_width=True)

# =====================================================
# 3) TRACKING SEARCH
# =====================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    df = pd.DataFrame(
        supabase.table("lot_master")
        .select("""
            kanban_no, model_name, wire_number,
            subpackage_number, wire_harness_code,
            lot_no, joint_a, joint_b
        """)
        .execute()
        .data
    )

    del_df = pd.DataFrame(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at")
        .execute()
        .data
    )

    df = df.merge(del_df, on="kanban_no", how="left")
    st.dataframe(df, use_container_width=True)

# =====================================================
# 4) UPLOAD LOT MASTER
# =====================================================
elif mode == "🔐📤 Upload Lot Master":

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("🔒 สำหรับ Planner เท่านั้น")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])

    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)

        required = {
            "lot_no", "kanban_no", "model_name",
            "wire_number", "subpackage_number",
            "wire_harness_code", "joint_a", "joint_b"
        }

        if not required.issubset(df.columns):
            st.error(f"❌ ต้องมี column: {required}")
            st.stop()

        if st.button("🚀 Upload"):
            supabase.table("lot_master").upsert(
                df[list(required)].to_dict("records")
            ).execute()

            st.success(f"✅ Upload {len(df)} records")
