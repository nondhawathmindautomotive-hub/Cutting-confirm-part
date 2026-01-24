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
# 📦 KANBAN DELIVERY LOG (FIXED PARAMS)
# =====================================================
elif mode == "Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    c1, c2, c3 = st.columns(3)
    c4, c5 = st.columns(2)

    f_kanban = c1.text_input("Kanban No.")
    f_lot    = c2.text_input("Lot No.")
    f_model  = c3.text_input("Model")
    f_part   = c4.text_input("Wire / Part No.")
    f_date   = c5.date_input("Scan Date", value=None)

    if st.button("🔍 Load Data"):

        try:
            # ✅ CALL RPC (ตรง signature เป๊ะ)
            res = supabase.rpc(
                "rpc_kanban_delivery_log",
                {
                    "p_kanban": f_kanban or None,
                    "p_lot": f_lot or None,
                    "p_model": f_model or None,
                    "p_part": f_part or None,
                    "p_scan_date": str(f_date) if f_date else None,
                }
            ).execute()

        except Exception as e:
            st.error("❌ เรียกข้อมูลไม่สำเร็จ")
            st.code(str(e))
            st.stop()

        df = pd.DataFrame(res.data or [])

        if df.empty:
            st.warning("❌ ไม่พบข้อมูลตามเงื่อนไข")
            st.stop()

        # =============================
        # TIMEZONE
        # =============================
        df["Delivered At (GMT+7)"] = pd.to_datetime(
            df["delivered_at"]
        ).dt.strftime("%Y-%m-%d %H:%M:%S")

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
        # TABLE
        # =============================
        st.dataframe(
            df[
                [
                    "lot_no",
                    "kanban_no",
                    "model_name",
                    "harness_part_no",
                    "wire_number",
                    "wire_harness_code",
                    "joint_a",
                    "joint_b",
                    "mc_a",
                    "mc_b",
                    "twist_mc",
                    "status",
                    "Delivered At (GMT+7)",
                ]
            ],
            use_container_width=True,
            height=700
        )

        st.caption(
            "📊 Source: lot_master + kanban_delivery (rpc_kanban_delivery_log)"
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































