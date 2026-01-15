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
# HELPERS
# =====================================================
def safe_df(data, cols=None):
    if data:
        return pd.DataFrame(data)
    return pd.DataFrame(columns=cols or [])

def norm(x):
    return str(x).strip() if x is not None else ""

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
        "Scan Kanban",
        "Lot Kanban Summary",
        "Kanban Delivery Log",
        "Tracking Search",
        "Upload Lot Master",
    ]
)

# =====================================================
# 1) SCAN KANBAN
# =====================================================
if mode == "Scan Kanban":

    st.header("✅ Scan Kanban")

    def confirm_scan():
        kanban = norm(st.session_state.scan)
        if not kanban:
            return

        now_ts = pd.Timestamp.now(tz="Asia/Bangkok").strftime("%Y-%m-%d %H:%M:%S")

        base = (
            supabase.table("lot_master")
            .select(
                "kanban_no, model_name, lot_no, wire_number, joint_a, joint_b"
            )
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
            .data
        )

        if not base:
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban ใน Lot Master")
            st.session_state.scan = ""
            return

        row = base[0]
        model = norm(row["model_name"])
        lot = norm(row["lot_no"])
        wire_number = norm(row.get("wire_number"))
        joint_a = norm(row.get("joint_a"))
        joint_b = norm(row.get("joint_b"))

        # -------------------------
        # CHECK EXIST
        # -------------------------
        exist = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .eq("kanban_no", kanban)
            .execute()
            .data
        )

        payload = {
            "kanban_no": kanban,
            "model_name": model,
            "lot_no": lot,
            "wire_number": wire_number,
            "last_scanned_at": now_ts
        }

        if exist:
            supabase.table("kanban_delivery").update(payload)\
                .eq("kanban_no", kanban).execute()
            st.session_state.msg = ("success", "🔄 Scan ซ้ำ (อัปเดตเวลา)")
        else:
            supabase.table("kanban_delivery").insert(payload).execute()
            st.session_state.msg = ("success", "✅ ส่ง Kanban สำเร็จ")

        st.session_state.scan = ""

    st.text_input(
        "Scan Kanban No.",
        key="scan",
        on_change=confirm_scan
    )

    if "msg" in st.session_state:
        t, m = st.session_state.msg
        getattr(st, t)(m)
        del st.session_state.msg

# =====================================================
# 2) LOT KANBAN SUMMARY (SOURCE OF TRUTH)
# =====================================================
elif mode == "Lot Kanban Summary":

    st.header("📊 Lot Kanban Summary")

    c1, c2, c3 = st.columns(3)
    f_lot = c1.text_input("Lot No. (ต้องตรง 100%)")
    f_model = c2.text_input("Model (ค้นหาบางส่วนได้)")
    f_status = c3.selectbox(
        "Status",
        ["ALL", "SENT", "REMAIN"],
        format_func=lambda x: {
            "ALL": "📦 ทั้งหมด",
            "SENT": "✅ ส่งแล้ว",
            "REMAIN": "⏳ ยังไม่ส่ง"
        }[x]
    )

    if not f_lot:
        st.info("กรุณาใส่ Lot No.")
        st.stop()

    with st.spinner("กำลังโหลดข้อมูลจากฐานจริง..."):
        res = supabase.rpc(
            "rpc_lot_kanban_circuits",
            {
                "p_lot_no": f_lot.strip(),
                "p_model": f_model.strip() or None,
                "p_status": f_status
            }
        ).execute()

    df = safe_df(res.data)

    if df.empty:
        st.warning("ไม่พบข้อมูล")
        st.stop()

    # =============================
    # KPI (TRUTH FROM RPC)
    # =============================
    total = len(df)
    sent = int(df["sent"].sum())
    remaining = total - sent

    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total Kanban", total)
    k2.metric("✅ Sent", sent)
    k3.metric("⏳ Remaining", remaining)

    st.divider()

    # =============================
    # FORMAT TIME
    # =============================
    df["Delivered At (GMT+7)"] = df["delivered_at"].apply(to_gmt7)
    df["Status"] = df["sent"].apply(lambda x: "Sent" if x else "Remaining")

    # =============================
    # DISPLAY TABLE (PRO LEVEL)
    # =============================
    st.dataframe(
        df[
            [
                "kanban_no",
                "model_name",
                "wire_number",
                "Status",
                "Delivered At (GMT+7)"
            ]
        ],
        use_container_width=True,
        height=600
    )

    st.caption(
        f"📊 Source: rpc_lot_kanban_circuits | Lot {f_lot} | Total = {total}"
    )


# =====================================================
# 📦 KANBAN DELIVERY LOG (FINAL / OR SEARCH)
# =====================================================
elif mode == "Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    c1, c2, c3 = st.columns(3)
    c4, c5 = st.columns(2)

    kanban = c1.text_input("Kanban No.")
    model  = c2.text_input("Model")
    lot    = c3.text_input("Lot No.")
    wire   = c4.text_input("Wire Number")
    scan_d = c5.date_input("Scan Date", value=None)

    # 🔥 CALL RPC
    params = {
        "p_kanban": kanban or None,
        "p_model": model or None,
        "p_lot": lot or None,
        "p_wire": wire or None,
        "p_scan_date": scan_d.isoformat() if scan_d else None
    }

    data = supabase.rpc(
        "rpc_kanban_delivery_log",
        params
    ).execute().data

    df = safe_df(data)

    if df.empty:
        st.warning("❌ ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
        st.stop()

    # =============================
    # FORMAT TIME
    # =============================
    df["Delivered At (GMT+7)"] = df["delivered_at"].apply(to_gmt7)

    # =============================
    # KPI
    # =============================
    total = len(df)
    sent = len(df[df["delivery_status"] == "Sent"])
    remaining = total - sent

    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total", total)
    k2.metric("✅ Sent", sent)
    k3.metric("⏳ Not Sent", remaining)

    # =============================
    # DISPLAY
    # =============================
    st.dataframe(
        df[
            [
                "kanban_no",
                "model_name",
                "lot_no",
                "wire_number",
                "delivery_status",
                "Delivered At (GMT+7)"
            ]
        ],
        use_container_width=True
    )

    st.caption("📊 Source: RPC (lot_master LEFT JOIN kanban_delivery)")

# =====================================================
# 4) TRACKING SEARCH
# =====================================================
elif mode == "Tracking Search":

    st.header("🔍 Tracking Search")

    kanban = st.text_input("Kanban No.")
    model = st.text_input("Model")
    lot = st.text_input("Lot No.")

    query = supabase.table("lot_master").select(
        "kanban_no, model_name, lot_no"
    )

    if kanban:
        query = query.ilike("kanban_no", f"%{kanban}%")
    if model:
        query = query.ilike("model_name", f"%{model}%")
    if lot:
        query = query.ilike("lot_no", f"%{lot}%")

    df = safe_df(query.range(0, 50000).execute().data)
    st.dataframe(df, use_container_width=True)

# =====================================================
# 5) UPLOAD LOT MASTER
# =====================================================
elif mode == "Upload Lot Master":

    st.header("🔐 Upload Lot Master")

    if st.text_input("Password", type="password") != "planner":
        st.warning("Planner only")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])
    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
        st.dataframe(df.head())
























