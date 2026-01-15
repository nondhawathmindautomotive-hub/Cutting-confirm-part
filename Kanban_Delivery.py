import streamlit as st
from supabase import create_client
import pandas as pd

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="Kanban Delivery - MIND Automotive", layout="wide")

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

st.title("📦 Kanban Delivery - MIND Automotive Parts")

# =====================================================
# TIMEZONE
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
    return pd.DataFrame(data) if data else pd.DataFrame(columns=cols or [])

def norm(v):
    return str(v).strip() if v else ""

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
# 1) SCAN KANBAN (UPSERT + JOINT SAFE)
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
            st.session_state.msg = ("error", "❌ ไม่พบ Kanban ใน lot_master")
            st.session_state.scan = ""
            return

        r = base[0]
        model, lot = norm(r["model_name"]), norm(r["lot_no"])
        ja, jb = norm(r.get("joint_a")), norm(r.get("joint_b"))

        rows = (
            supabase.table("lot_master")
            .select("kanban_no, joint_a, joint_b")
            .eq("model_name", model)
            .eq("lot_no", lot)
            .execute()
            .data
        )

        joint_list = [
            norm(x["kanban_no"])
            for x in rows
            if (ja and norm(x.get("joint_a")) == ja)
            or (jb and norm(x.get("joint_b")) == jb)
        ] or [kanban]

        payload = [
            {
                "kanban_no": k,
                "model_name": model,
                "lot_no": lot,
                "last_scanned_at": now_ts,
            }
            for k in set(joint_list)
        ]

        supabase.table("kanban_delivery").upsert(
            payload,
            on_conflict="kanban_no"
        ).execute()

        st.session_state.msg = (
            "success",
            f"✅ Scan สำเร็จ\nModel: {model}\nLot: {lot}\nQty: {len(payload)}"
        )
        st.session_state.scan = ""

    st.text_input("Scan Kanban No.", key="scan", on_change=confirm_scan)

    if "msg" in st.session_state:
        t, m = st.session_state.msg
        getattr(st, t)(m)
        del st.session_state.msg

# =====================================================
# 2) MODEL KANBAN STATUS
# =====================================================
elif mode == "📊 Model Kanban Status":

    st.header("📊 Model Kanban Status")

    c1, c2 = st.columns(2)
    model_f = c1.text_input("Model")
    lot_f = c2.text_input("Lot")

    lot_df = safe_df(
        supabase.table("lot_master")
        .select("model_name, kanban_no, lot_no")
        .execute().data
    )

    if model_f:
        lot_df = lot_df[lot_df["model_name"].str.contains(model_f, case=False)]

    if lot_f:
        lot_df = lot_df[lot_df["lot_no"].astype(str) == lot_f.strip()]

    lot_df = lot_df.drop_duplicates(["kanban_no"])

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no")
        .execute().data,
        ["kanban_no"]
    )
    del_df["sent"] = 1

    df = lot_df.merge(del_df, on="kanban_no", how="left")
    df["sent"] = df["sent"].fillna(0)

    summary = (
        df.groupby(["model_name", "lot_no"])
        .agg(Total=("kanban_no", "nunique"), Sent=("sent", "sum"))
        .reset_index()
    )
    summary["Remaining"] = summary["Total"] - summary["Sent"]

    st.dataframe(summary, use_container_width=True)

# =====================================================
# 3) TRACKING SEARCH
# =====================================================
elif mode == "🔍 Tracking Search":

    st.header("🔍 Tracking Search")

    kanban = st.text_input("Kanban No.")
    q = supabase.table("lot_master").select("*")

    if kanban:
        q = q.ilike("kanban_no", f"%{kanban}%")

    lot_df = safe_df(q.execute().data)

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, last_scanned_at")
        .execute().data
    )

    del_df["Delivered At"] = (
        del_df["last_scanned_at"]
        .fillna(del_df["created_at"])
        .apply(to_gmt7)
    )

    df = lot_df.merge(
        del_df[["kanban_no", "Delivered At"]],
        on="kanban_no",
        how="left"
    )

    st.dataframe(df, use_container_width=True)

# =====================================================
# 4) UPLOAD LOT MASTER (UPSERT REAL)
# =====================================================
elif mode == "🔐📤 Upload Lot Master":

    if st.text_input("Planner Password", type="password") != "planner":
        st.stop()

    file = st.file_uploader("Upload CSV / Excel", ["csv", "xlsx"])
    if file:
        df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
        df = df.fillna("").astype(str)
        df["lot_no"] = df["lot_no"].str.replace(r"\.0$", "", regex=True)

        records = df.to_dict("records")
        supabase.table("lot_master").upsert(
            records,
            on_conflict="kanban_no"
        ).execute()

        st.success(f"✅ Upload สำเร็จ {len(records)} records")

# =====================================================
# 5) 📦 KANBAN DELIVERY LOG (FIXED 100%)
# =====================================================
elif mode == "📦 Kanban Delivery Log":

    st.header("📦 Kanban Delivery Log")

    lot_df = safe_df(
        supabase.table("lot_master")
        .select("kanban_no, model_name, lot_no")
        .execute().data
    ).drop_duplicates(["kanban_no"])

    del_df = safe_df(
        supabase.table("kanban_delivery")
        .select("kanban_no, created_at, last_scanned_at")
        .execute().data
    )

    del_df["sent"] = 1
    del_df["Delivered At"] = (
        del_df["last_scanned_at"]
        .fillna(del_df["created_at"])
        .apply(to_gmt7)
    )

    df = lot_df.merge(
        del_df[["kanban_no", "sent", "Delivered At"]],
        on="kanban_no",
        how="left"
    )

    df["sent"] = df["sent"].fillna(0)

    c1, c2, c3 = st.columns(3)
    c1.metric("📦 Total", len(df))
    c2.metric("✅ Sent", int(df["sent"].sum()))
    c3.metric("⏳ Remaining", int(len(df) - df["sent"].sum()))

    st.dataframe(df, use_container_width=True)
