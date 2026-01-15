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

def clean_series(s):
    return (
        pd.Series(s)
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

def norm(v):
    return str(v).strip() if v is not None else ""

# =====================================================
# 1) SCAN KANBAN (AUTO + STRICT JOINT)
# =====================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan Kanban")

    def confirm_scan():
        kanban = norm(st.session_state.scan)
        if not kanban:
            return

        now_ts = pd.Timestamp.now(tz="Asia/Bangkok").strftime("%Y-%m-%d %H:%M:%S")

        base = (
            supabase.table("lot_master")
            .select("kanban_no, model_name, lot_no, joint_a, joint_b")
            .eq("kanban_no", kanban)
            .limit(1)
            .execute()
            .data
        )

        if not base:
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban")
            st.session_state.scan = ""
            return

        row = base[0]
        model = norm(row["model_name"])
        lot = norm(row["lot_no"])
        joint_a = norm(row.get("joint_a"))
        joint_b = norm(row.get("joint_b"))

        is_joint = bool(joint_a or joint_b)

        # =========================
        # JOINT CIRCUIT
        # =========================
        if is_joint:
            rows = (
                supabase.table("lot_master")
                .select("kanban_no, joint_a, joint_b")
                .eq("model_name", model)
                .eq("lot_no", lot)
                .execute()
                .data
            )

            joint_list = []
            for r in rows:
                if joint_a and norm(r.get("joint_a")) == joint_a:
                    joint_list.append(norm(r["kanban_no"]))
                elif joint_b and norm(r.get("joint_b")) == joint_b:
                    joint_list.append(norm(r["kanban_no"]))

            joint_list = list(set(joint_list))

            exist = (
                supabase.table("kanban_delivery")
                .select("kanban_no")
                .in_("kanban_no", joint_list)
                .execute()
                .data
            )
            exist_set = {norm(x["kanban_no"]) for x in exist}

            # INSERT ใหม่
            to_insert = [
                {
                    "kanban_no": k,
                    "model_name": model,
                    "lot_no": lot,
                    "last_scanned_at": now_ts
                }
                for k in joint_list if k not in exist_set
            ]

            if to_insert:
                supabase.table("kanban_delivery").insert(to_insert).execute()

            # UPDATE ตัวที่มีอยู่แล้ว
            supabase.table("kanban_delivery").update(
                {"last_scanned_at": now_ts}
            ).in_("kanban_no", joint_list).execute()

            st.session_state.msg = (
                "success",
                f"""✅ Joint Scan สำเร็จ
- Model : {model}
- Lot   : {lot}
- Qty   : {len(joint_list)}"""
            )

            st.session_state.scan = ""
            return

        # =========================
        # NORMAL CIRCUIT
        # =========================
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

            st.session_state.msg = (
                "success",
                f"""🔄 Scan ซ้ำ (อัปเดตเวลา)
- Kanban : {kanban}
- Model  : {model}
- Lot    : {lot}"""
            )
            st.session_state.scan = ""
            return

        # INSERT ใหม่
        supabase.table("kanban_delivery").insert({
            "kanban_no": kanban,
            "model_name": model,
            "lot_no": lot,
            "last_scanned_at": now_ts
        }).execute()

        st.session_state.msg = (
            "success",
            f"""✅ ส่ง Kanban สำเร็จ
- Kanban : {kanban}
- Model  : {model}
- Lot    : {lot}"""
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
# 2) MODEL KANBAN STATUS (CSV-PROOF / COUNT CORRECT)
# =====================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    c1, c2 = st.columns(2)
    model_filter = c1.text_input("Model (ไม่จำเป็น)")
    lot_filter = c2.text_input("Lot")

    # -----------------------------
    # LOAD LOT MASTER (USE REAL COLUMN)
    # -----------------------------
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("model_name, kanban_no, lot_no")
        .execute()
        .data
    )

    if lot_df.empty:
        st.warning("ไม่พบข้อมูล lot_master")
        st.stop()

    # -----------------------------
    # CLEAN DATA
    # -----------------------------
    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()

    lot_df["lot_no"] = (
        lot_df["lot_no"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    lot_df["model_name"] = (
        lot_df["model_name"]
        .astype(str)
        .str.strip()
    )

    # -----------------------------
# FILTER
# -----------------------------
    if lot_filter:
        lot_df = lot_df[
            lot_df["lot_no"]
            .astype(str)
            .str.strip()
            .str.contains(lot_filter.strip(), case=False, na=False)
        ]

    if model_filter:
        lot_df = lot_df[
            lot_df["model_name"]
            .str.contains(model_filter.strip(), case=False, na=False)
        ]

    # -----------------------------
    # UNIQUE KANBAN (CRITICAL)
    # -----------------------------
    lot_df = lot_df.drop_duplicates(
        subset=["model_name", "lot_no", "kanban_no"]
    )
    # =====================================================
    # 🔒 FORCE SCHEMA (PREVENT KeyError 100%)
    # =====================================================
    required_cols = ["kanban_no", "model_name", "lot_no"]

    for c in required_cols:
        if c not in lot_df.columns:
            lot_df[c] = ""

    lot_df = lot_df[required_cols]

    # -----------------------------
    # LOAD DELIVERY (SAFE)
    # -----------------------------
    del_raw = (
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data
    )

    if del_raw:
        del_df = pd.DataFrame(del_raw)
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
        del_df["sent"] = 1
    else:
        # 🔒 กัน KeyError 100%
        del_df = pd.DataFrame(columns=["kanban_no", "sent"])

    # -----------------------------
    # MERGE
    # -----------------------------
    df = lot_df.merge(
        del_df[["kanban_no", "sent"]],
        on="kanban_no",
        how="left"
    )
    df["sent"] = df["sent"].fillna(0).astype(int)
    # -----------------------------
    # SUMMARY (✔ EXACT CSV COUNT)
    # -----------------------------
    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(
            Total_Kanban=("kanban_no", "nunique"),
            Sent=("sent", "sum")
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total_Kanban"] - summary["Sent"]

    # -----------------------------
    # DISPLAY
    # -----------------------------
    st.dataframe(
        summary.sort_values(["model_name", "lot_no"]),
        use_container_width=True
    )

    # -----------------------------
    # DETAIL (PROOF 472)
    # -----------------------------
    with st.expander("📋 รายการ Kanban ที่ถูกนำมานับ"):
        st.dataframe(
            df.sort_values(["model_name", "kanban_no"]),
            use_container_width=True
        )


# =====================================================
# 3) TRACKING SEARCH (GMT+7 + JOINT)
# =====================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    c1, c2, c3 = st.columns(3)
    c4, c5, c6 = st.columns(3)

    kanban = c1.text_input("Kanban No.")
    model = c2.text_input("Model")
    wire = c3.text_input("Wire Number")
    subp = c4.text_input("Subpackage")
    harness = c5.text_input("Wire Harness Code")
    lot = c6.text_input("Lot No.")

    query = supabase.table("lot_master").select(
        "kanban_no, model_name, wire_number, subpackage_number, wire_harness_code, lot_no, joint_a, joint_b"
    )

    if kanban:
        query = query.ilike("kanban_no", f"%{kanban}%")
    if model:
        query = query.ilike("model_name", f"%{model}%")
    if wire:
        query = query.ilike("wire_number", f"%{wire}%")
    if subp:
        query = query.ilike("subpackage_number", f"%{subp}%")
    if harness:
        query = query.ilike("wire_harness_code", f"%{harness}%")
    if lot:
        query = query.ilike("lot_no", f"%{lot}%")

    lot_df = safe_df(query.execute().data)

# =============================
# LOAD DELIVERY TIME
# =============================
    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, last_scanned_at")
        .execute()
        .data,
        ["kanban_no", "created_at", "last_scanned_at"]
    )

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()

        # ใช้ last_scanned_at ก่อน ถ้าไม่มี ค่อยใช้ created_at
        del_df["Delivered at (GMT+7)"] = (
            del_df["last_scanned_at"]
            .fillna(del_df["created_at"])
            .apply(to_gmt7)
        )

        del_df = del_df.drop(columns=["created_at", "last_scanned_at"])
    else:
        del_df = pd.DataFrame(
            columns=["kanban_no", "Delivered at (GMT+7)"]
        )


# =============================
# MERGE
# =============================
    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()

    df = lot_df.merge(
        del_df,
        on="kanban_no",
        how="left"
    )

    st.dataframe(df, use_container_width=True)

# =====================================================
# 4) 🔐📤 Upload Lot Master (FIXED & CLOSED)
# =====================================================
elif mode == "🔐📤 Upload Lot Master":

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("🔒 สำหรับ Planner เท่านั้น")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])
    if not file:
        st.info("กรุณาอัปโหลดไฟล์")
        st.stop()

    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)

    required = [
        "lot_no",
        "kanban_no",
        "model_name",
        "wire_number",
        "subpackage_number",
        "wire_harness_code",
        "joint_a",
        "joint_b",
    ]

    missing = set(required) - set(df.columns)
    if missing:
        st.error(f"❌ ขาด column: {missing}")
        st.stop()

    # CLEAN DATA
    df = df[required].copy().fillna("")
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()

    df["lot_no"] = df["lot_no"].str.replace(r"\.0$", "", regex=True)

    st.dataframe(df.head(), use_container_width=True)

    if st.button("🚀 Upload เข้า Lot Master"):
        supabase.table("lot_master").insert(
            df.to_dict(orient="records")
        ).execute()

        st.success(f"✅ Upload สำเร็จ {len(df)} รายการ")

