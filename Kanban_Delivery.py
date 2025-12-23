import streamlit as st
from supabase import create_client
import pandas as pd

# ===============================
# CONFIG
# ===============================
st.set_page_config(page_title="Kanban Delivery Tracking", layout="wide")

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
# HELPER : SAFE DATAFRAME
# =====================================================
def safe_df(data, columns):
    """
    รับ list จาก Supabase แล้วคืน DataFrame
    ถ้า data ว่าง → คืน DataFrame ที่มี column ครบ
    """
    if data:
        return pd.DataFrame(data)
    return pd.DataFrame(columns=columns)

# =====================================================
# 1) SCAN KANBAN
# =====================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan / Confirm Kanban")

    joint_mode = st.toggle("🔗 Joint Delivery (ส่งทั้ง Lot / Model)", value=False)

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
            .data
        )

        if not lot:
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban นี้")
            st.session_state.scan = ""
            return

        model = lot[0]["model_name"]
        lot_no = lot[0]["lot_no"]

        # ================= JOINT =================
        if joint_mode:
            all_k = supabase.table("lot_master") \
                .select("kanban_no") \
                .eq("model_name", model) \
                .eq("lot_no", lot_no) \
                .execute().data

            all_list = [x["kanban_no"] for x in all_k]

            sent_df = safe_df(
                supabase.table("kanban_delivery")
                .select("kanban_no")
                .in_("kanban_no", all_list)
                .execute().data,
                ["kanban_no"]
            )

            sent_set = set(sent_df["kanban_no"])

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
                f"✅ Joint ส่งแล้ว {len(insert_rows)} ใบ | {model} | Lot {lot_no}"
            )
            st.session_state.scan = ""
            return

        # ================= NORMAL =================
        exist = supabase.table("kanban_delivery") \
            .select("kanban_no") \
            .eq("kanban_no", kanban) \
            .execute().data

        if exist:
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
# =====================================================
# 2) MODEL KANBAN STATUS (FINAL / STABLE)
# =====================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    c1, c2 = st.columns(2)
    model_filter = c1.text_input("Model")
    lot_filter = c2.text_input("Lot (เช่น 251205)")

    # ===============================
    # LOAD LOT MASTER
    # ===============================
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("model_name, kanban_no, lot_no")
        .execute().data,
        ["model_name", "kanban_no", "lot_no"]
    )

    if lot_df.empty:
        st.warning("ไม่พบข้อมูลใน Lot Master")
        st.stop()

    # ===============================
    # 🔥 CLEAN DATA (หัวใจของปัญหา)
    # ===============================
    lot_df["lot_no"] = lot_df["lot_no"].astype(str).str.strip()
    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["model_name"] = lot_df["model_name"].astype(str).str.strip()

    # ===============================
    # LOAD DELIVERY
    # ===============================
    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute().data,
        ["kanban_no"]
    )

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
        del_df["sent"] = 1
    else:
        del_df = pd.DataFrame(columns=["kanban_no", "sent"])

    # ===============================
    # MERGE
    # ===============================
    df = lot_df.merge(del_df, on="kanban_no", how="left")
    df["sent"] = df["sent"].fillna(0)

    # ===============================
    # FILTER (โรงงานจริง)
    # ===============================
    if model_filter:
        df = df[df["model_name"].str.contains(model_filter, case=False, na=False)]

    if lot_filter:
        df = df[df["lot_no"] == lot_filter.strip()]

    if df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไขค้นหา")
        st.stop()

    # ===============================
    # SUMMARY
    # ===============================
    summary = (
        df.groupby(["model_name", "lot_no"])
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

# =====================================================
# 3) TRACKING SEARCH (❌ KEYERROR FIXED)
# =====================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    c1, c2, c3 = st.columns(3)
    c4, c5, c6 = st.columns(3)

    kanban = c1.text_input("Kanban No.")
    model = c2.text_input("Model")
    wire = c3.text_input("Wire Number")

    subpackage = c4.text_input("Subpackage Number")
    harness = c5.text_input("Wire Harness Code")
    lot = c6.text_input("Lot No.")

    lot_df = safe_df(
        supabase.table("lot_master")
        .select("""
            kanban_no,
            model_name,
            wire_number,
            subpackage_number,
            wire_harness_code,
            lot_no,
            joint_a,
            joint_b
        """)
        .execute().data,
        [
            "kanban_no",
            "model_name",
            "wire_number",
            "subpackage_number",
            "wire_harness_code",
            "lot_no",
            "joint_a",
            "joint_b"
        ]
    )

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at")
        .execute().data,
        ["kanban_no", "created_at"]
    )

    df = lot_df.merge(del_df, on="kanban_no", how="left")

    # ================= FILTER =================
    if kanban:
        df = df[df["kanban_no"].str.contains(kanban, na=False)]
    if model:
        df = df[df["model_name"].str.contains(model, case=False, na=False)]
    if wire:
        df = df[df["wire_number"].str.contains(wire, na=False)]
    if subpackage:
        df = df[df["subpackage_number"].str.contains(subpackage, na=False)]
    if harness:
        df = df[df["wire_harness_code"].str.contains(harness, na=False)]
    if lot:
        df = df[df["lot_no"].astype(str).str.contains(lot, na=False)]

    if df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไขค้นหา")
        st.stop()

    df.rename(columns={
        "kanban_no": "Kanban No",
        "model_name": "Model",
        "wire_number": "Wire",
        "subpackage_number": "Subpackage",
        "wire_harness_code": "Harness Code",
        "lot_no": "Lot",
        "created_at": "Delivered At",
        "joint_a": "Joint A",
        "joint_b": "Joint B"
    }, inplace=True)

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


