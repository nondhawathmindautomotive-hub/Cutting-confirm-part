import streamlit as st
from supabase import create_client
import pandas as pd

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(
    page_title="Kanban Delivery - MIND Automotive",
    layout="wide"
)

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
# HELPERS
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
# 📊 LOT KANBAN SUMMARY (PRODUCTION – FINAL)
# =====================================================
if mode == "📊 Lot Kanban Summary":

    st.header("📊 Lot Kanban Summary (Production)")

    c1, c2 = st.columns(2)
    f_lot = c1.text_input("Lot No. (ต้องตรง)")
    f_model = c2.text_input("Model (optional)")

    st.divider()

    # -------------------------------------------------
    # 1) LOAD SUMMARY TABLE (SOURCE OF TRUTH)
    # -------------------------------------------------
    summary_df = safe_df(
        supabase.table("lot_kanban_summary")
        .select(
            "lot_no, model_name, total_circuit, sent_circuit, remaining_circuit, last_updated_at"
        )
        .range(0, 50000)
        .execute().data
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
    # 2) LOAD LOT MASTER (FOR CSV RECORD COUNT)
    # -------------------------------------------------
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("lot_no")
        .range(0, 50000)
        .execute().data
    )

    lot_df["lot_no"] = lot_df["lot_no"].apply(norm_lot)

    if f_lot:
        lot_df = lot_df[lot_df["lot_no"] == norm_lot(f_lot)]

    # -------------------------------------------------
    # KPI (🔥 ตรงตามที่คุณต้องการ)
    # -------------------------------------------------
    total_record = len(lot_df)  # 👈 1365

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
        use_container_width=True,
    )

    st.caption(
        f"📄 CSV Record = {total_record} | "
        f"⚙️ Circuit = {total_circuit}"
    )

# =====================================================
# 📦 KANBAN DELIVERY LOG
# =====================================================
elif mode == "📦 Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    lot_df = safe_df(
        supabase.table("lot_master")
        .select("kanban_no, model_name, lot_no")
        .range(0, 50000)
        .execute().data
    )

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, last_scanned_at")
        .range(0, 50000)
        .execute().data
    )

    if lot_df.empty:
        st.error("❌ ไม่พบ lot_master")
        st.stop()

    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["lot_no"] = lot_df["lot_no"].apply(norm_lot)

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
        del_df["Delivered At"] = (
            del_df["last_scanned_at"]
            .fillna(del_df["created_at"])
            .apply(to_gmt7)
        )

    df = lot_df.merge(
        del_df[["kanban_no", "Delivered At"]],
        on="kanban_no",
        how="left"
    )

    df["Status"] = df["Delivered At"].apply(
        lambda x: "Sent" if x else "Remaining"
    )

    st.dataframe(df, use_container_width=True)

# =====================================================
# 🔍 TRACKING SEARCH
# =====================================================
elif mode == "🔍 Tracking Search":
    st.info("ใช้ logic เดิมของคุณได้ (ไม่กระทบ summary)")

# =====================================================
# 🔐📤 UPLOAD LOT MASTER
# =====================================================
elif mode == "🔐📤 Upload Lot Master":
    st.info("ใช้ logic Upload เดิมได้")
