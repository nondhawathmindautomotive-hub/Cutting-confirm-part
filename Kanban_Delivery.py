import streamlit as st
from supabase import create_client
import pandas as pd


supabase = create_client(
st.secrets["SUPABASE_URL"],
st.secrets["SUPABASE_KEY"]
)


st.set_page_config(page_title="Kanban Scan", layout="centered")
st.title("📦 Kanban Scan Confirm")


# ===== SCAN INPUT =====
def process_scan():
kb = st.session_state.scan.strip()
if not kb:
return


master = supabase.table("master_kanban").select("*").eq("kanban_no", kb).execute()
if not master.data:
st.session_state.error = "❌ ไม่พบ Kanban นี้"
return


mk = master.data[0]
used = supabase.table("delivery_confirm").select("id", count="exact").eq("kanban_no", kb).execute().count


if used >= mk["std_qty"]:
st.session_state.error = "❌ Kanban นี้ส่งครบแล้ว"
return


supabase.table("delivery_confirm").insert({
"kanban_no": kb,
"part_no": mk["part_no"],
"harness_group": mk["harness_group"]
}).execute()


st.session_state.success = f"ส่งแล้ว {used+1} เหลือ {mk['std_qty']-(used+1)}"
st.session_state.scan = ""


st.text_input("Scan Kanban No.", key="scan", on_change=process_scan)


if "error" in st.session_state:
st.error(st.session_state.error)
del st.session_state.error


if "success" in st.session_state:
st.success(st.session_state.success)
del st.session_state.success


st.divider()


# ===== TRACKING TABLE =====
if st.session_state.get("scan"):
kb = st.session_state.scan
else:
kb = None


if kb:
track = supabase.table("delivery_confirm").select("scan_time").eq("kanban_no", kb).order("scan_time").execute()
if track.data:
df = pd.DataFrame(track.data)
st.subheader("📊 Tracking")
st.dataframe(df)
