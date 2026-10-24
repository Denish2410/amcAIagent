"""Streamlit demo: photo in -> complaint filed with tracking ID -> "what's the status?".

Run:  streamlit run app.py
"""
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

# Load .env without requiring python-dotenv.
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import agent as agent_mod  # noqa: E402
import db  # noqa: E402
import tools  # noqa: E402

st.set_page_config(page_title="AMC Sahayak", page_icon="🛠️", layout="wide")
db.init_db()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("🛠️ AMC Sahayak")
    st.caption("Civic complaint agent · mock AMC backend")
    user_id = st.text_input("Citizen mobile / ID", value="9876543210")

    has_key = bool(os.getenv("GEMINI_API_KEY"))
    offline = st.toggle("Offline mode (no Gemini)", value=not has_key, disabled=not has_key,
                        help="Uses a rule-based agent over the same tools. Auto-on when GEMINI_API_KEY is missing.")
    os.environ["OFFLINE_MODE"] = "1" if offline else "0"
    fast = st.toggle("Fast-forward complaint lifecycle", value=True,
                     help="Demo clock: Filed → Assigned (1 min) → In progress (3 min) → Resolved (6 min).")
    os.environ["FAST_FORWARD"] = "1" if fast else "0"
    st.caption(f"Agent: **{'Offline rules' if offline else 'Gemini · ' + os.getenv('GEMINI_MODEL', 'gemini-flash-latest')}**")

    st.divider()
    st.subheader("👷 Officer console (mock)")
    conn = db.connect()
    rows = [dict(r) for r in conn.execute(
        """SELECT c.tracking_id, c.issue_type, w.name AS ward, c.status, c.lat, c.lon, c.upvotes
           FROM complaints c JOIN wards w ON w.id = c.ward_id ORDER BY c.created_at DESC LIMIT 20""")]
    conn.close()
    if not rows:
        st.caption("No complaints yet.")
    for r in rows[:8]:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"`{r['tracking_id']}`  \n{r['issue_type'].replace('_', ' ')} · {r['ward']} · **{r['status']}**")
        if r["status"] != "RESOLVED" and c2.button("Next ▶", key=f"adv_{r['tracking_id']}"):
            tools.advance_status(r["tracking_id"])
            st.rerun()
    pts = [r for r in rows if r["lat"] is not None]
    if pts:
        st.map(pd.DataFrame(pts)[["lat", "lon"]], size=40, zoom=11)

    st.divider()
    if st.button("Reset demo data", type="secondary"):
        db.init_db(reset=True)
        st.session_state.clear()
        st.rerun()

# ---------------------------------------------------------------- agent per session
agent_key = (user_id, offline)
if st.session_state.get("agent_key") != agent_key:
    st.session_state.agent_key = agent_key
    st.session_state.agent = agent_mod.make_agent(user_id)
    st.session_state.fallback = agent_mod.OfflineAgent(user_id)
    st.session_state.messages = []

st.title("Report a civic issue")
st.caption("Send a photo of a pothole, garbage, broken streetlight or water logging. "
           "Add the area name if your photo has no location. Then ask *what's the status?*")


def render_trace(trace):
    if not trace:
        return
    with st.expander(f"🔧 Agent steps · {len(trace)} tool call{'s' if len(trace) != 1 else ''}"):
        for i, step in enumerate(trace, 1):
            st.markdown(f"**{i}. `{step['tool']}`**")
            st.code(json.dumps({"args": step["args"], "result": step["result"]}, indent=2, ensure_ascii=False),
                    language="json")


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("image"):
            st.image(m["image"], width=280)
        if m.get("content"):
            st.markdown(m["content"])
        render_trace(m.get("trace"))

prompt = st.chat_input("Type a message or attach a photo…", accept_file=True,
                       file_type=["jpg", "jpeg", "png", "webp"])
if prompt:
    text = prompt.text or ""
    image_id, image_bytes = None, None
    if prompt.files:
        f = prompt.files[0]
        image_bytes = f.getvalue()
        image_id = tools.save_upload(image_bytes, f.name)

    st.session_state.messages.append({"role": "user", "content": text, "image": image_bytes})
    with st.chat_message("user"):
        if image_bytes:
            st.image(image_bytes, width=280)
        if text:
            st.markdown(text)

    with st.chat_message("assistant"):
        with st.spinner("Working on it…"):
            try:
                reply, trace = st.session_state.agent.run(text, image_id=image_id)
            except Exception as e:  # keep the demo alive if Gemini errors out
                reply, trace = st.session_state.fallback.run(text, image_id=image_id)
                reply = f"_⚠️ Gemini error ({type(e).__name__}: {str(e)[:120]}); answered with the offline agent._\n\n{reply}"
        st.markdown(reply)
        render_trace(trace)
    st.session_state.messages.append({"role": "assistant", "content": reply, "trace": trace})
    st.rerun()
