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
def match_joint(row, base):
    """
    base = แถวที่ scan
    row  = แถว candidate
    """
    ja = norm(base.get("joint_a"))
    jb = norm(base.get("joint_b"))

    r_ja = norm(row.get("joint_a"))
    r_jb = norm(row.get("joint_b"))

    # มี A + B → ต้องตรงทั้งคู่
    if ja and jb:
        return r_ja == ja and r_jb == jb

    # มีเฉพาะ A
    if ja:
        return r_ja == ja

    # มีเฉพาะ B
    if jb:
        return r_jb == jb

    return False

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
# 1) SCAN KANBAN (WIRE HARNESS COMPLETE VERSION)
# =====================================================
if mode == "Scan Kanban":

    st.header("✅ Scan Kanban")

    def confirm_scan():
        kanban = norm(st.session_state.scan)
        if not kanban:
            return

        # เวลาไทย
        now_ts = pd.Timestamp.now(tz="Asia/Bangkok").strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # -------------------------------------------------
        # 1) หา BASE ROW จาก kanban ที่ scan
        # -------------------------------------------------
        base_res = (
            supabase.table("lot_master")
            .select(
                "kanban_no, model_name, lot_no, wire_number, wire_harness_code"
            )
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
            .data
        )

        if not base_res:
            st.session_state.msg = (
                "error",
                "❌ ไม่พบ Kanban ใน Lot Master"
            )
            st.session_state.scan = ""
            return

        base = base_res[0]

        lot_no = norm(base["lot_no"])
        model = norm(base["model_name"])
        wire_number = norm(base.get("wire_number"))
        harness_code = norm(base.get("wire_harness_code"))

        if not harness_code:
            st.session_state.msg = (
                "error",
                "❌ ไม่พบ wire_harness_code"
            )
            st.session_state.scan = ""
            return

        # -------------------------------------------------
        # 2) ดึงทุก kanban ที่ lot + wire_harness_code เดียวกัน
        # -------------------------------------------------
        all_rows = (
            supabase.table("lot_master")
            .select("kanban_no")
            .eq("lot_no", lot_no)
            .eq("wire_harness_code", harness_code)
            .execute()
            .data
        )

        all_kanbans = [
            norm(r["kanban_no"])
            for r in all_rows
        ]

        if not all_kanbans:
            st.session_state.msg = (
                "warning",
                "⚠️ ไม่พบชุด wire_harness_code ที่ผูกกัน"
            )
            st.session_state.scan = ""
            return

        # -------------------------------------------------
        # 3) เช็คว่าใบไหนส่งไปแล้ว
        # -------------------------------------------------
        sent_rows = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .in_("kanban_no", all_kanbans)
            .execute()
            .data
        )

        sent_set = {
            norm(r["kanban_no"])
            for r in sent_rows
        }

        # -------------------------------------------------
        # 4) INSERT เฉพาะใบที่ยังไม่เคยส่ง
        # -------------------------------------------------
        to_insert = [
            {
                "kanban_no": k,
                "model_name": model,
                "lot_no": lot_no,
                "wire_number": wire_number,
                "last_scanned_at": now_ts
            }
            for k in all_kanbans
            if k not in sent_set
        ]

        if to_insert:
            supabase.table("kanban_delivery") \
                .insert(to_insert) \
                .execute()

            st.session_state.msg = (
                "success",
                f"✅ Completed {len(to_insert)} Kanban "
                f"(Wire Harness: {harness_code})"
            )
        else:
            st.session_state.msg = (
                "info",
                "ℹ️ ชุดนี้ถูกส่งครบแล้ว"
            )

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
# 📦 LOT KANBAN SUMMARY (SAFE / NO ERROR)
# =====================================================
elif mode == "Lot Kanban Summary":

    st.header("📦 Lot Kanban Summary")

    # ===============================
    # FILTER ZONE
    # ===============================
    f1, f2, f3, f4 = st.columns(4)

    with f1:
        f_lot_no = st.text_input("Lot No.")

    with f2:
        f_model = st.text_input("Model")

    with f3:
        f_harness = st.text_input("Harness Code")

    with f4:
        f_wire = st.text_input("Wire / Part No.")

    f5, f6, f7 = st.columns(3)

    with f5:
        date_from = st.date_input("From Date", value=None)

    with f6:
        date_to = st.date_input("To Date", value=None)

    with f7:
        status_filter = st.selectbox(
            "Status",
            ["ALL", "COMPLETED", "REMAINING"],
        )

    search_text = st.text_input(
        "🔍 Search (Kanban / Wire / Model / Harness)",
        placeholder="พิมพ์อะไรก็ได้ที่ต้องการค้นหา",
    )

    show_limit = st.selectbox(
        "📊 Show rows",
        [50, 100, 300, 1000],
        index=1,
    )

    st.divider()

    # ===============================
    # CALL RPC (SAFE PARAM)
    # ===============================
    try:
        res = supabase.rpc(
            "rpc_lot_kanban_summary_safe",
            {
                "p_lot_no": f_lot_no.strip() or None,
                "p_model": f_model.strip() or None,
                "p_harness_code": f_harness.strip() or None,
                "p_wire": f_wire.strip() or None,
                "p_from": str(date_from) if date_from else None,
                "p_to": str(date_to) if date_to else None,
                "p_status": status_filter,
            },
        ).execute()
    except Exception as e:
        st.error("❌ RPC Error")
        st.code(str(e))
        st.stop()

    df = safe_df(res.data)

    if df.empty:
        st.warning("ไม่พบข้อมูล")
        st.stop()

    # ===============================
    # SAFE COLUMN NORMALIZE
    # ===============================
    if "status" not in df.columns:
        df["status"] = "UNKNOWN"

    if "delivered_at" in df.columns:
        df["delivered_at"] = (
            pd.to_datetime(df["delivered_at"], errors="coerce", utc=True)
            .dt.tz_convert("Asia/Bangkok")
        )
    else:
        df["delivered_at"] = pd.NaT

    # ===============================
    # GLOBAL SEARCH
    # ===============================
    if search_text:
        kw = search_text.lower().strip()
        df = df[
            df.apply(
                lambda r: kw in " ".join(
                    str(v).lower()
                    for v in r.values
                    if pd.notna(v)
                ),
                axis=1,
            )
        ]

    # ===============================
    # STATUS FILTER (DOUBLE SAFE)
    # ===============================
    if status_filter != "ALL":
        df = df[df["status"] == status_filter]

    # ===============================
    # KPI
    # ===============================
    total = len(df)
    sent = len(df[df["status"] == "COMPLETED"])
    remain = total - sent

    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total", total)
    k2.metric("✅ Sent", sent)
    k3.metric("⏳ Remaining", remain)

    st.divider()

    # ===============================
    # COLUMN CONTROL
    # ===============================
    expected_cols = [
        "lot_no",
        "kanban_no",
        "model_name",
        "wire_number",
        "cable_name",
        "wire_length_mm",
        "subpackage_number",
        "wire_harness_code",
        "status",
        "delivered_at",
    ]

    df = df[[c for c in expected_cols if c in df.columns]]

    df = df.rename(
        columns={
            "lot_no": "Lot",
            "kanban_no": "Kanban No",
            "model_name": "Model",
            "wire_number": "Wire No",
            "cable_name": "Cable Name",
            "wire_length_mm": "Wire Length (mm)",
            "subpackage_number": "Subpackage",
            "wire_harness_code": "Harness Code",
            "status": "Status",
            "delivered_at": "Delivered At (GMT+7)",
        }
    )

    # ===============================
    # DISPLAY
    # ===============================
    st.dataframe(
        df.head(show_limit),
        use_container_width=True,
        hide_index=True,
        height=650,
    )

    st.caption(
        "📊 Source: rpc_lot_kanban_summary_safe | "
        "Lot Master + Kanban Delivery"
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




































