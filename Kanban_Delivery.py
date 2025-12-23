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
        s.astype(str)
         .str.replace(r"\.0$", "", regex=True)
         .str.strip()
    )

def norm(v):
    return str(v).replace(".0", "").strip()

# =====================================================
# 1) SCAN KANBAN (AUTO JOINT – SAFE)
# =====================================================
if mode == "✅ Scan Kanban":

    st.header("✅ Scan Kanban")

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
            st.error("❌ ไม่พบ Kanban")
            st.session_state.scan = ""
            return

        row = base[0]
        model = norm(row["model_name"])
        lot = norm(row["lot_no"])
        joint_a = norm(row.get("joint_a") or "")
        joint_b = norm(row.get("joint_b") or "")
        is_joint = bool(joint_a or joint_b)

        # ---------------- JOINT ----------------
        if is_joint:
            all_rows = (
                supabase.table("lot_master")
                .select("kanban_no, joint_a, joint_b")
                .eq("model_name", model)
                .eq("lot_no", lot)
                .execute()
                .data
            )

            joint_list = []
            for r in all_rows:
                if joint_a and norm(r.get("joint_a")) == joint_a:
                    joint_list.append(norm(r["kanban_no"]))
                elif joint_b and norm(r.get("joint_b")) == joint_b:
                    joint_list.append(norm(r["kanban_no"]))

            if not joint_list:
                st.warning("⚠️ ไม่พบ Kanban ใน Joint")
                st.session_state.scan = ""
                return

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
                st.success(f"✅ Joint COMPLETE ({len(to_insert)} วงจร)")
            else:
                st.warning("⚠️ Joint นี้ส่งครบแล้ว")

            st.session_state.scan = ""
            return

        # ---------------- NORMAL ----------------
        exist = (
            supabase.table("kanban_delivery")
            .select("kanban_no")
            .eq("kanban_no", kanban)
            .execute()
            .data
        )

        if exist:
            st.warning("⚠️ Kanban นี้ถูกส่งแล้ว")
        else:
            supabase.table("kanban_delivery").insert({
                "kanban_no": kanban,
                "model_name": model,
                "lot_no": lot
            }).execute()
            st.success(f"✅ ส่ง Kanban {kanban}")

        st.session_state.scan = ""

    st.text_input("Scan Kanban No.", key="scan", on_change=confirm_scan)

# =====================================================
# 2) MODEL KANBAN STATUS (✅ FIXED)
# =====================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    c1, c2 = st.columns(2)
    model_filter = c1.text_input("Model (ไม่จำเป็น)")
    lot_filter = c2.text_input("Lot")

    raw = safe_df(
        supabase.table("lot_master")
        .select(
            "model_name, lot_no, kanban_no, wire_harness_code"
        )
        .execute()
        .data
    )

    if raw.empty:
        st.warning("ไม่พบข้อมูลในระบบ")
        st.stop()

    raw["lot_no"] = clean_series(raw["lot_no"])
    raw["kanban_no"] = clean_series(raw["kanban_no"])
    raw["wire_harness_code"] = clean_series(raw["wire_harness_code"])

    if lot_filter:
        raw = raw[raw["lot_no"] == norm(lot_filter)]

    if model_filter:
        raw = raw[
            raw["model_name"]
            .str.contains(model_filter, case=False, na=False)
        ]

    if raw.empty:
        st.warning("ไม่พบข้อมูล Lot นี้")
        st.stop()

    sent_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute()
        .data,
        ["kanban_no"]
    )
    sent_df["sent"] = 1
    sent_df["kanban_no"] = clean_series(sent_df["kanban_no"])

    df = raw.merge(sent_df, on="kanban_no", how="left")
    df["sent"] = df["sent"].fillna(0)

    # ✅ นับ “วงจรจริง”
    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(
            Total_Circuit=("wire_harness_code", "nunique"),
            Sent=("sent", "sum")
        )
        .reset_index()
    )
    summary["Remaining"] = summary["Total_Circuit"] - summary["Sent"]

    st.dataframe(summary, use_container_width=True)

# =====================================================
# 3) TRACKING SEARCH
# =====================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    kanban = st.text_input("Kanban No.")
    lot = st.text_input("Lot")

    query = supabase.table("lot_master").select("*")
    if kanban:
        query = query.ilike("kanban_no", f"%{kanban}%")
    if lot:
        query = query.ilike("lot_no", f"%{lot}%")

    df = safe_df(query.execute().data)
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
