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
    if ts is None or ts == "":
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
        "✅ Scan Kanban",
        "📊 Model Kanban Status",
        "📊 Lot Kanban Summary",
        "🔍 Tracking Search",
        "🔐📤 Upload Lot Master",
        "📦 Kanban Delivery Log",
    ]
)

# =====================================================
# HELPERS
# =====================================================
def safe_df(data, cols=None):
    if data:
        return pd.DataFrame(data)
    return pd.DataFrame(columns=cols or [])

def norm(v):
    return str(v).strip() if v is not None else ""

# =====================================================
# 1) SCAN KANBAN
# =====================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan Kanban")

    def confirm_scan():
        kanban = norm(st.session_state.scan)
        if not kanban:
            return

        now_ts = pd.Timestamp.now(
            tz="Asia/Bangkok"
        ).strftime("%Y-%m-%d %H:%M:%S")

        base = (
            supabase.table("lot_master")
            .select("kanban_no, model_name, lot_no")
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
            .data
        )

        if not base:
            st.error("❌ ไม่พบ Kanban")
            st.session_state.scan = ""
            return

        row = base[0]

        exist = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .eq("kanban_no", kanban)
            .execute()
            .data
        )

        if exist:
            supabase.table("kanban_delivery").update(
                {"last_scanned_at": now_ts}
            ).eq("kanban_no", kanban).execute()
            st.success("🔄 Scan ซ้ำ (อัปเดตเวลา)")
        else:
            supabase.table("kanban_delivery").insert({
                "kanban_no": kanban,
                "model_name": row["model_name"],
                "lot_no": row["lot_no"],
                "last_scanned_at": now_ts
            }).execute()
            st.success("✅ Scan สำเร็จ")

        st.session_state.scan = ""

    st.text_input(
        "Scan Kanban No.",
        key="scan",
        on_change=confirm_scan
    )

# =====================================================
# 2) MODEL KANBAN STATUS
# =====================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    c1, c2 = st.columns(2)
    model_filter = c1.text_input("Model")
    lot_filter = c2.text_input("Lot")

    lot_df = safe_df(
        supabase.table("lot_master")
        .select("model_name, kanban_no, lot_no")
        .range(0, 50000)
        .execute().data
    )

    if lot_df.empty:
        st.warning("ไม่พบข้อมูล")
        st.stop()

    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["model_name"] = lot_df["model_name"].astype(str).str.strip()
    lot_df["lot_no"] = (
        lot_df["lot_no"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    if model_filter:
        lot_df = lot_df[
            lot_df["model_name"]
            .str.contains(model_filter, case=False, na=False)
        ]

    if lot_filter:
        lot_df = lot_df[
            lot_df["lot_no"]
            .str.contains(lot_filter, case=False, na=False)
        ]

    lot_df = lot_df.drop_duplicates(
        subset=["model_name", "lot_no", "kanban_no"]
    )

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .range(0, 50000)
        .execute().data,
        ["kanban_no"]
    )

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
        del_df["sent"] = 1
    else:
        del_df["sent"] = 0

    df = lot_df.merge(
        del_df[["kanban_no", "sent"]],
        on="kanban_no",
        how="left"
    )

    df["sent"] = df["sent"].fillna(0)

    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(
            Total_Circuit=("kanban_no", "nunique"),
            Sent=("sent", "sum")
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total_Circuit"] - summary["Sent"]

    st.dataframe(summary, use_container_width=True)

# =====================================================
# 3) 📊 LOT KANBAN SUMMARY (⭐ CORE FIX ⭐)
# =====================================================
elif mode == "📊 Lot Kanban Summary":

    st.header("📊 Lot Kanban Summary (Production)")

    c1, c2 = st.columns(2)
    f_lot = c1.text_input("Lot No. (260105)")
    f_model = c2.text_input("Model (optional)")

    st.divider()

    # -------------------------------------------------
    # LOAD LOT MASTER (NO FILTER!)
    # -------------------------------------------------
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("kanban_no, model_name, lot_no")
        .range(0, 50000)
        .execute().data
    )

    if lot_df.empty:
        st.error("❌ ไม่พบข้อมูล lot_master")
        st.stop()

    # -------------------------------------------------
    # NORMALIZE FIRST (🔥 สำคัญที่สุด)
    # -------------------------------------------------
    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["model_name"] = lot_df["model_name"].astype(str).str.strip()
    lot_df["lot_no"] = (
        lot_df["lot_no"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"[^0-9A-Za-z]", "", regex=True)
        .str.strip()
    )

    # -------------------------------------------------
    # FILTER AFTER NORMALIZE
    # -------------------------------------------------
    if f_lot:
        lot_key = (
            f_lot.strip()
            .replace(".0", "")
            .replace(" ", "")
            .replace("-", "")
        )
        lot_df = lot_df[lot_df["lot_no"] == lot_key]

    if f_model:
        lot_df = lot_df[
            lot_df["model_name"]
            .str.contains(f_model, case=False, na=False)
        ]

    if lot_df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    # -------------------------------------------------
    # 📄 CSV LEVEL
    # -------------------------------------------------
    total_record = len(lot_df)              # ✅ 1365

    # -------------------------------------------------
    # ⚙️ CIRCUIT LEVEL
    # -------------------------------------------------
    circuit_df = lot_df.drop_duplicates(subset=["kanban_no"])
    total_circuit = len(circuit_df)         # 1007

    # -------------------------------------------------
    # DELIVERY
    # -------------------------------------------------
    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .range(0, 50000)
        .execute().data,
        ["kanban_no"]
    )

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()

    sent = circuit_df[
        circuit_df["kanban_no"].isin(del_df["kanban_no"])
    ]["kanban_no"].nunique()

    remaining = total_circuit - sent

    # -------------------------------------------------
    # KPI DISPLAY (FINAL ANSWER)
    # -------------------------------------------------
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📄 Total Record (CSV)", total_record)
    k2.metric("⚙️ Total Circuit", total_circuit)
    k3.metric("✅ Sent", sent)
    k4.metric("⏳ Remaining", remaining)

# =====================================================
# 4) TRACKING SEARCH
# =====================================================
elif mode == "🔍 Tracking Search":
    st.info("โหมดนี้ยังใช้ logic เดิมของคุณได้")

# =====================================================
# 5) UPLOAD LOT MASTER
# =====================================================
elif mode == "🔐📤 Upload Lot Master":
    st.info("โหมด Upload ใช้ตามเดิมได้")

# =====================================================
# 6) KANBAN DELIVERY LOG
# =====================================================
elif mode == "📦 Kanban Delivery Log":
    st.info("โหมด Log ใช้ตามเดิมได้")
