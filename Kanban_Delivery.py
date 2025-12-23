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
        "🔐📤 Upload Lot Master"
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

    st.header("✅ Scan Kanban (Auto + Joint)")

    def confirm_scan():
        kanban = norm(st.session_state.scan)
        if not kanban:
            return

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

            sent = (
                supabase.table("kanban_delivery")
                .select("kanban_no")
                .in_("kanban_no", joint_list)
                .execute()
                .data
            )
            sent_set = {norm(x["kanban_no"]) for x in sent}

            to_insert = [
                {"kanban_no": k, "model_name": model, "lot_no": lot}
                for k in joint_list if k not in sent_set
            ]

            if to_insert:
                supabase.table("kanban_delivery").insert(to_insert).execute()
                st.session_state.msg = (
                    "success",
                    f"✅ Joint COMPLETE {len(to_insert)} วงจร"
                )
            else:
                st.session_state.msg = ("warning", "⚠️ Joint นี้ถูกส่งครบแล้ว")

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
            st.session_state.msg = ("warning", "⚠️ Kanban นี้ถูกส่งแล้ว")
            st.session_state.scan = ""
            return

        supabase.table("kanban_delivery").insert({
            "kanban_no": kanban,
            "model_name": model,
            "lot_no": lot
        }).execute()

        st.session_state.msg = ("success", f"✅ ส่ง Kanban {kanban}")
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
# 2) MODEL KANBAN STATUS (COUNT REAL KANBAN)
# =====================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    c1, c2 = st.columns(2)
    model_filter = c1.text_input("Model (ไม่จำเป็น)")
    lot_filter = c2.text_input("Lot")

    # -----------------------------
    # LOAD LOT MASTER
    # -----------------------------
    lot_df = safe_df(
        supabase.table("lot_master")
        .select("model_name, kanban_no, lot_no")
        .execute()
        .data,
        ["model_name", "kanban_no", "lot_no"]
    )

    if lot_df.empty:
        st.warning("ไม่พบข้อมูล lot master")
        st.stop()

    lot_df["kanban_no"] = lot_df["kanban_no"].astype(str).str.strip()
    lot_df["lot_no"] = clean_series(lot_df["lot_no"])
    lot_df["model_name"] = lot_df["model_name"].astype(str).str.strip()

    # -----------------------------
    # FILTER
    # -----------------------------
    if lot_filter:
        lot_df = lot_df[
            lot_df["lot_no"] == str(lot_filter).strip()
        ]

    if model_filter:
        lot_df = lot_df[
            lot_df["model_name"].str.contains(
                model_filter, case=False, na=False
            )
        ]

    if lot_df.empty:
        st.warning("ไม่พบข้อมูลตามเงื่อนไข")
        st.stop()

    # -----------------------------
    # LOAD DELIVERY (SENT)
    # -----------------------------
    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data,
        ["kanban_no"]
    )

    del_df["kanban_no"] = del_df["kanban_no"].astype(str).str.strip()
    del_df["sent"] = 1

    # -----------------------------
    # MERGE
    # -----------------------------
    df = lot_df.merge(
        del_df,
        on="kanban_no",
        how="left"
    )

    df["sent"] = df["sent"].fillna(0)

    # -----------------------------
    # SUMMARY (COUNT REAL KANBAN)
    # -----------------------------
    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(
            Total=("kanban_no", "nunique"),  # ✅ นับ Kanban จริง
            Sent=(
                "kanban_no",
                lambda x: x[
                    df.loc[x.index, "sent"] == 1
                ].nunique()
            )
        )
        .reset_index()
    )

    summary["Remaining"] = summary["Total"] - summary["Sent"]

    summary = summary.sort_values(
        ["lot_no", "model_name"]
    )

    # -----------------------------
    # DISPLAY
    # -----------------------------
    st.dataframe(
        summary,
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

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at")
        .execute()
        .data,
        ["kanban_no", "created_at"]
    )

    del_df["Delivered at (GMT+7)"] = del_df["created_at"].apply(to_gmt7)
    del_df = del_df.drop(columns=["created_at"])

    df = lot_df.merge(del_df, on="kanban_no", how="left")
    st.dataframe(df, use_container_width=True)

# =====================================================
# 4) UPLOAD LOT MASTER
# =====================================================
elif mode == "🔐📤 Upload Lot Master":

    if st.text_input("Planner Password", type="password") != "planner":
        st.warning("🔒 สำหรับ Planner เท่านั้น")
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])

    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)

        required = {
            "lot_no", "kanban_no", "model_name",
            "wire_number", "subpackage_number",
            "wire_harness_code", "joint_a", "joint_b"
        }

        if not required.issubset(df.columns):
            st.error(f"❌ ต้องมี column: {required}")
            st.stop()

        df["lot_no"] = clean_series(df["lot_no"])

        if st.button("🚀 Upload"):
            supabase.table("lot_master").upsert(
                df[list(required)].to_dict("records")
            ).execute()

            st.success(f"✅ Upload {len(df)} records")



