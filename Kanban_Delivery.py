import streamlit as st
from supabase import create_client
import pandas as pd

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Kanban Delivery - MIND Automotive",
    layout="wide"
)

# =====================================================
# SUPABASE
# =====================================================
supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

st.title("📦 Kanban Delivery - MIND Automotive Parts")

# =====================================================
# TIMEZONE (GMT+7)
# =====================================================
def to_gmt7(ts):
    if not ts:
        return ""
    return (
        pd.to_datetime(ts, utc=True)
        .tz_convert("Asia/Bangkok")
        .strftime("%Y-%m-%d %H:%M:%S")
    )

# =====================================================
# COMMON HELPERS
# =====================================================
def safe_df(data, cols=None):
    if data:
        return pd.DataFrame(data)
    return pd.DataFrame(columns=cols or [])

def norm_lot(x):
    return (
        str(x)
        .replace(".0", "")
        .replace(" ", "")
        .replace("-", "")
        .strip()
    )

# =====================================================
# SIDEBAR
# =====================================================
mode = st.sidebar.radio(
    "📌 เลือกโหมด",
    [
        "📊 Lot Kanban Summary",
        "📦 Kanban Delivery Log",
        "🔍 Tracking Search",
        "🔐📤 Upload Lot Master",
    ]
)

# =====================================================
# 📊 LOT KANBAN SUMMARY (PRODUCTION – SOURCE OF TRUTH)
# =====================================================
if mode == "📊 Lot Kanban Summary":

    st.header("📊 Lot Kanban Summary (Production)")

    c1, c2 = st.columns(2)
    f_lot = c1.text_input("Lot No. (ต้องตรง 100%)")
    f_model = c2.text_input("Model (optional)")

    st.divider()

    # -------------------------------------------------
    # 1) LOAD SUMMARY TABLE (PRODUCTION TRUTH)
    # -------------------------------------------------
    summary_df = safe_df(
        supabase.table("lot_kanban_summary")
        .select(
            "lot_no, model_name, total_circuit, sent_circuit, remaining_circuit, last_updated_at"
        )
        .range(0, 50000)
        .execute()
        .data
    )

    if summary_df.empty:
        st.error("❌ ไม่พบข้อมูล lot_kanban_summary")
        st.stop()

    summary_df["lot_no"] = summary_df["lot_no"].apply(norm_lot)
    summary_df["model_name"] = summary_df["model_name"].astype(str).str.strip()

    # -------------------------------------------------
    # FILTER SUMMARY
    # -------------------------------------------------
    if f_lot:
        summary_df = summary_df[
            summary_df["lot_no"] == norm_lot(f_lot)
        ]

    if f_model:
        summary_df = summary_df[
            summary_df["model_name"]
            .str.contains(f_model, case=False, na=False)
        ]

    if summary_df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    # -------------------------------------------------
    # 2) LOAD LOT MASTER (CSV RECORD COUNT ONLY)
    # -------------------------------------------------
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("lot_no")
        .range(0, 50000)
        .execute()
        .data
    )

    lot_df["lot_no"] = lot_df["lot_no"].apply(norm_lot)

    if f_lot:
        lot_df = lot_df[lot_df["lot_no"] == norm_lot(f_lot)]

    # -------------------------------------------------
    # KPI DISPLAY (🔥 ตรงตามที่ต้องการ)
    # -------------------------------------------------
    total_record = len(lot_df)                # 📄 CSV = 1365
    total_circuit = int(summary_df["total_circuit"].sum())
    sent = int(summary_df["sent_circuit"].sum())
    remaining = int(summary_df["remaining_circuit"].sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📄 Total Record (CSV)", total_record)
    k2.metric("⚙️ Total Circuit", total_circuit)
    k3.metric("✅ Sent", sent)
    k4.metric("⏳ Remaining", remaining)

    st.divider()

    # -------------------------------------------------
    # DISPLAY SUMMARY TABLE
    # -------------------------------------------------
    summary_df["Last Update (GMT+7)"] = summary_df["last_updated_at"].apply(to_gmt7)

    st.subheader("📊 Summary by Lot / Model")

    st.dataframe(
        summary_df[
            [
                "lot_no",
                "model_name",
                "total_circuit",
                "sent_circuit",
                "remaining_circuit",
                "Last Update (GMT+7)",
            ]
        ].sort_values(["lot_no", "model_name"]),
        use_container_width=True
    )

    st.caption(
        f"📄 CSV Record = {total_record} | "
        f"⚙️ Production Circuit = {total_circuit}"
    )

# =====================================================
# 📦 KANBAN DELIVERY LOG (VIEW ONLY)
# =====================================================
elif mode == "📦 Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    lot_df = safe_df(
        supabase.table("lot_master")
        .select("kanban_no, model_name, lot_no")
        .range(0, 50000)
        .execute()
        .data
    )

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, last_scanned_at")
        .range(0, 50000)
        .execute()
        .data
    )

    if lot_df.empty:
        st.error("❌ ไม่พบ lot_master")
        st.stop()

    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["lot_no"] = lot_df["lot_no"].apply(norm_lot)

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
        del_df["Delivered At (GMT+7)"] = (
            del_df["last_scanned_at"]
            .fillna(del_df["created_at"])
            .apply(to_gmt7)
        )

    df = lot_df.merge(
        del_df[["kanban_no", "Delivered At (GMT+7)"]],
        on="kanban_no",
        how="left"
    )

    df["Status"] = df["Delivered At (GMT+7)"].apply(
        lambda x: "Sent" if x else "Remaining"
    )

    st.dataframe(df, use_container_width=True)

# =====================================================
# 🔍 TRACKING SEARCH (PLACEHOLDER)
# =====================================================
elif mode == "🔍 Tracking Search":
    st.info("🔍 ใช้ logic Tracking เดิมของคุณได้ (ไม่กระทบ Summary)")

# =====================================================
# 🔐📤 UPLOAD LOT MASTER
# =====================================================
elif mode == "🔐📤 Upload Lot Master":

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("🔒 สำหรับ Planner เท่านั้น")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])
    if not file:
        st.stop()

    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)

    st.dataframe(df.head(), use_container_width=True)

    if st.button("🚀 Upload เข้า Lot Master"):
        supabase.table("lot_master").insert(
            df.fillna("").astype(str).to_dict(orient="records")
        ).execute()

        st.success(f"✅ Upload สำเร็จ {len(df)} รายการ")
