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
# SCAN RESULT STYLE (BIG SCREEN)
# =====================================================
st.markdown("""
<style>
.scan-result {
    font-size: 42px;
    font-weight: 800;
    padding: 32px;
    border-radius: 18px;
    text-align: center;
    line-height: 1.5;
    margin-top: 24px;
}

/* 🟩 สแกนใหม่ ไม่มีพ่วง */
.scan-green {
    background-color: #e6f9f0;
    color: #065f46;
    border: 4px solid #10b981;
}

/* 🟦 สแกนใหม่ มีพ่วง */
.scan-blue {
    background-color: #e8f1ff;
    color: #1e3a8a;
    border: 4px solid #3b82f6;
}

/* 🟧 สแกนซ้ำ */
.scan-orange {
    background-color: #fff7ed;
    color: #9a3412;
    border: 4px solid #fb923c;
}
</style>
""", unsafe_allow_html=True)


# =====================================================
# TIMEZONE (GMT+7)
# =====================================================
def to_gmt7(ts):
    if not ts:
        return ""
    return (
        pd.to_datetime(ts, utc=True)          # บอกว่าเป็น UTC
          .tz_convert("Asia/Bangkok")         # แปลงเป็นเวลาไทย
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
        "Delivery Plan",
        "Kanban Delivery Log",
        "Upload Lot Master",
        "Part Tracking", 
    ]
)

# =====================================================
# 1) SCAN KANBAN
# =====================================================
# 1) SCAN KANBAN
# =====================================================
if mode == "Scan Kanban":

    st.header("✅ Scan Kanban")

    def confirm_scan():
        kanban = norm(st.session_state.scan)
        if not kanban:
            return

        # ------------------------------------------------
        # STEP 0 : ตรวจว่า Kanban มีอยู่ใน lot_master ไหม
        # ------------------------------------------------
        lot_exist = (
            supabase.table("lot_master")
            .select("kanban_no")
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
            .data
        )

        if not lot_exist:
            st.session_state.msg = (
                "orange",
                "❌ ไม่พบข้อมูล Kanban ใน Lot Master<br>"
                "กรุณาติดต่อหัวหน้างานเพื่อแก้ไข"
            )
            st.session_state.scan = ""
            return

        # ------------------------------------------------
        # STEP 1 : เช็คว่าเคย Complete แล้วหรือยัง
        # ------------------------------------------------
        exist = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
            .data
        )

        # 🟧 สแกนซ้ำ → หยุดทันที (ไม่เรียก RPC)
        if exist:
            st.session_state.msg = (
                "orange",
                "⚠️ Kanban นี้ถูกสแกนแล้ว<br>"
                "📦 ไม่สามารถส่งซ้ำได้"
            )
            st.session_state.scan = ""
            return

        # ------------------------------------------------
        # STEP 2 : เรียก RPC bundle (เฉพาะสแกนใหม่)
        # ------------------------------------------------
        rpc_res = supabase.rpc(
            "rpc_complete_kanban_bundle",
            {"p_kanban_no": kanban}
        ).execute()

        bundle_df = pd.DataFrame(rpc_res.data or [])
        bundle_count = len(bundle_df)

        # ------------------------------------------------
        # STEP 3 : MESSAGE + COLOR LOGIC
        # ------------------------------------------------
        if bundle_count > 1:
            # 🟦 สแกนใหม่ + มีพ่วง
            st.session_state.msg = (
                "blue",
                f"✅ ส่ง Kanban สำเร็จ<br>"
                f"🧩 ชุดพ่วง ถูก Complete พร้อมกัน {bundle_count} ใบ"
            )
        else:
            # 🟩 สแกนใหม่ + ไม่มีพ่วง
            st.session_state.msg = (
                "green",
                "✅ ส่ง Kanban สำเร็จ<br>"
                "📦 Kanban เดี่ยว (ไม่มีพ่วง)"
            )

        # clear ช่อง scan
        st.session_state.scan = ""

    # =============================
    # INPUT
    # =============================
    st.text_input(
        "Scan Kanban No.",
        key="scan",
        on_change=confirm_scan
    )

    # =============================
    # SCAN RESULT (BIG & COLOR)
    # =============================
    if "msg" in st.session_state:
        color, text = st.session_state.msg

        css_map = {
            "green": "scan-green",
            "blue": "scan-blue",
            "orange": "scan-orange",
        }

        st.markdown(
            f"""
            <div class="scan-result {css_map[color]}">
                {text}
            </div>
            """,
            unsafe_allow_html=True
        )

        del st.session_state.msg