# =====================================================
# 5) 📦 KANBAN DELIVERY LOG (LOT MASTER BASED - FINAL)
# =====================================================
elif mode == "📦 Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    # -----------------------------
    # SEARCH INPUT
    # -----------------------------
    c1, c2, c3 = st.columns(3)
    f_kanban = c1.text_input("Kanban No. (ค้นหาบางส่วนได้)")
    f_model  = c2.text_input("Model (ค้นหาบางส่วนได้)")
    f_lot    = c3.text_input("Lot No.")

    st.divider()

    # -----------------------------
    # LOAD LOT MASTER (NO 1000 LIMIT)
    # -----------------------------
    lot_raw = (
        supabase.table("lot_master")
        .select("kanban_no, model_name, lot_no")
        .range(0, 50000)
        .execute()
        .data
    )

    lot_df = safe_df(lot_raw)

    if lot_df.empty:
        st.error("❌ ไม่พบข้อมูล lot_master")
        st.stop()

    # -----------------------------
    # HARD NORMALIZE (โรงงานจริง)
    # -----------------------------
    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["model_name"] = lot_df["model_name"].astype(str).str.strip()

    lot_df["lot_no"] = (
        lot_df["lot_no"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"[^0-9A-Za-z]", "", regex=True)  # 🔥 ตัด space, \r, -
        .str.strip()
    )

    # -----------------------------
    # APPLY FILTER
    # -----------------------------
    if f_lot:
        lot_key = (
            f_lot.strip()
            .replace(" ", "")
            .replace("-", "")
        )
        lot_df = lot_df[
            lot_df["lot_no"].str.contains(
                lot_key, case=False, na=False
            )
        ]

    if f_model:
        lot_df = lot_df[
            lot_df["model_name"]
            .str.contains(f_model.strip(), case=False, na=False)
        ]

    if f_kanban:
        lot_df = lot_df[
            lot_df["kanban_no"]
            .str.contains(f_kanban.strip(), case=False, na=False)
        ]

    if lot_df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
        st.stop()

    # -----------------------------
    # UNIQUE = 1 KANBAN = 1 CIRCUIT
    # -----------------------------
    lot_df = lot_df.drop_duplicates(subset=["kanban_no"])

    # -----------------------------
    # LOAD DELIVERY TABLE (NO LIMIT)
    # -----------------------------
    del_raw = (
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, last_scanned_at")
        .range(0, 50000)
        .execute()
        .data
    )

    del_df = safe_df(
        del_raw,
        ["kanban_no", "created_at", "last_scanned_at"]
    )

    if not del_df.empty:
        del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()

        del_df["sent"] = (
            del_df["created_at"].notna()
            | del_df["last_scanned_at"].notna()
        ).astype(int)

        del_df["Delivered At (GMT+7)"] = (
            del_df["last_scanned_at"]
            .fillna(del_df["created_at"])
            .apply(to_gmt7)
        )

        del_df = del_df[
            ["kanban_no", "sent", "Delivered At (GMT+7)"]
        ]
    else:
        del_df = pd.DataFrame(
            columns=["kanban_no", "sent", "Delivered At (GMT+7)"]
        )

    # -----------------------------
    # MERGE (LOT MASTER = TRUTH)
    # -----------------------------
    df = lot_df.merge(
        del_df,
        on="kanban_no",
        how="left"
    )

    df["sent"] = df["sent"].fillna(0).astype(int)

    # -----------------------------
    # KPI SUMMARY (REAL COUNT)
    # -----------------------------
    total = len(df)
    sent = int(df["sent"].sum())
    remaining = total - sent

    k1, k2, k3 = st.columns(3)
    k1.metric("📦 Total (Lot Master)", total)
    k2.metric("✅ Sent (kanban_delivery)", sent)
    k3.metric("⏳ Remaining", remaining)

    # -----------------------------
    # DISPLAY
    # -----------------------------
    st.dataframe(
        df.sort_values(
            by="Delivered At (GMT+7)",
            ascending=False,
            na_position="last"
        ),
        use_container_width=True
    )

    st.caption(f"📊 แสดงผลทั้งหมด {len(df)} วงจร")







