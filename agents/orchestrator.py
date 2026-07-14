import logging
from typing import Any

from core.groq_client import GroqClient
from rag.rag_engine import RAGEngine

logger = logging.getLogger(__name__)

_KEYWORD_MAP: dict[str, list[str]] = {
    "compliance": ["spec", "specification", "deviation", "ncr", "non-conformance", "submittal",
                   "drawing", "vendor", "procurement", "quality", "compliant", "requirement"],
    "schedule":   ["schedule", "delay", "delayed", "lead time", "critical path", "overrun",
                   "milestone", "timeline", "start date", "completion", "risk", "buffer"],
    "supply_chain": ["shipment", "shipping", "delivery", "supplier", "arrive", "arrival", "transit",
                     "dispatch", "eta", "logistics", "freight", "origin", "supply chain"],
    "commissioning": ["commission", "test", "testing", "iat", "ist", "tier", "tia-942", "uptime",
                      "checklist", "generator start", "ats", "ups test", "cooling test", "fire test"],
    "rfi":        ["rfi", "rfi-", "document", "question", "clause", "specification clause",
                   "contract", "standard", "resolution", "answered", "project document"],
}

_AGENT_KEYS = ["compliance", "schedule", "supply_chain", "commissioning", "rfi"]


def _keyword_classify(query: str) -> str | None:
    lower = query.lower()
    scores: dict[str, int] = {k: 0 for k in _AGENT_KEYS}
    for agent_key, keywords in _KEYWORD_MAP.items():
        for kw in keywords:
            if kw in lower:
                scores[agent_key] += 1
    best_key = max(scores, key=lambda k: scores[k])
    return best_key if scores[best_key] > 0 else None


class OrchestratorAgent:

    def __init__(self, rag: RAGEngine) -> None:
        self._rag = rag
        self._groq = GroqClient()
        self._agents: dict[str, Any] = {}

    def _get_agent(self, key: str) -> Any:
        if key not in self._agents:
            self._agents[key] = self._build_agent(key)
        return self._agents[key]

    def _build_agent(self, key: str) -> Any:
        if key == "compliance":
            from agents.spec_compliance import SpecComplianceAgent
            return SpecComplianceAgent(rag=self._rag)
        if key == "schedule":
            from agents.schedule_risk import ScheduleRiskEngine
            return ScheduleRiskEngine()
        if key == "supply_chain":
            from agents.supply_chain import SupplyChainAgent
            return SupplyChainAgent()
        if key == "commissioning":
            from agents.commissioning_qa import CommissioningQACopilot
            return CommissioningQACopilot(rag=self._rag)
        if key == "rfi":
            from agents.rfi_knowledge import RFIKnowledgeAgent
            return RFIKnowledgeAgent(rag=self._rag)
        raise ValueError(f"Unknown agent key: {key}")

    def _gemini_classify(self, query: str) -> str:
        prompt = (
            "Classify the following data centre EPC project query into exactly one category.\n"
            "Categories: compliance, schedule, supply_chain, commissioning, rfi\n\n"
            "Rules:\n"
            "- compliance: equipment specs, NCRs, vendor submittals, drawings\n"
            "- schedule: project timelines, delays, critical path, lead times\n"
            "- supply_chain: shipments, deliveries, suppliers, logistics\n"
            "- commissioning: testing, TIA-942, Uptime Institute, test procedures\n"
            "- rfi: RFI questions, contract documents, spec clauses, past resolutions\n\n"
            f"Query: {query}\n\n"
            "Respond with ONLY the category name, nothing else."
        )
        result = self._groq.generate(prompt)
        if result.get("error"):
            return "rfi"
        classification = result["text"].strip().lower()
        for key in _AGENT_KEYS:
            if key in classification:
                return key
        return "rfi"

    def route(self, query: str) -> dict[str, Any]:
        agent_key = _keyword_classify(query)
        method = "keyword"

        if agent_key is None:
            agent_key = self._gemini_classify(query)
            method = "groq"

        logger.info("Routing query to '%s' via %s", agent_key, method)

        try:
            agent = self._get_agent(agent_key)
            result = self._dispatch(agent_key, agent, query)
            return {
                "agent_used": agent_key,
                "classification_method": method,
                "result": result,
                "error": False,
            }
        except Exception as exc:
            logger.error("Agent '%s' failed: %s", agent_key, exc)
            return {
                "agent_used": agent_key,
                "classification_method": method,
                "result": {"error": True, "reason": str(exc)},
                "error": True,
            }

    def _dispatch(self, key: str, agent: Any, query: str) -> Any:
        if key == "compliance":
            report = agent.check_all()
            return {
                "summary": report.summary(),
                "top_deviations": [
                    {"item_id": d["item_id"], "name": d["name"],
                     "spec": d["spec_requirement"], "submitted": d["vendor_submitted_value"],
                     "severity": d["severity"]}
                    for d in report.deviations[:5]
                ],
                "ncr_count": len(report.ncr_log),
            }
        if key == "schedule":
            report = agent.analyse()
            return {
                "summary": report.summary(),
                "critical_violations": report.critical_path_violations[:3],
                "mitigations": {
                    k: v for k, v in list(report.mitigations.items())[:3]
                },
            }
        if key == "supply_chain":
            at_risk = agent.get_at_risk()
            result: dict[str, Any] = {
                "summary": agent.summary(),
                "at_risk_shipments": at_risk,
            }
            if at_risk:
                result["alternatives"] = agent.get_alternatives(at_risk[0]["equipment_type"])
            return result
        if key == "commissioning":
            system = _extract_system_type(query)
            checklist = agent.get_test_sequence(system)
            return {"system_type": system, "checklist": checklist}
        if key == "rfi":
            return agent.query(query)
        raise ValueError(f"No dispatch rule for key: {key}")


def _extract_system_type(query: str) -> str:
    lower = query.lower()
    for sys in ["cooling", "power", "network", "fire", "electrical"]:
        if sys in lower:
            return sys
    return "power"