# =====================================================
# 2) LOT KANBAN SUMMARY (SOURCE OF TRUTH)
# =====================================================
elif mode == "Lot Kanban Summary":

    st.header("📊 Lot Kanban Summary")

    c1, c2, c3, c4 = st.columns(4)
    f_lot   = c1.text_input("Lot No. (ต้องตรง 100%)")
    f_model = c2.text_input("Model")
    f_wire  = c3.text_input("Wire Number")
    f_part  = c4.text_input("Harness Part No")

    f_status = st.selectbox(
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

    # =============================
    # KPI (ใช้ข้อมูลจริงจาก kanban_delivery)
    # =============================
    kpi_res = supabase.rpc(
        "rpc_part_kpi",
        {
            "p_lot_no": f_lot.strip(),
            "p_wire_number": f_wire.strip() or None,
            "p_harness_part_no": f_part.strip() or None
        }
    ).execute()

    if not kpi_res.data:
        st.warning("ไม่พบข้อมูล KPI")
        st.stop()

    kpi = kpi_res.data[0]

    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total Kanban", int(kpi["total_kanban"]))
    k2.metric("✅ Sent", int(kpi["sent_kanban"]))
    k3.metric("⏳ Remaining", int(kpi["remaining_kanban"]))

    st.divider()

    # =============================
    # DETAIL TABLE
    # =============================
    res = supabase.rpc(
        "rpc_lot_kanban_circuits",
        {
            "p_lot_no": f_lot.strip(),
            "p_model": f_model.strip() or None,
            "p_status": f_status,
            "p_wire_number": f_wire.strip() or None,
            "p_part_no": f_part.strip() or None
        }
    ).execute()

    df = pd.DataFrame(res.data)

    if df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    df["Delivered At (GMT+7)"] = df["delivered_at_gmt7"].astype(str)

    st.dataframe(
        df[
            [
                "lot_no",
                "kanban_no",
                "model_name",
                "harness_part_no",
                "wire_number",
                "wire_harness_code",
                "subpackage_number",
                "cable_name",
                "wire_length_mm",
                "joint_a",
                "joint_b",
                "mc_a",
                "mc_b",
                "twist_mc",
                "status",
                "Delivered At (GMT+7)"
            ]
        ],
        use_container_width=True,
        height=650
    )

    st.caption("📊 Source: kanban_delivery + lot_master (RPC)")

# =====================================================
# =====================================================
# =====================================================
# 📅 DELIVERY PLAN (Plan vs Actual)
# =====================================================
if mode == "Delivery Plan":

    st.header("📅 Delivery Plan (Plan vs Actual)")

    # -------------------------
    # 🔍 SEARCH
    # -------------------------
    keyword = st.text_input(
        "🔍 ค้นหา (Lot / Part / Model)",
        placeholder="พิมพ์ lot, part number หรือ model"
    )

    # -------------------------
    # 📅 DATE FILTER
    # -------------------------
    c1, c2 = st.columns(2)
    with c1:
        date_from = st.date_input("📅 Plan Delivery From")
    with c2:
        date_to = st.date_input("📅 Plan Delivery To")

    # -------------------------
    # LOAD DATA (CLIENT SAFE)
    # -------------------------
    res = (
        supabase
        .table("v_plan_vs_actual")
        .select("*")
        .execute()
    )

    df = pd.DataFrame(res.data or [])

    if df.empty:
        st.warning("⚠️ ไม่พบข้อมูล Delivery Plan")
        st.stop()

    # -------------------------
    # DATE CLEAN (สำคัญมาก)
    # -------------------------
    df["plan_delivery_date"] = pd.to_datetime(
        df["plan_delivery_date"],
        errors="coerce"
    )

    date_from_dt = pd.to_datetime(date_from)
    date_to_dt   = pd.to_datetime(date_to)

    df = df[
        (df["plan_delivery_date"] >= date_from_dt) &
        (df["plan_delivery_date"] <= date_to_dt)
    ]

    # -------------------------
    # KEYWORD FILTER
    # -------------------------
    if keyword:
        kw = keyword.lower()
        df = df[
            df["lot_no"].astype(str).str.lower().str.contains(kw) |
            df["part_number"].astype(str).str.lower().str.contains(kw) |
            df["model_level"].astype(str).str.lower().str.contains(kw)
        ]

    if df.empty:
        st.warning("⚠️ ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    # -------------------------
    # CALCULATION
    # -------------------------
    df["actual_qty"] = df["actual_qty"].fillna(0)

    df["progress_pct"] = (
        df["actual_qty"] / df["plan_qty"] * 100
    ).round(1)

    df["delivery_status"] = df.apply(
        lambda r:
            "🟢 Completed" if r["actual_qty"] >= r["plan_qty"]
            else "🟡 In Progress" if r["actual_qty"] > 0
            else "🔴 Not Start",
        axis=1
    )

    status_order = {
        "🔴 Not Start": 0,
        "🟡 In Progress": 1,
        "🟢 Completed": 2
    }
    df["status_order"] = df["delivery_status"].map(status_order)

    # -------------------------
    # SORT (ใช้ชื่อคอลัมน์จริง)
    # -------------------------
    df = df.sort_values(
        by=["status_order", "plan_delivery_date", "lot_no"],
        ascending=[True, True, True]
    )

    # -------------------------
    # KPI
    # -------------------------
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Plan Qty", int(df["plan_qty"].sum()))
    c2.metric("✅ Actual Qty", int(df["actual_qty"].sum()))

    overall = (
        df["actual_qty"].sum()
        / df["plan_qty"].sum() * 100
        if df["plan_qty"].sum() > 0 else 0
    )
    c3.metric("📊 Achievement", f"{overall:.1f}%")

    st.divider()

    # -------------------------
    # TABLE
    # -------------------------
    st.dataframe(
        df[
            [
                "delivery_status",
                "lot_no",
                "part_number",
                "model_level",
                "plan_qty",
                "actual_qty",
                "progress_pct",
                "plan_delivery_date",
                "last_delivered_at",
            ]
        ],
        use_container_width=True,
        height=520
    )

    st.caption("📊 Source: v_plan_vs_actual | client-side filter (safe)")




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
# =====================================================
# 5) UPLOAD LOT MASTER (SAFE / PRODUCTION VERSION)
# =====================================================
elif mode == "Upload Lot Master":

    st.header("🔐 Upload Lot Master (Safe Replace)")

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

    st.success(f"📂 โหลดไฟล์สำเร็จ {len(df)} แถว")

    # -----------------------------
    # NORMALIZE HEADER (สำคัญมาก)
    # -----------------------------
    df.columns = (
        df.columns
          .str.strip()
          .str.lower()
    )

    # -----------------------------
    # REQUIRED COLUMNS (ตรง DB)
    # -----------------------------
    required_cols = [
        "lot_no",
        "kanban_no",
        "model_name",
        "harness_part_no",
        "wire_number",
        "wire_harness_code",
        "mc_a",
        "mc_b",
        "twist_mc",
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

    # -----------------------------
    # DEDUPLICATE (เลือกแถวที่ข้อมูลครบที่สุด)
    # -----------------------------
    def completeness_score(r):
        return sum(
            1 for c in required_cols
            if str(r.get(c, "")).strip() != ""
        )

    df["_score"] = df.apply(completeness_score, axis=1)

    df = (
        df.sort_values("_score", ascending=False)
          .drop_duplicates(subset=["kanban_no"], keep="first")
          .drop(columns="_score")
    )

    st.info(f"🧹 หลังตัดซ้ำ เหลือ {len(df)} kanban")
    st.dataframe(df.head(10), use_container_width=True)

    # -----------------------------
    # CONFIRM
    # -----------------------------
    if not st.button("🚀 Upload to Supabase"):
        st.stop()

    # -----------------------------
    # LOAD EXISTING DATA (เฉพาะ kanban ที่ชน)
    # -----------------------------
    kanban_list = df["kanban_no"].tolist()

    existing = (
        supabase.table("lot_master")
        .select(
            "kanban_no, lot_no, model_name, harness_part_no, wire_number, wire_harness_code, mc_a, mc_b, twist_mc"
        )
        .in_("kanban_no", kanban_list)
        .execute()
        .data
    )

    existing_map = {r["kanban_no"]: r for r in existing}

    # -----------------------------
    # SAFE UPSERT
    # -----------------------------
    success = 0
    skipped = 0

    with st.spinner("⏳ กำลังอัปโหลดข้อมูล..."):
        for _, row in df.iterrows():

            new_score = completeness_score(row)
            old = existing_map.get(row["kanban_no"])

            old_score = 0
            if old:
                old_score = sum(
                    1 for v in old.values()
                    if v not in ("", None)
                )

            # ❌ ข้อมูลใหม่แย่กว่า → ข้าม
            if old and new_score < old_score:
                skipped += 1
                continue

            payload = {
                "lot_no": str(row["lot_no"]).strip(),
                "kanban_no": str(row["kanban_no"]).strip(),
                "model_name": str(row["model_name"]).strip(),
                "harness_part_no": str(row["harness_part_no"]).strip(),
                "wire_number": str(row["wire_number"]).strip(),
                "wire_harness_code": str(row["wire_harness_code"]).strip(),
                "mc_a": str(row["mc_a"]).strip(),
                "mc_b": str(row["mc_b"]).strip(),
                "twist_mc": str(row["twist_mc"]).strip(),
                "updated_at": pd.Timestamp.now(
                    tz="Asia/Bangkok"
                ).strftime("%Y-%m-%d %H:%M:%S"),
            }

            supabase.table("lot_master").upsert(
                payload,
                on_conflict="kanban_no"
            ).execute()

            success += 1

    # -----------------------------
    # RESULT
    # -----------------------------
    st.success(f"✅ Upload สำเร็จ {success} kanban")
    if skipped:
        st.warning(f"⏭️ ข้าม {skipped} kanban (ข้อมูลเดิมครบกว่า)")

    st.caption(
        "📌 Logic: kanban ซ้ำ → ใช้แถวที่ข้อมูลครบกว่า | ไม่ลบของเดิม"
    )

# =====================================================
# 📅 DELIVERY PLAN (Plan vs Actual)
# =====================================================
# =====================================================
# 📅 DELIVERY PLAN (Plan vs Actual) — CLIENT SAFE
# =====================================================
if mode == "Delivery Plan":

    st.header("📅 Delivery Plan (Plan vs Actual)")

    # -------------------------
    # 🔍 SEARCH
    # -------------------------
    keyword = st.text_input(
        "🔍 ค้นหา (Lot / Part / Model)",
        placeholder="พิมพ์ lot, part number หรือ model"
    )

    # -------------------------
    # 📅 DATE FILTER
    # -------------------------
    c1, c2 = st.columns(2)
    with c1:
        date_from = st.date_input("📅 Plan Delivery From")
    with c2:
        date_to = st.date_input("📅 Plan Delivery To")

    # -------------------------
    # LOAD ALL DATA (NO FILTER IN SUPABASE)
    # -------------------------
    res = (
        supabase
        .table("v_plan_vs_actual")
        .select("*")
        .execute()
    )

    df = pd.DataFrame(res.data or [])

    if df.empty:
        st.warning("⚠️ ไม่พบข้อมูล Delivery Plan")
        st.stop()

# DATE CLEAN
    df["plan_delivery_date"] = pd.to_datetime(
        df["plan_delivery_date"],
        errors="coerce"
    )

    date_from_dt = pd.to_datetime(date_from)
    date_to_dt   = pd.to_datetime(date_to)

    df = df[
        (df["plan_delivery_date"] >= date_from_dt) &
        (df["plan_delivery_date"] <= date_to_dt)
    ]

    # -------------------------
    # KEYWORD FILTER
    # -------------------------
    if keyword:
        kw = keyword.lower()
        df = df[
            df["lot_no"].astype(str).str.lower().str.contains(kw) |
            df["part_number"].astype(str).str.lower().str.contains(kw) |
            df["model_level"].astype(str).str.lower().str.contains(kw)
        ]

    if df.empty:
        st.warning("⚠️ ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    # -------------------------
    # CALCULATION
    # -------------------------
    df["actual_qty"] = df["actual_qty"].fillna(0)

    df["progress_pct"] = (
        df["actual_qty"] / df["plan_qty"] * 100
    ).round(1)

    df["delivery_status"] = df.apply(
        lambda r:
            "🟢 Completed" if r["actual_qty"] >= r["plan_qty"]
            else "🟡 In Progress" if r["actual_qty"] > 0
            else "🔴 Not Start",
        axis=1
    )

    status_order = {
        "🔴 Not Start": 0,
        "🟡 In Progress": 1,
        "🟢 Completed": 2
    }
    df["status_order"] = df["delivery_status"].map(status_order)

    # -------------------------
    # SORT
    # -------------------------
    df = df.sort_values(
        by=["status_order", "plan_delivery_dt", "lot_no"],
        ascending=[True, True, True]
    )

    # -------------------------
    # KPI
    # -------------------------
    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Plan Qty", int(df["plan_qty"].sum()))
    c2.metric("✅ Actual Qty", int(df["actual_qty"].sum()))

    overall = (
        df["actual_qty"].sum()
        / df["plan_qty"].sum() * 100
        if df["plan_qty"].sum() > 0 else 0
    )
    c3.metric("📊 Achievement", f"{overall:.1f}%")

    st.divider()

    # -------------------------
    # TABLE
    # -------------------------
    st.dataframe(
        df[
            [
                "delivery_status",
                "lot_no",
                "part_number",
                "model_level",
                "plan_qty",
                "actual_qty",
                "progress_pct",
                "plan_delivery_dt",
                "last_delivered_at",
            ]
        ],
        use_container_width=True,
        height=520
    )

    st.caption("📊 Source: v_plan_vs_actual | client-safe (no supabase filter)")

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
























































