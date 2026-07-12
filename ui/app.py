"""
EPC Intelligence Platform — Streamlit UI
Entry point: streamlit run ui/app.py (from epc-intelligence/ directory)
"""
import os
import sys
import logging

# Ensure project root is on path when run from ui/ or project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

# ------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="EPC Intelligence Platform",
    page_icon="[DC]",
    layout="wide",
    initial_sidebar_state="expanded",
)

import config
from rag.rag_engine import RAGEngine
from agents.spec_compliance import SpecComplianceAgent
from agents.schedule_risk import ScheduleRiskEngine
from agents.supply_chain import SupplyChainAgent
from agents.commissioning_qa import CommissioningQACopilot, TestResult
from agents.rfi_knowledge import RFIKnowledgeAgent
from agents.orchestrator import OrchestratorAgent

logging.basicConfig(level=logging.WARNING)

# ------------------------------------------------------------------
# Session state initialisation (agents load once per session)
# ------------------------------------------------------------------

@st.cache_resource(show_spinner="Initialising platform...")
def init_platform():
    """Load all agents once and cache for the session. Zero Groq calls here."""
    if not config.GROQ_API_KEY:
        return None, "GROQ_API_KEY not set. Please add it to Streamlit Cloud secrets."

    rag = RAGEngine()

    # Ingest standards — pure file I/O, no Groq
    if rag.collection_count() < 10:
        for fname in os.listdir(config.STANDARDS_DIR):
            if fname.endswith(".txt"):
                fpath = os.path.join(config.STANDARDS_DIR, fname)
                rag.ingest_file(fpath, source_label=fname)

    # Agents are created here — GroqClient() instantiated but NOT called
    agents = {
        "compliance":    SpecComplianceAgent(rag=rag),
        "schedule":      ScheduleRiskEngine(),
        "supply":        SupplyChainAgent(),
        "commissioning": CommissioningQACopilot(rag=rag),
        "rfi":           RFIKnowledgeAgent(rag=rag),
        "orchestrator":  OrchestratorAgent(rag=rag),
    }
    return agents, None


def _severity_badge(severity: str) -> str:
    colours = {"CRITICAL": "[!]", "HIGH": "[H]", "MEDIUM": "[M]", "LOW": "[L]"}
    return colours.get(severity, "[*]") + f" {severity}"

def _risk_badge(level: str) -> str:
    colours = {"HIGH": "[!]", "MEDIUM": "[M]", "LOW": "[OK]"}
    return colours.get(level, "[*]") + f" {level}"

def _status_badge(status: str) -> str:
    colours = {"DELIVERED": "[OK]", "IN_TRANSIT": "[>>]", "DISPATCHED": "[>]", "DELAYED": "[!]"}
    return colours.get(status, "[*]") + f" {status}"


