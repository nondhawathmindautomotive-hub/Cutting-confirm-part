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

        now_ts = pd.Timestamp.now(
            tz="Asia/Bangkok"
        ).strftime("%Y-%m-%d %H:%M:%S")

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
        lot = norm_lot(row["lot_no"])
        joint_a = norm(row.get("joint_a"))
        joint_b = norm(row.get("joint_b"))

        is_joint = bool(joint_a or joint_b)

        # ---------- JOINT ----------
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
            exist_set = {x["kanban_no"] for x in exist}

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

            supabase.table("kanban_delivery").update(
                {"last_scanned_at": now_ts}
            ).in_("kanban_no", joint_list).execute()

            st.success(f"✅ Joint Scan สำเร็จ | Qty = {len(joint_list)}")
            st.session_state.scan = ""
            return

        # ---------- NORMAL ----------
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
            st.session_state.scan = ""
            return

        supabase.table("kanban_delivery").insert({
            "kanban_no": kanban,
            "model_name": model,
            "lot_no": lot,
            "last_scanned_at": now_ts
        }).execute()

        st.success("✅ ส่ง Kanban สำเร็จ")
        st.session_state.scan = ""

    st.text_input("Scan Kanban No.", key="scan", on_change=confirm_scan)

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
elif mode == "Kanban Delivery Log":

    st.header("Kanban Delivery Log")

    # -----------------------------
    # SEARCH INPUT (OPTIONAL ALL)
    # -----------------------------
    c1, c2, c3, c4, c5 = st.columns(5)

    f_kanban = c1.text_input("Kanban No.")
    f_model  = c2.text_input("Model")
    f_lot    = c3.text_input("Lot No.")
    f_wire   = c4.text_input("Wire Number")
    f_date   = c5.date_input("Scan Date", value=None)

    load = st.button("📥 Load Data", type="primary")

    if not load:
        st.info("ℹ️ พิมพ์อะไรก็ได้อย่างน้อย 1 ช่อง แล้วกด Load Data")
        st.stop()

    # =====================================================
    # 1) LOAD DELIVERY (EVENT TABLE)
    # =====================================================
    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select(
            "kanban_no, model_name, lot_no, created_at, last_scanned_at"
        )
        .range(0, 50000)
        .execute()
        .data
    )

    if del_df.empty:
        st.warning("❌ ไม่มีข้อมูลการ Scan")
        st.stop()

    # -----------------------------
    # NORMALIZE DELIVERY
    # -----------------------------
    del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
    del_df["model_name"] = del_df["model_name"].astype(str).str.strip()
    del_df["lot_no"] = (
        del_df["lot_no"]
        .astype(str)
        .str.replace(".0", "", regex=False)
        .str.replace(" ", "")
        .str.strip()
    )

    del_df["Delivered At (GMT+7)"] = (
        del_df["last_scanned_at"]
        .fillna(del_df["created_at"])
        .apply(to_gmt7)
    )

    # =====================================================
    # 2) LOAD LOT MASTER (WIRE NUMBER)
    # =====================================================
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("kanban_no, wire_number")
        .range(0, 50000)
        .execute()
        .data
    )

    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["wire_number"] = lot_df["wire_number"].astype(str).str.strip()

    # =====================================================
    # 3) MERGE
    # =====================================================
    df = del_df.merge(
        lot_df,
        on="kanban_no",
        how="left"
    )

    # =====================================================
    # 4) OR SEARCH (KEY POINT)
    # =====================================================
    mask = pd.Series(False, index=df.index)

    if f_kanban:
        mask |= df["kanban_no"].str.contains(f_kanban, case=False, na=False)

    if f_model:
        mask |= df["model_name"].str.contains(f_model, case=False, na=False)

    if f_lot:
        mask |= df["lot_no"].str.contains(f_lot, case=False, na=False)

    if f_wire:
        mask |= df["wire_number"].str.contains(f_wire, case=False, na=False)

    if f_date:
        scan_date = pd.to_datetime(
            df["Delivered At (GMT+7)"],
            errors="coerce"
        ).dt.date
        mask |= (scan_date == f_date)

    df = df[mask]

    if df.empty:
        st.warning("❌ ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
        st.stop()

    # =====================================================
    # KPI
    # =====================================================
    total = df["kanban_no"].nunique()
    st.metric("📦 Total Matched Kanban", total)

    # =====================================================
    # DISPLAY
    # =====================================================
    st.dataframe(
        df[
            [
                "kanban_no",
                "wire_number",
                "model_name",
                "lot_no",
                "Delivered At (GMT+7)"
            ]
        ].sort_values("Delivered At (GMT+7)", ascending=False),
        use_container_width=True
    )

    st.caption(f"📊 แสดงผล {len(df)} รายการ (OR Search)")

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










