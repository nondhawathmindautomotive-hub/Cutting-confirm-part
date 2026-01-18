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
        "Part Tracking", 
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

    # =============================
    # FILTER
    # =============================
    c1, c2, c3, c4 = st.columns(4)
    f_lot = c1.text_input("Lot No. (ต้องตรง 100%)")
    f_model = c2.text_input("Model")
    f_wire = c3.text_input("Wire Number")
    f_part = c4.text_input("Harness Part No")

    f_status = st.selectbox(
        "Status",
        ["ALL", "SENT", "REMAIN"],
        format_func=lambda x: {
            "ALL": "📦 ทั้งหมด",
            "SENT": "✅ ส่งแล้ว",
            "REMAIN": "⏳ ยังไม่ส่ง"
        }[x]
    )

    # ⛔ ต้องอยู่ตรงนี้เท่านั้น
    if not f_lot:
        st.info("กรุณาใส่ Lot No.")
        st.stop()

    # =============================
    # KPI
    # =============================
    with st.spinner("กำลังคำนวณยอดจริงจากฐานข้อมูล..."):
        kpi_res = supabase.rpc(
            "rpc_part_kpi",
            {
                "p_lot_no": f_lot.strip(),
                "p_wire_number": f_wire.strip() or None,
                "p_harness_part_no": f_part.strip() or None
            }
        ).execute()

    if not kpi_res.data:
        st.warning("ไม่พบข้อมูล")
        st.stop()

    kpi = kpi_res.data[0]

    total_kanban = int(kpi["total_kanban"])
    sent_kanban = int(kpi["sent_kanban"])
    remaining_kanban = int(kpi["remaining_kanban"])

    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total Kanban", total_kanban)
    k2.metric("✅ Sent", sent_kanban)
    k3.metric("⏳ Remaining", remaining_kanban)

    st.divider()

    # =============================
    # DETAIL TABLE
    # =============================
    with st.spinner("กำลังโหลดรายการวงจร..."):
        res = supabase.rpc(
            "rpc_lot_kanban_circuits",
            {
                "p_lot_no": f_lot.strip(),
                "p_model": f_model.strip() or None,
                "p_status": f_status,
                "p_wire_number": f_wire.strip() or None,
                "p_harness_part_no": f_part.strip() or None
            }
        ).execute()

    df = safe_df(res.data)

    if df.empty:
        st.warning("ไม่พบรายการวงจรตามเงื่อนไข")
        st.stop()

    df["Delivered At (GMT+7)"] = df["delivered_at"].apply(to_gmt7)
    df["Status"] = df["sent"].apply(lambda x: "Sent" if x else "Remaining")

    st.dataframe(
        df[
            [
                "kanban_no",
                "model_name",
                "harness_part_no",
                "wire_number",
                "Status",
                "Delivered At (GMT+7)"
            ]
        ],
        use_container_width=True,
        height=650
    )

    st.caption(
        f"📊 Source: rpc_part_kpi + rpc_lot_kanban_circuits | "
        f"Lot {f_lot} | Total จริง = {total_kanban}"
    )


# =====================================================
# 📦 KANBAN DELIVERY LOG (FINAL / OR SEARCH)
# =====================================================
elif mode == "Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log ")

    c1, c2, c3 = st.columns(3)
    c4, c5 = st.columns(2)

    f_kanban = c1.text_input("Kanban No.")
    f_lot = c2.text_input("Lot No.")
    f_model = c3.text_input("Model")
    f_wire = c4.text_input("Wire Number / Part No.")
    f_date = c5.date_input("Scan Date", value=None)

    if st.button("🔍 Load Data"):

        res = supabase.rpc(
            "rpc_kanban_delivery_log",
            {
                "p_kanban": f_kanban or None,
                "p_lot": f_lot or None,
                "p_model": f_model or None,
                "p_wire": f_wire or None,
                "p_part": f_wire or None,
                "p_scan_date": str(f_date) if f_date else None
            }
        ).execute()

        df = safe_df(res.data)

        if df.empty:
            st.warning("❌ ไม่พบข้อมูลตามเงื่อนไข")
            st.stop()

        # KPI
        total = len(df)
        sent = (df["status"] == "Sent").sum()
        remaining = total - sent

        k1, k2, k3 = st.columns(3)
        k1.metric("📦 Total", total)
        k2.metric("✅ Sent", sent)
        k3.metric("⏳ Not Sent", remaining)

        df["Delivered At (GMT+7)"] = df["delivered_at"].apply(to_gmt7)

        st.dataframe(
            df[
                [
                    "kanban_no",
                    "lot_no",
                    "model_name",
                    "harness_part_no",
                    "wire_number",
                    "status",
                    "Delivered At (GMT+7)"
                ]
            ],
            use_container_width=True,
            height=650
        )

        st.caption("📊 Source: lot_master + kanban_delivery (RPC Audit)")

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

# =====================================================
# 6) PART TRACKING (WIRE / HARNESS)
# =====================================================
elif mode == "Part Tracking":

    st.header("🧩 Part Tracking (Wire / Harness)")

    c1, c2 = st.columns(2)
    f_wire = c1.text_input("Wire Number")
    f_part = c2.text_input("Harness Part No")

    if not f_wire and not f_part:
        st.info("กรุณาใส่ Wire Number หรือ Harness Part No อย่างน้อย 1 ช่อง")
        st.stop()

    with st.spinner("กำลังค้นหาข้อมูลจากฐานข้อมูล..."):
        res = supabase.rpc(
            "rpc_part_tracking",
            {
                "p_wire_number": f_wire or None,
                "p_harness_part_no": f_part or None
            }
        ).execute()

    df = pd.DataFrame(res.data)

    if df.empty:
        st.warning("❌ ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    # =============================
    # KPI
    # =============================
    total = len(df)
    sent = (df["status"] == "Sent").sum()
    not_sent = total - sent

    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total", total)
    k2.metric("✅ Sent", sent)
    k3.metric("⏳ Not Sent", not_sent)

    st.divider()

    # =============================
    # TIMEZONE FORMAT
    # =============================
    df["Delivered At (GMT+7)"] = df["delivered_at"].apply(to_gmt7)

    # =============================
    # DISPLAY TABLE
    # =============================
    st.dataframe(
        df[
            [
                "kanban_no",
                "lot_no",
                "model_name",
                "harness_part_no",
                "wire_number",
                "status",
                "Delivered At (GMT+7)"
            ]
        ],
        use_container_width=True,
        height=600
    )

    st.caption(
        f"📊 Source: rpc_part_tracking | "
        f"Total = {total}"
    )


