def _render_orchestrator_result(agent_key: str, result: dict, agents: dict, query: str) -> None:
    """Render orchestrator result as clean natural language instead of raw JSON."""
    from core.groq_client import GroqClient
    groq = GroqClient()

    if agent_key == "compliance":
        summary = result.get("summary", {})
        deviations = result.get("top_deviations", [])
        st.markdown(f"**{summary.get('total', 0)} items checked** — "
                    f"{summary.get('compliant_count', 0)} compliant, "
                    f"**{summary.get('deviation_count', 0)} deviations**, "
                    f"{summary.get('open_ncrs', 0)} open NCRs")
        if deviations:
            for d in deviations:
                st.markdown(f"- `{d['item_id']}` {d['name']}: spec `{d['spec']}` vs submitted `{d['submitted']}` — **{d['severity']}**")

    elif agent_key == "schedule":
        summary = result.get("summary", {})
        violations = result.get("critical_violations", [])
        mitigations = result.get("mitigations", {})
        risk = summary.get("overall_risk", "UNKNOWN")
        st.markdown(f"**Overall Risk: {risk}** — {summary.get('at_risk_count', len(violations))} task(s) at risk")
        for v in violations:
            task_id = v.get("task_id", "")
            st.markdown(f"- `{task_id}` {v.get('name','')} — Delay: **{v.get('delay_days',0)}d**")
            opts = mitigations.get(task_id, [])
            for opt in opts[:2]:
                st.caption(f"  > {opt}")

    elif agent_key == "supply_chain":
        summary = result.get("summary", {})
        at_risk = result.get("at_risk_shipments", [])
        alts = result.get("alternatives", {})
        st.markdown(f"**{summary.get('at_risk', 0)} at-risk shipment(s)** out of {summary.get('total_suppliers', 0)} tracked")
        for s in at_risk:
            st.markdown(f"- `{s['supplier_id']}` {s['name']} — {s['equipment_type']} — ETA **{s['eta_days']} days**")
        if alts and alts.get("alternatives"):
            st.markdown("**Alternative suppliers:**")
            alt_text = alts["alternatives"]
            if isinstance(alt_text, list):
                for a in alt_text:
                    st.caption(f"> {a}")
            else:
                st.caption(alt_text[:400])

    elif agent_key == "commissioning":
        system = result.get("system_type", "power")
        checklist = result.get("checklist", [])
        st.markdown(f"**{system.title()} commissioning sequence** — {len(checklist)} steps")
        for step in checklist[:4]:
            st.caption(f"Step {step.get('step','?')}: {step.get('description','')[:80]}")
        if len(checklist) > 4:
            st.caption(f"... and {len(checklist)-4} more steps. Open the Commissioning QA tab for full sequence.")

    elif agent_key == "rfi":
        answer = result.get("answer", "")
        citations = result.get("citations", [])
        similar = result.get("similar_rfis", [])
        st.markdown(answer)
        if citations:
            sources = ", ".join(set(c["source"] for c in citations))
            st.caption(f"Sources: {sources}")
        if similar:
            st.markdown("**Related RFIs:**")
            for r in similar[:2]:
                st.caption(f"> {r['rfi_id']} — {r['subject']}")

    else:
        # Fallback: ask Groq to summarise whatever came back
        prompt = (
            f"Summarise the following data centre EPC project analysis result "
            f"in 2-3 plain English sentences for a project manager. "
            f"Original question: {query}\n\nResult data: {str(result)[:1000]}"
        )
        r = groq.generate(prompt)
        if not r.get("error"):
            st.markdown(r["text"])
        else:
            st.json(result, expanded=False)


# ------------------------------------------------------------------
# Main app
# ------------------------------------------------------------------

