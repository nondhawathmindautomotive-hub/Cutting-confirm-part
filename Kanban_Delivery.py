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
    return pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M:%S")


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

        try:
            # ---------------------------------
            # CALL RPC (RETURN INT)
            # ---------------------------------
            res = supabase.rpc(
                "rpc_complete_joint_by_kanban",
                {
                    "p_kanban_no": kanban
                }
            ).execute()

            # 🔑 RPC นี้ RETURN เป็น int โดยตรง
            completed = int(res.data)

            if completed > 0:
                st.session_state.msg = (
                    "success",
                    f"✅ COMPLETE สำเร็จ {completed} วงจร (Joint / Single)"
                )
            else:
                st.session_state.msg = (
                    "warning",
                    "⚠️ Kanban / Joint นี้ถูกส่งครบแล้ว"
                )

        except Exception as e:
            st.session_state.msg = (
                "error",
                f"❌ RPC Error: {e}"
            )

        st.session_state.scan = ""

    # -----------------------------
    # INPUT (AUTO CONFIRM)
    # -----------------------------
    st.text_input(
        "Scan Kanban No.",
        key="scan",
        on_change=confirm_scan
    )

    # -----------------------------
    # MESSAGE
    # -----------------------------
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

    st.header("📦 Kanban Delivery Log")

    c1, c2, c3 = st.columns(3)
    c4, c5 = st.columns(2)

    f_kanban = c1.text_input("Kanban No.")
    f_lot    = c2.text_input("Lot No.")
    f_model  = c3.text_input("Model")
    f_wire   = c4.text_input("Wire / Part No.")
    f_date   = c5.date_input("Scan Date", value=None)

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

        # =============================
        # FORMAT TIME (TH)
        # =============================
        df["Delivered At (GMT+7)"] = df["delivered_at"].apply(to_gmt7)

        # =============================
        # KPI
        # =============================
        total = len(df)
        sent = (df["status"] == "Sent").sum()
        remaining = total - sent

        k1, k2, k3 = st.columns(3)
        k1.metric("📦 Total", total)
        k2.metric("✅ Sent", sent)
        k3.metric("⏳ Not Sent", remaining)

        st.divider()

        # =============================
        # TABLE (FULL DETAIL)
        # =============================
        st.dataframe(
            df[
                [
                    "lot_no",
                    "kanban_no",
                    "wire_harness_code",
                    "model_name",
                    "harness_part_no",
                    "wire_number",
                    "subpackage_number",
                    "cable_name",
                    "wire_length_mm",
                    "joint_a",
                    "joint_b",
                    "mc_a",
                    "mc_b",
                    "twist_mc",
                    "status",
                    "Delivered At (GMT+7)",
                    "delivered_by_name"
                ]
            ],
            use_container_width=True,
            height=700
        )

        st.caption(
            "📊 Source: lot_master + kanban_delivery + operator_master (RPC)"
        )

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
# 5) UPLOAD LOT MASTER (PRODUCTION VERSION)
# =====================================================
elif mode == "Upload Lot Master":

    st.header("🔐 Upload Lot Master (Latest Only)")

    # -----------------------------
    # PASSWORD
    # -----------------------------
    if st.text_input("Password", type="password") != "planner":
        st.warning("❌ Planner only")
        st.stop()

    # -----------------------------
    # FILE UPLOAD
    # -----------------------------
    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])
    if not file:
        st.stop()

    # -----------------------------
    # READ FILE
    # -----------------------------
    try:
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
    except Exception as e:
        st.error(f"❌ อ่านไฟล์ไม่สำเร็จ: {e}")
        st.stop()

    st.success(f"📂 โหลดไฟล์สำเร็จ {len(df)} รายการ")
    st.dataframe(df.head(10), use_container_width=True)

    # -----------------------------
    # REQUIRED COLUMNS
    # -----------------------------
    required_cols = [
        "lot_no",
        "kanban_no",
        "model_name",
        "Harness_part_no",
        "wire_number",
        "wire_harness_code",
        "MC_A",
        "MC_B",
        "Twist_MC",
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"❌ ไฟล์ขาดคอลัมน์: {missing}")
        st.stop()

    # -----------------------------
    # CLEAN DATA
    # -----------------------------
    df = df.fillna("")
    df["kanban_no"] = df["kanban_no"].astype(str).str.strip()

    # 🔥 ตัดซ้ำในไฟล์เองก่อน (เอาแถวล่างสุด = ล่าสุด)
    df = df.drop_duplicates(subset=["kanban_no"], keep="last")

    # -----------------------------
    # CONFIRM
    # -----------------------------
    if not st.button("🚀 Upload to Supabase"):
        st.stop()

    # -----------------------------
    # UPLOAD
    # -----------------------------
    success = 0
    fail = 0
    errors = []

    with st.spinner("⏳ กำลังอัปโหลดข้อมูล..."):
        for i, row in df.iterrows():
            try:
                payload = {
                    "lot_no": str(row["lot_no"]).strip(),
                    "kanban_no": str(row["kanban_no"]).strip(),
                    "model_name": str(row["model_name"]).strip(),
                    "harness_part_no": str(row["Harness_part_no"]).strip(),
                    "wire_number": str(row["wire_number"]).strip(),
                    "wire_harness_code": str(row["wire_harness_code"]).strip(),
                    "mc_a": str(row["MC_A"]).strip(),
                    "mc_b": str(row["MC_B"]).strip(),
                    "twist_mc": str(row["Twist_MC"]).strip(),
                    "updated_at": pd.Timestamp.now(tz="Asia/Bangkok").strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }

                # 🔥 UPSERT: ถ้าซ้ำ kanban_no → แทนของเก่า
                supabase.table("lot_master").upsert(
                    payload,
                    on_conflict="kanban_no"
                ).execute()

                success += 1

            except Exception as e:
                fail += 1
                errors.append(
                    {
                        "kanban_no": row.get("kanban_no"),
                        "error": str(e)
                    }
                )

    # -----------------------------
    # RESULT
    # -----------------------------
    st.success(f"✅ Upload สำเร็จ {success} รายการ")
    if fail:
        st.error(f"❌ ผิดพลาด {fail} รายการ")
        st.dataframe(pd.DataFrame(errors).head(20))

    st.caption("📌 Logic: Duplicate kanban_no → keep latest record only")

