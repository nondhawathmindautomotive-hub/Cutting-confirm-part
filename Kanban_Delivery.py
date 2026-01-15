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
        "✅ Scan Kanban",
        "📊 Lot Kanban Summary",
        "📦 Kanban Delivery Log",
        "🔍 Tracking Search",
        "🔐📤 Upload Lot Master",
    ]
)

# =====================================================
# ✅ 1) SCAN KANBAN (PRODUCTION SAFE)
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
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban ใน Lot Master")
            st.session_state.scan = ""
            return

        row = base[0]
        model = norm(row["model_name"])
        lot = norm_lot(row["lot_no"])
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

            st.session_state.msg = (
                "success",
                f"✅ Joint Scan สำเร็จ | Qty = {len(joint_list)}"
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

            st.session_state.msg = ("success", "🔄 Scan ซ้ำ (อัปเดตเวลา)")
            st.session_state.scan = ""
            return

        supabase.table("kanban_delivery").insert({
            "kanban_no": kanban,
            "model_name": model,
            "lot_no": lot,
            "last_scanned_at": now_ts
        }).execute()

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
# 📊 2) LOT KANBAN SUMMARY (PRODUCTION TRUTH)
# =====================================================
elif mode == "📊 Lot Kanban Summary":

    st.header("📊 Lot Kanban Summary (Production)")

    c1, c2 = st.columns(2)
    f_lot = c1.text_input("Lot No. (ต้องตรง 100%)")
    f_model = c2.text_input("Model (optional)")

    # -----------------------------
    # SUMMARY TABLE (SOURCE OF TRUTH)
    # -----------------------------
    summary_df = safe_df(
        supabase.table("lot_kanban_summary")
        .select(
            "lot_no, model_name, total_circuit, sent_circuit, remaining_circuit, last_updated_at"
        )
        .range(0, 50000)
        .execute()
        .data
    )

    summary_df["lot_no"] = summary_df["lot_no"].apply(norm_lot)

    if f_lot:
        summary_df = summary_df[summary_df["lot_no"] == norm_lot(f_lot)]

    if f_model:
        summary_df = summary_df[
            summary_df["model_name"].str.contains(f_model, case=False, na=False)
        ]

    if summary_df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    # -----------------------------
    # CSV RECORD COUNT
    # -----------------------------
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("lot_no")
        .range(0, 50000)
        .execute()
        .data
    )

    lot_df["lot_no"] = lot_df["lot_no"].apply(norm_lot)

    if f_lot:
        lot_df = lot_df[lot_df["lot_no"] == norm_lot(f_lot)]

    # -----------------------------
    # KPI
    # -----------------------------
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📄 Total Record (CSV)", len(lot_df))
    k2.metric("⚙️ Total Circuit", int(summary_df["total_circuit"].sum()))
    k3.metric("✅ Sent", int(summary_df["sent_circuit"].sum()))
    k4.metric("⏳ Remaining", int(summary_df["remaining_circuit"].sum()))

    summary_df["Last Update (GMT+7)"] = summary_df["last_updated_at"].apply(to_gmt7)

    st.dataframe(
        summary_df[
            [
                "lot_no",
                "model_name",
                "total_circuit",
                "sent_circuit",
                "remaining_circuit",
                "Last Update (GMT+7)"
            ]
        ],
        use_container_width=True
    )

# =====================================================
# 📦 3) KANBAN DELIVERY LOG
# =====================================================
elif mode == "📦 Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    # =============================
    # SEARCH
    # =============================
    c1, c2, c3 = st.columns(3)
    f_kanban = c1.text_input("Kanban No.")
    f_model  = c2.text_input("Model")
    f_lot    = c3.text_input("Lot No.")

    st.divider()

    # =============================
    # LOAD DELIVERY
    # =============================
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
        st.warning("❌ ยังไม่มีข้อมูลการ Scan")
        st.stop()

    # =============================
    # NORMALIZE
    # =============================
    del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
    del_df["model_name"] = del_df["model_name"].astype(str).str.strip()
    del_df["lot_no"] = (
        del_df["lot_no"]
        .astype(str)
        .str.replace(".0", "", regex=False)
        .str.strip()
    )

    del_df["Delivered At (GMT+7)"] = (
        del_df["last_scanned_at"]
        .fillna(del_df["created_at"])
        .apply(to_gmt7)
    )

    # =============================
    # APPLY FILTER
    # =============================
    if f_kanban:
        del_df = del_df[
            del_df["kanban_no"].str.contains(f_kanban, case=False, na=False)
        ]

    if f_model:
        del_df = del_df[
            del_df["model_name"].str.contains(f_model, case=False, na=False)
        ]

    if f_lot:
        del_df = del_df[
            del_df["lot_no"].str.contains(f_lot, case=False, na=False)
        ]

    if del_df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไขที่ค้นหา")
        st.stop()

    # =============================
    # KPI
    # =============================
    total = len(del_df)

    k1, = st.columns(1)
    k1.metric("📦 Total Delivered Kanban", total)

    # =============================
    # DISPLAY
    # =============================
    st.dataframe(
        del_df[
            [
                "kanban_no",
                "model_name",
                "lot_no",
                "Delivered At (GMT+7)"
            ]
        ].sort_values("Delivered At (GMT+7)", ascending=False),
        use_container_width=True
    )

    st.caption(f"📊 แสดงทั้งหมด {total} รายการ")

# =====================================================
# 🔍 4) TRACKING SEARCH (PLACEHOLDER)
# =====================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    c1, c2, c3 = st.columns(3)
    kanban = c1.text_input("Kanban No.")
    model  = c2.text_input("Model")
    lot    = c3.text_input("Lot No.")

    query = supabase.table("lot_master").select(
        "kanban_no, model_name, lot_no"
    )

    if kanban:
        query = query.ilike("kanban_no", f"%{kanban}%")
    if model:
        query = query.ilike("model_name", f"%{model}%")
    if lot:
        query = query.ilike("lot_no", f"%{lot}%")

    lot_df = safe_df(query.range(0, 50000).execute().data)

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, last_scanned_at")
        .range(0, 50000)
        .execute().data
    )

    if not del_df.empty:
        del_df["Delivered At (GMT+7)"] = (
            del_df["last_scanned_at"]
            .fillna(del_df["created_at"])
            .apply(to_gmt7)
        )

    df = lot_df.merge(
        del_df[["kanban_no", "Delivered At (GMT+7)"]],
        on="kanban_no",
        how="left"
    )

    df["Status"] = df["Delivered At (GMT+7)"].apply(
        lambda x: "Sent" if pd.notna(x) else "Remaining"
    )

    st.dataframe(df, use_container_width=True)