def main():
    agents, error = init_platform()

    # Header
    st.markdown("## [DC] EPC Intelligence Platform")
    st.markdown("*AI-powered project intelligence for Data Centre construction*")
    st.divider()

    if error:
        st.error(f"[!] Initialisation failed: {error}")
        st.info("Set your `GROQ_API_KEY` in a `.env` file in the project root and restart.")
        st.stop()

    # ------------------------------------------------------------------
    # Sidebar — Orchestrator query bar
    # ------------------------------------------------------------------
    with st.sidebar:
        st.markdown("### [AI] Ask the Orchestrator")
        st.caption("Ask anything — the AI routes your query to the right agent automatically.")
        orch_query = st.text_area(
            "Your question:",
            placeholder="e.g. 'Is the UPS delivery going to make the installation window?'",
            height=100,
            key="orch_input",
        )
        if st.button("Ask", type="primary", use_container_width=True):
            if orch_query.strip():
                with st.spinner("Routing query..."):
                    result = agents["orchestrator"].route(orch_query)
                agent_name = result['agent_used'].replace('_', ' ').title()
                method = result['classification_method']
                st.success(f"Routed to: **{agent_name}** (via {method})")

                if result.get("error"):
                    st.error(result["result"].get("reason", "Agent error"))
                else:
                    _render_orchestrator_result(result["agent_used"], result["result"], agents, orch_query)
            else:
                st.warning("Please enter a question.")

        st.divider()

        # Project status — computed once per session, never on every rerun
        st.markdown("### [==] Project Status")
        if "project_stats" not in st.session_state:
            _cr = agents["compliance"].check_all()
            _ss = agents["supply"].summary()
            _sr = agents["schedule"].analyse(skip_mitigations=True)
            st.session_state["project_stats"] = {
                "open_ncrs": _cr.summary()["open_ncrs"],
                "at_risk": _ss["at_risk"],
                "schedule_risk": _sr.overall_risk,
                "critical_violations": len(_sr.critical_path_violations),
            }
            st.session_state["compliance_report"] = _cr
            st.session_state["schedule_report"] = _sr
            st.session_state["supply_summary"] = _ss

        _stats = st.session_state["project_stats"]
        col1, col2 = st.columns(2)
        col1.metric("Open NCRs", _stats["open_ncrs"])
        col2.metric("At-Risk Shipments", _stats["at_risk"])
        col1.metric("Schedule Risk", _stats["schedule_risk"])
        col2.metric("Critical Violations", _stats["critical_violations"])

    # ------------------------------------------------------------------
    # Main tabs
    # ------------------------------------------------------------------
    # Pull reports from session state — computed once, never recomputed on reruns
    compliance_report = st.session_state.get("compliance_report") or agents["compliance"].check_all()
    schedule_report   = st.session_state.get("schedule_report")   or agents["schedule"].analyse(skip_mitigations=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "[*] Compliance",
        "[~] Schedule Risk",
        "[>>] Supply Chain",
        "[+] Commissioning QA",
        "[?] RFI Intelligence",
    ])

    # ================================================================
    # TAB 1 — Spec & Quality Compliance
    # ================================================================
    with tab1:
        st.markdown("### Specification & Quality Compliance Agent")
        st.caption("Automated procurement compliance check against project specifications.")

        col_left, col_right = st.columns([2, 1])

        with col_right:
            summary = compliance_report.summary()
            st.metric("Total Items", summary["total"])
            st.metric("Compliant", summary["compliant_count"], delta=None)
            st.metric("Deviations", summary["deviation_count"],
                      delta=f"-{summary['deviation_count']}" if summary["deviation_count"] else None,
                      delta_color="inverse")
            st.metric("Open NCRs", summary["open_ncrs"])
            st.metric("Critical NCRs", summary["critical_ncrs"])

        with col_left:
            if compliance_report.deviations:
                st.markdown("#### [!] Non-Conformances Detected")
                for dev in compliance_report.deviations:
                    with st.expander(
                        f"{_severity_badge(dev['severity'])}  |  {dev['item_id']} — {dev['name']}",
                        expanded=dev["severity"] in ("CRITICAL", "HIGH"),
                    ):
                        c1, c2, c3 = st.columns(3)
                        c1.markdown(f"**Spec Requirement**\n\n`{dev['spec_requirement']} {dev['unit']}`")
                        c2.markdown(f"**Vendor Submitted**\n\n`{dev['vendor_submitted_value']} {dev['unit']}`")
                        c3.markdown(f"**Category**\n\n{dev['category']}")
                        st.caption(f"Reason: {dev['compliance_reason']}")
            else:
                st.success("All procurement items are compliant.")

        st.divider()

        # NCR log table
        if compliance_report.ncr_log:
            st.markdown("#### [#] NCR Audit Log")
            ncr_data = [
                {
                    "NCR ID": n.ncr_id,
                    "Item": n.name,
                    "Category": n.category,
                    "Spec Required": f"{n.spec_requirement} {n.unit}",
                    "Submitted": f"{n.vendor_submitted_value} {n.unit}",
                    "Severity": n.severity,
                    "Status": n.status,
                }
                for n in compliance_report.ncr_log
            ]
            st.dataframe(ncr_data, use_container_width=True)

        st.divider()
        # Drawing upload
        st.markdown("#### [IMG] Drawing / Submittal Analysis (Vision AI)")
        st.caption("Upload an equipment drawing or vendor submittal. Analysed by Llama 4 Scout vision model against TIA-942 / Tier III standards.")
        uploaded = st.file_uploader(
            "Upload an equipment drawing or vendor submittal (PNG/JPG/PDF)",
            type=["png", "jpg", "jpeg", "pdf"],
        )
        if uploaded:
            if uploaded.type.startswith("image/"):
                st.image(uploaded, use_container_width=True)
                with st.spinner("Analysing image with Llama 4 Scout vision — reading actual drawing content..."):
                    result = agents["compliance"].analyse_drawing(uploaded.read(), uploaded.name)
                if result.get("error"):
                    st.warning(f"Manual review required for **{uploaded.name}**")
                else:
                    model_used = result.get("model", "Groq")
                    st.caption(f"Analysed by: `{model_used}`")
                    st.markdown(f"**Review: `{result['filename']}`**")
                    st.code(result["analysis"], language=None)
                    st.download_button(
                        "[DN] Download Review",
                        data=result["analysis"],
                        file_name=f"review_{uploaded.name}.txt",
                        mime="text/plain",
                    )
            else:
                st.info("PDF drawing analysis: requires manual review.")

    # ================================================================
    # TAB 2 — Schedule Risk Engine
    # ================================================================
    with tab2:
        st.markdown("### Predictive Schedule Risk Engine")
        st.caption("CPM-based risk detection with Groq-generated mitigation options.")

        overall = schedule_report.overall_risk
        risk_col, _, _ = st.columns(3)
        risk_col.markdown(f"**Overall Project Risk:** {_risk_badge(overall)}")

        if schedule_report.critical_path_violations:
            st.markdown("#### [!] Critical Path Violations")
            for task in schedule_report.critical_path_violations:
                with st.expander(
                    f"[!] {task['task_id']} — {task['name']}  |  Delay: {task['delay_days']}d  |  Risk Score: {task['risk_score']}",
                    expanded=True,
                ):
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Planned Start", task["planned_start"])
                    c2.metric("Actual Start", task["actual_start"])
                    c3.metric("Lead Time", f"{task['lead_time_days']}d")
                    c4.metric("Buffer", f"{task['buffer_days']}d")

                    # Mitigations are generated on-demand only
                    mit_key = f"mit_{task['task_id']}"
                    if st.button(f"Generate Mitigations for {task['task_id']}", key=mit_key):
                        with st.spinner("Generating mitigation options via Groq..."):
                            full_report = agents["schedule"].analyse(skip_mitigations=False)
                            mits = full_report.mitigations.get(task["task_id"], [])
                        if mits:
                            st.markdown("**Mitigation Options:**")
                            for i, m in enumerate(mits, 1):
                                st.markdown(f"{i}. {m}")
                        else:
                            st.info("No mitigations generated — check Groq API quota.")

        if schedule_report.at_risk:
            st.markdown("#### [M] All At-Risk Tasks")
            risk_table = [
                {
                    "Task ID": t["task_id"],
                    "Name": t["name"],
                    "Status": t["status"],
                    "Delay (days)": t["delay_days"],
                    "Risk Score": t["risk_score"],
                    "Critical Path": "YES" if t["on_critical_path"] else "no",
                    "Planned End": t["planned_end"],
                }
                for t in schedule_report.at_risk
            ]
            st.dataframe(risk_table, use_container_width=True)

        if schedule_report.on_track:
            with st.expander(f"[OK] On-Track Tasks ({len(schedule_report.on_track)})"):
                on_track_table = [
                    {"Task ID": t["task_id"], "Name": t["name"], "Status": t["status"],
                     "Planned End": t["planned_end"]}
                    for t in schedule_report.on_track
                ]
                st.dataframe(on_track_table, use_container_width=True)

    # ================================================================
    # TAB 3 — Supply Chain Visibility
    # ================================================================
    with tab3:
        st.markdown("### Supply Chain Visibility Agent")
        st.caption("Real-time shipment tracking with geospatial map and alternative sourcing.")

        all_suppliers = agents["supply"].get_all()
        at_risk = agents["supply"].get_at_risk()
        summary = agents["supply"].summary()

        # KPI row
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Suppliers", summary["total_suppliers"])
        k2.metric("Delivered", summary["delivered"])
        k3.metric("In Transit / Dispatched", summary["in_transit"])
        k4.metric("AT RISK", summary["at_risk"], delta=f"-{summary['at_risk']} deliveries" if summary["at_risk"] else None, delta_color="inverse")

        # Map
        st.markdown("#### [MAP] Supplier Locations")
        map_data = [{"lat": s["lat"], "lon": s["lon"]} for s in all_suppliers]
        if map_data:
            st.map(map_data, zoom=4)

        # At-risk table
        if at_risk:
            st.markdown("#### [!] At-Risk Deliveries")
            for s in at_risk:
                with st.expander(
                    f"[!] {s['supplier_id']} — {s['name']}  |  {s['equipment_type']}  |  ETA: {s['eta_days']} days",
                    expanded=True,
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.markdown(f"**Status:** {_status_badge(s['shipment_status'])}")
                    c2.markdown(f"**Route:** {s['origin_city']} → {s['destination_city']}")
                    c3.markdown(f"**ETA:** {s['eta_days']} days")

                    if st.button(f"Find Alternative Suppliers for {s['equipment_type']}", key=f"alt_{s['supplier_id']}"):
                        with st.spinner("Querying Groq for alternatives..."):
                            alt = agents["supply"].get_alternatives(s["equipment_type"])
                        st.markdown("**Alternative Procurement Options:**")
                        if isinstance(alt["alternatives"], list):
                            for option in alt["alternatives"]:
                                st.markdown(f"- {option}")
                        else:
                            st.text(alt["alternatives"])

        # Full shipment table
        st.markdown("#### [BOX] All Shipments")
        ship_table = [
            {
                "ID": s["supplier_id"],
                "Supplier": s["name"],
                "Equipment": s["equipment_type"],
                "Status": _status_badge(s["shipment_status"]),
                "ETA (days)": s["eta_days"],
                "Route": f"{s['origin_city']} → {s['destination_city']}",
            }
            for s in all_suppliers
        ]
        st.dataframe(ship_table, use_container_width=True)

    # ================================================================
    # TAB 4 — Commissioning QA
    # ================================================================
    with tab4:
        st.markdown("### Commissioning QA Copilot")
        st.caption("TIA-942 and Uptime Institute Tier III grounded test sequences with auto-generated test records.")

        system_options = ["power", "cooling", "network", "fire"]
        selected_system = st.selectbox("Select system to commission:", system_options, index=0)

        if st.button("Load Test Sequence", type="primary"):
            with st.spinner(f"Retrieving {selected_system} commissioning checklist from standards..."):
                checklist = agents["commissioning"].get_test_sequence(selected_system)
            st.session_state["checklist"] = checklist
            st.session_state["system_type"] = selected_system
            st.session_state["test_results"] = {}

        checklist = st.session_state.get("checklist", [])
        system_type = st.session_state.get("system_type", selected_system)

        if checklist:
            st.markdown(f"#### {system_type.title()} System — Commissioning Checklist")
            st.caption("Mark each step as PASS or FAIL after completing the physical test.")

            test_results = st.session_state.get("test_results", {})

            for step in checklist:
                step_num = step.get("step", "?")
                desc = step.get("description", "")
                acceptance = step.get("acceptance", "As per spec")
                source = step.get("source", "")

                with st.expander(f"Step {step_num}: {desc[:80]}{'...' if len(desc) > 80 else ''}"):
                    st.markdown(f"**Acceptance Criteria:** `{acceptance}`")
                    if source:
                        st.caption(f"Source: {source}")

                    col_val, col_status = st.columns([2, 1])
                    measured = col_val.text_input(
                        "Measured / Observed value:",
                        key=f"val_{step_num}",
                        placeholder="e.g. 0.5 ohm, PASS, 8 seconds",
                    )
                    if measured:
                        validation = agents["commissioning"].validate_test_result(
                            desc, measured, acceptance
                        )
                        status = validation["status"]
                        colour = {"PASS": "[OK]", "FAIL": "[X]", "MANUAL_REVIEW": "[?]"}.get(status, "[*]")
                        col_status.markdown(f"**Auto Result:** {colour} {status}")
                        col_status.caption(validation["reason"])
                        test_results[step_num] = {
                            "step": step_num,
                            "description": desc,
                            "acceptance": acceptance,
                            "measured_value": measured,
                            "status": status,
                        }
                        st.session_state["test_results"] = test_results

            # Generate test record button
            if test_results:
                st.divider()
                tester_name = st.text_input("Tester name:", value="Site Engineer", key="tester")
                project_name = st.text_input("Project name:", value="Mumbai Data Centre EPC", key="project")

                if st.button("[DOC] Generate Test Record Document", type="primary"):
                    results_objs = [
                        TestResult(
                            step=v["step"],
                            description=v["description"],
                            acceptance=v["acceptance"],
                            measured_value=v["measured_value"],
                            status=v["status"],
                        )
                        for v in test_results.values()
                    ]
                    with st.spinner("Generating formal test record..."):
                        record = agents["commissioning"].generate_test_record(
                            system_type, results_objs, project_name, tester_name
                        )
                        doc_text = agents["commissioning"].format_test_record_text(record)

                    st.success(f"Test Record **{record.record_id}** generated — Overall: {record.overall_status}")
                    st.text_area("Test Record Document:", doc_text, height=400, key="test_record_output")
                    st.download_button(
                        "[DN] Download Test Record",
                        data=doc_text,
                        file_name=f"{record.record_id}.txt",
                        mime="text/plain",
                    )

    # ================================================================
    # TAB 5 — RFI Intelligence
    # ================================================================
    with tab5:
        st.markdown("### Project Knowledge & RFI Intelligence Agent")
        st.caption("RAG-powered search over all project RFIs and commissioning standards. Answers with citations.")

        # Chat history
        if "rfi_history" not in st.session_state:
            st.session_state["rfi_history"] = []

        # Display chat history
        for msg in st.session_state["rfi_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("citations"):
                    with st.expander("[CITE] Citations"):
                        for c in msg["citations"]:
                            st.markdown(f"- **{c['source']}** (relevance: {c['score']:.2f})")
                if msg.get("similar_rfis"):
                    with st.expander("[SIMILAR] Similar Resolved RFIs"):
                        for rfi in msg["similar_rfis"]:
                            st.markdown(
                                f"**{rfi['rfi_id']}** — {rfi['subject']}\n\n"
                                f"> Resolution: {rfi['resolution']}\n\n"
                                f"*Clause: {rfi['related_clause']}*"
                            )

        # Input
        user_q = st.chat_input("Ask about specs, RFIs, standards, or project documents...")
        if user_q:
            st.session_state["rfi_history"].append({"role": "user", "content": user_q})
            with st.chat_message("user"):
                st.markdown(user_q)

            with st.chat_message("assistant"):
                with st.spinner("Searching project knowledge base..."):
                    result = agents["rfi"].query(user_q)

                answer = result["answer"]
                st.markdown(answer)

                if result.get("citations"):
                    with st.expander("[CITE] Citations"):
                        for c in result["citations"]:
                            st.markdown(f"- **{c['source']}** (relevance: {c['score']:.2f})")

                if result.get("similar_rfis"):
                    with st.expander(f"[SIMILAR] {len(result['similar_rfis'])} Similar Resolved RFI(s) Found"):
                        for rfi in result["similar_rfis"]:
                            st.markdown(
                                f"**{rfi['rfi_id']}** — {rfi['subject']}\n\n"
                                f"> Resolution: {rfi['resolution']}\n\n"
                                f"*Clause: {rfi['related_clause']}*"
                            )

            st.session_state["rfi_history"].append({
                "role": "assistant",
                "content": answer,
                "citations": result.get("citations", []),
                "similar_rfis": result.get("similar_rfis", []),
            })

        # Quick query buttons
        st.divider()
        st.caption("Quick queries:")
        q_cols = st.columns(3)
        quick_queries = [
            "What is the UPS battery autonomy requirement for Tier III?",
            "What is the maximum cable tray load per metre?",
            "Generator start time requirement for ATS transfer?",
        ]
        for i, (col, q) in enumerate(zip(q_cols, quick_queries)):
            if col.button(q[:45] + "...", key=f"quick_{i}"):
                st.session_state["rfi_history"].append({"role": "user", "content": q})
                with st.spinner("Searching..."):
                    result = agents["rfi"].query(q)
                st.session_state["rfi_history"].append({
                    "role": "assistant",
                    "content": result["answer"],
                    "citations": result.get("citations", []),
                    "similar_rfis": result.get("similar_rfis", []),
                })
                st.rerun()


if __name__ == "__main__":
    main()