# =====================================================
# 🧩 PART TRACKING (LOT / HARNESS)
# =====================================================
elif mode == "Part Tracking":

    st.header("🧩 Part Tracking (Lot / Harness)")

    c1, c2 = st.columns(2)
    f_lot = c1.text_input("Lot No")
    f_harness = c2.text_input("Harness Part No")

    if not f_lot and not f_harness:
        st.info("กรุณาใส่ Lot No หรือ Harness Part No อย่างน้อย 1 ช่อง")
        st.stop()

    if st.button("🔍 Load Data"):

        # =============================
        # RPC CALL
        # =============================
        res = supabase.rpc(
            "rpc_part_tracking_lot_harness",
            {
                "p_lot_no": f_lot.strip() if f_lot else None,
                "p_harness_part_no": f_harness.strip() if f_harness else None
            }
        ).execute()

        df = safe_df(res.data)

        if df.empty:
            st.warning("❌ ไม่พบข้อมูลตามเงื่อนไข")
            st.stop()

        # =============================
        # TIMEZONE (TH)
        # =============================
        df["Delivered At (GMT+7)"] = df["delivered_at"].apply(to_gmt7)
        df["Status"] = df["sent"].apply(
            lambda x: "Sent" if x else "Remaining"
        )

        # =============================
        # KPI
        # =============================
        total = len(df)
        sent = (df["sent"] == True).sum()
        remaining = total - sent

        k1, k2, k3 = st.columns(3)
        k1.metric("📦 Total", total)
        k2.metric("✅ Sent", sent)
        k3.metric("⏳ Remaining", remaining)

        st.divider()

        # =============================
        # FILTER STATUS
        # =============================
        status_filter = st.radio(
            "แสดงข้อมูล",
            ["ALL", "SENT", "REMAIN"],
            horizontal=True,
            format_func=lambda x: {
                "ALL": "📦 ทั้งหมด",
                "SENT": "✅ ส่งแล้ว",
                "REMAIN": "⏳ ยังไม่ส่ง"
            }[x]
        )

        if status_filter == "SENT":
            df = df[df["sent"] == True]
        elif status_filter == "REMAIN":
            df = df[df["sent"] == False]

        # =============================
        # DISPLAY TABLE
        # =============================
        st.dataframe(
            df[
                [
                    "lot_no",
                    "kanban_no",
                    "model_name",
                    "harness_part_no",
                    "wire_number",
                    "Status",
                    "Delivered At (GMT+7)"
                ]
            ].sort_values(
                by="Delivered At (GMT+7)",
                ascending=False,
                na_position="last"
            ),
            use_container_width=True,
            height=600
        )

        st.caption(
            "📊 Source: rpc_part_tracking_lot_harness | "
            "ข้อมูลจริงจาก Lot Master + Kanban Delivery"
        )























