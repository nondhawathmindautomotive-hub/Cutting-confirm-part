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
# =====================================================
# 📊 LOT KANBAN SUMMARY (FINAL - RPC / NO LIMIT)
# =====================================================
elif mode == "Lot Kanban Summary":

    st.header("Lot Kanban Summary")

    # -----------------------------
    # INPUT
    # -----------------------------
    c1, c2 = st.columns([2, 3])
    f_lot = c1.text_input("Lot No. (ต้องตรง 100%)")
    f_model = c2.text_input("Model (ค้นหาบางส่วนได้)")

    load = st.button("📥 Load Data", type="primary")

    if not load:
        st.info("ℹ️ กรุณากรอก Lot แล้วกดปุ่ม **Load Data**")
        st.stop()

    if not f_lot:
        st.warning("❌ ต้องระบุ Lot No.")
        st.stop()

    # =====================================================
    # 1) LOAD SUMMARY BY RPC (SOURCE OF TRUTH)
    # =====================================================
    result = supabase.rpc(
        "get_lot_kanban_summary",
        {"p_lot": f_lot.strip()}
    ).execute().data

    if not result:
        st.error("❌ ไม่พบข้อมูล Lot นี้")
        st.stop()

    row = result[0]

    total = int(row["total_kanban"])
    sent = int(row["sent_kanban"])
    remaining = int(row["remaining_kanban"])

    # -----------------------------
    # KPI
    # -----------------------------
    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total Kanban", total)
    k2.metric("✅ Sent", sent)
    k3.metric("⏳ Remaining", remaining)

    st.divider()

    # =====================================================
    # 2) LOAD DETAIL (OPTIONAL / DISPLAY ONLY)
    # =====================================================
    query = (
        supabase.table("vw_lot_kanban_summary")
        .select(
            "lot_no, model_name, total_kanban, sent_kanban, remaining_kanban"
        )
        .eq("lot_no", f_lot.strip())
    )

    if f_model:
        query = query.ilike("model_name", f"%{f_model.strip()}%")

    detail = query.range(0, 50000).execute().data
    df = safe_df(detail)

    if df.empty:
        st.warning("⚠️ ไม่พบข้อมูล Detail (แต่ Summary ถูกต้อง)")
        st.stop()

    # -----------------------------
    # FORCE TYPE
    # -----------------------------
    for c in ["total_kanban", "sent_kanban", "remaining_kanban"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # -----------------------------
    # DISPLAY DETAIL
    # -----------------------------
    st.subheader("📋 รายละเอียดแยกตาม Model")

    st.dataframe(
        df.sort_values("model_name"),
        use_container_width=True
    )

    st.caption(
        f"📊 Source of Truth: RPC(get_lot_kanban_summary) | "
        f"Detail: vw_lot_kanban_summary | "
        f"Lot {f_lot} | Total = {total}"
    )


# =====================================================
# 📦 KANBAN DELIVERY LOG (FINAL / OR SEARCH)
# =====================================================
# =====================================================
# 📦 KANBAN DELIVERY LOG (MASTER + DELIVERY)
# =====================================================
elif mode == "Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    c1, c2, c3, c4, c5 = st.columns(5)
    f_kanban = c1.text_input("Kanban No.")
    f_model  = c2.text_input("Model")
    f_lot    = c3.text_input("Lot No.")
    f_wire   = c4.text_input("Wire Number")
    f_date   = c5.date_input("Scan Date", value=None)

    st.divider()

    # -----------------------------
    # LOAD LOT MASTER (BASE)
    # -----------------------------
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("kanban_no, model_name, lot_no, wire_number")
        .range(0, 50000)
        .execute()
        .data
    )

    if lot_df.empty:
        st.error("❌ ไม่พบข้อมูล lot_master")
        st.stop()

    # Normalize
    for c in ["kanban_no", "model_name", "lot_no", "wire_number"]:
        lot_df[c] = lot_df[c].astype(str).str.strip()

    lot_df["lot_no"] = lot_df["lot_no"].str.replace(".0", "", regex=False)

    # -----------------------------
    # LOAD DELIVERY (EVENT)
    # -----------------------------
    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, last_scanned_at")
        .range(0, 50000)
        .execute()
        .data,
        ["kanban_no", "last_scanned_at"]
    )

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
        del_df["Delivered At"] = del_df["last_scanned_at"].apply(to_gmt7)
        del_df["Status"] = "Sent"
        del_df = del_df[["kanban_no", "Delivered At", "Status"]]
    else:
        del_df = pd.DataFrame(
            columns=["kanban_no", "Delivered At", "Status"]
        )

    # -----------------------------
    # MERGE (LEFT JOIN)
    # -----------------------------
    df = lot_df.merge(
        del_df,
        on="kanban_no",
        how="left"
    )

    df["Status"] = df["Status"].fillna("Not Sent")

    # -----------------------------
    # FILTER (ANY FIELD)
    # -----------------------------
    if f_kanban:
        df = df[df["kanban_no"].str.contains(f_kanban, case=False)]

    if f_model:
        df = df[df["model_name"].str.contains(f_model, case=False)]

    if f_lot:
        df = df[df["lot_no"] == f_lot.strip()]

    if f_wire:
        df = df[df["wire_number"].str.contains(f_wire, case=False)]

    if f_date:
        df = df[
            pd.to_datetime(df["Delivered At"], errors="coerce")
            .dt.date == f_date
        ]

    if df.empty:
        st.warning("❌ ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
        st.stop()

    # -----------------------------
    # DISPLAY
    # -----------------------------
    st.dataframe(
        df[
            [
                "kanban_no",
                "model_name",
                "lot_no",
                "wire_number",
                "Status",
                "Delivered At"
            ]
        ].sort_values("Delivered At", ascending=False),
        use_container_width=True
    )

    st.caption(f"📊 แสดงผล {len(df)} รายการ (รวมที่ยังไม่ Scan)")


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



















