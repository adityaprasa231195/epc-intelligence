"""
Commissioning QA Copilot

RAG-powered agent grounded in TIA-942 and Uptime Institute Tier standards.
Guides engineers through test sequences, validates results, and generates test records.
"""
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from core.groq_client import GroqClient
from rag.rag_engine import RAGEngine

logger = logging.getLogger(__name__)

# Hardcoded fallback checklists when RAG returns empty
_FALLBACK_CHECKLISTS: dict[str, list[dict]] = {
    "power": [
        {"step": 1, "description": "Verify earthing resistance < 1 ohm (IS 3043)", "acceptance": "< 1 ohm"},
        {"step": 2, "description": "Insulation resistance test on all power cables at 1000V DC", "acceptance": "> 100 MΩ"},
        {"step": 3, "description": "Energise main LV switchboard — verify metering and protection relay settings", "acceptance": "As per design"},
        {"step": 4, "description": "UPS individual test — verify bypass operation and battery autonomy", "acceptance": "> 10 min at full load"},
        {"step": 5, "description": "ATS mains failure simulation — verify transfer within 10 seconds", "acceptance": "≤ 10 seconds"},
        {"step": 6, "description": "Generator load test at 25%, 50%, 75%, 100% nameplate rating", "acceptance": "Stable voltage/freq"},
        {"step": 7, "description": "Integrated UPS-Generator transfer test", "acceptance": "No IT interruption"},
    ],
    "cooling": [
        {"step": 1, "description": "Flush and clean all chilled water pipework", "acceptance": "Clean flush water"},
        {"step": 2, "description": "Pressure test chilled water circuits at 1.5x design pressure for 2 hours", "acceptance": "No pressure drop"},
        {"step": 3, "description": "Balance all AHU airflows to within ±10% of design values", "acceptance": "±10% of design"},
        {"step": 4, "description": "Commission variable speed drives on all pumps and fans", "acceptance": "As per control schedule"},
        {"step": 5, "description": "Verify cooling tower water treatment system operation", "acceptance": "Chemical dosing active"},
        {"step": 6, "description": "Combined cooling system load test — minimum 4 hours at design IT load", "acceptance": "18°C–27°C inlet air"},
        {"step": 7, "description": "N+1 redundancy test — isolate one cooling unit, verify remaining units hold temperature", "acceptance": "Temperature maintained"},
    ],
    "network": [
        {"step": 1, "description": "Test all structured cabling to TIA-568 — insertion loss and return loss", "acceptance": "Within TIA-568 limits"},
        {"step": 2, "description": "Verify redundant fibre entry paths from separate building entries", "acceptance": "Two independent paths"},
        {"step": 3, "description": "Test network equipment redundancy — simulate single switch failure", "acceptance": "No connectivity loss"},
        {"step": 4, "description": "Verify all patch panel labelling matches as-built drawings", "acceptance": "100% match"},
        {"step": 5, "description": "Test DCIM integration with all network equipment", "acceptance": "All devices visible in DCIM"},
    ],
    "fire": [
        {"step": 1, "description": "VESDA functional test — introduce smoke at each sampling point", "acceptance": "Response within 60s"},
        {"step": 2, "description": "Verify FM-200 discharge time simulation ≤ 10 seconds", "acceptance": "≤ 10 seconds"},
        {"step": 3, "description": "Test EPO button at each data hall entrance", "acceptance": "IT load shutdown confirmed"},
        {"step": 4, "description": "Fire alarm integration with BMS — verify CRAC units shut down on alarm", "acceptance": "CRAC shutdown in < 5s"},
        {"step": 5, "description": "Test VESDA sampling point spacing compliance (≤ 5m)", "acceptance": "≤ 5 metres between points"},
    ],
}

_VALID_SYSTEMS = list(_FALLBACK_CHECKLISTS.keys())


@dataclass
class TestResult:
    step: int
    description: str
    acceptance: str
    measured_value: str = ""
    status: str = "PENDING"  # PENDING / PASS / FAIL
    notes: str = ""


@dataclass
class TestRecord:
    record_id: str
    system_type: str
    project_name: str
    test_date: str
    tester: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def overall_status(self) -> str:
        if all(r.status == "PASS" for r in self.results if r.status != "PENDING"):
            return "PASS"
        if any(r.status == "FAIL" for r in self.results):
            return "FAIL"
        return "IN_PROGRESS"


class CommissioningQACopilot:
    """
    Commissioning QA agent grounded in TIA-942 / Uptime Institute standards.
    """

    def __init__(self, rag: RAGEngine) -> None:
        self._rag = rag
        self._groq = GroqClient()

    # ------------------------------------------------------------------
    # Test sequence retrieval
    # ------------------------------------------------------------------

    def get_test_sequence(self, system_type: str) -> list[dict]:
        """
        Retrieve RAG-grounded test checklist for a system type.
        Falls back to hardcoded checklist if RAG is empty or unhelpful.
        """
        system_key = system_type.lower().split()[0]  # "cooling system" → "cooling"

        # Try RAG first
        chunks = self._rag.query(f"commissioning test sequence {system_type} steps procedure")
        if chunks and chunks[0]["score"] > 0.3:
            # Ask Groq to structure the retrieved context into a checklist
            context = "\n\n".join(c["chunk"] for c in chunks[:3])
            prompt = (
                f"Based on the following commissioning standards excerpts, generate a numbered test checklist "
                f"for commissioning the '{system_type}' in a Tier III data centre.\n\n"
                f"Context:\n{context}\n\n"
                "Format each step as:\nStep N: [Description] | Acceptance Criteria: [criteria]\n"
                "Include the source standard in parentheses where applicable."
            )
            result = self._groq.generate(prompt)
            if not result.get("error"):
                # Parse the LLM output into structured steps
                steps = _parse_rag_checklist(result["text"], chunks)
                if steps:
                    return steps

        # Fallback to hardcoded checklist
        logger.info("RAG unavailable or low score — using fallback checklist for '%s'", system_key)
        return _FALLBACK_CHECKLISTS.get(system_key, _FALLBACK_CHECKLISTS["power"])

    # ------------------------------------------------------------------
    # Test result validation (deterministic)
    # ------------------------------------------------------------------

    def validate_test_result(
        self, description: str, measured_value: str, acceptance_criteria: str
    ) -> dict[str, str]:
        """
        Simple deterministic validator — checks if measured value satisfies criteria.
        Returns {"status": "PASS" | "FAIL" | "MANUAL_REVIEW", "reason": str}
        """
        # Numeric comparison: extract numbers and compare
        measured_num = _extract_number(measured_value)
        criteria_parts = acceptance_criteria.strip()

        if measured_num is not None:
            # Handle comparison operators in criteria
            if criteria_parts.startswith("<"):
                threshold = _extract_number(criteria_parts)
                if threshold is not None:
                    status = "PASS" if measured_num < threshold else "FAIL"
                    return {"status": status, "reason": f"{measured_num} {'<' if status == 'PASS' else '≥'} {threshold}"}
            elif criteria_parts.startswith(">"):
                threshold = _extract_number(criteria_parts)
                if threshold is not None:
                    status = "PASS" if measured_num > threshold else "FAIL"
                    return {"status": status, "reason": f"{measured_num} {'>' if status == 'PASS' else '≤'} {threshold}"}
            elif "–" in criteria_parts or "-" in criteria_parts:
                # Range check
                parts = criteria_parts.replace("–", "-").split("-")
                if len(parts) == 2:
                    lo = _extract_number(parts[0])
                    hi = _extract_number(parts[1])
                    if lo is not None and hi is not None:
                        status = "PASS" if lo <= measured_num <= hi else "FAIL"
                        return {"status": status, "reason": f"{measured_num} {'in' if status == 'PASS' else 'outside'} range {lo}–{hi}"}

        # String-based pass/fail keywords
        lower_val = measured_value.lower()
        if any(k in lower_val for k in ("pass", "ok", "confirmed", "compliant", "yes")):
            return {"status": "PASS", "reason": "Observed result indicates pass"}
        if any(k in lower_val for k in ("fail", "no", "not", "rejected", "non-compliant")):
            return {"status": "FAIL", "reason": "Observed result indicates failure"}

        return {"status": "MANUAL_REVIEW", "reason": "Cannot auto-determine pass/fail — requires engineer review"}

    # ------------------------------------------------------------------
    # Test record generation
    # ------------------------------------------------------------------

    def generate_test_record(
        self,
        system_type: str,
        results: list[TestResult],
        project_name: str = "Data Centre EPC Project",
        tester: str = "Site Engineer",
    ) -> TestRecord:
        """Create a structured TestRecord from a list of TestResult objects."""
        import uuid
        record = TestRecord(
            record_id=f"TR-{system_type.upper()[:4]}-{uuid.uuid4().hex[:6].upper()}",
            system_type=system_type,
            project_name=project_name,
            test_date=date.today().isoformat(),
            tester=tester,
            results=results,
        )
        return record

    def format_test_record_text(self, record: TestRecord) -> str:
        """
        Ask Gemini to format a TestRecord as a professional document string.
        Falls back to a plain-text template if Gemini fails.
        """
        results_text = "\n".join(
            f"Step {r.step}: {r.description} | Acceptance: {r.acceptance} | "
            f"Measured: {r.measured_value or 'N/A'} | Status: {r.status}"
            for r in record.results
        )
        prompt = (
            f"Format the following commissioning test data into a professional Test Record document "
            f"for a Tier III data centre.\n\n"
            f"Record ID: {record.record_id}\n"
            f"System: {record.system_type}\n"
            f"Project: {record.project_name}\n"
            f"Date: {record.test_date}\n"
            f"Tester: {record.tester}\n"
            f"Overall Status: {record.overall_status}\n\n"
            f"Test Results:\n{results_text}\n\n"
            "Include a formal header, test summary, results table, and sign-off section."
        )
        result = self._groq.generate(prompt)
        if result.get("error"):
            return _plain_text_record(record)
        return result["text"]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_number(s: str) -> float | None:
    """Extract the first numeric value from a string."""
    import re
    m = re.search(r"[\d]+\.?[\d]*", s)
    return float(m.group()) if m else None


def _parse_rag_checklist(text: str, chunks: list[dict]) -> list[dict]:
    """Parse Gemini-generated numbered checklist into step dicts."""
    import re
    steps = []
    # Match "Step N:" or "N." patterns
    pattern = r"(?:Step\s*)?(\d+)[:.]\s*(.+?)(?:\|\s*Acceptance Criteria:\s*(.+?))?(?=\n(?:Step\s*)?\d+[:.]|\Z)"
    for match in re.finditer(pattern, text, re.DOTALL):
        step_num = int(match.group(1))
        description = match.group(2).strip()
        acceptance = match.group(3).strip() if match.group(3) else "As per design specification"
        source = chunks[0]["source"] if chunks else "Standards"
        steps.append({
            "step": step_num,
            "description": description,
            "acceptance": acceptance,
            "source": source,
        })
    return steps


def _plain_text_record(record: TestRecord) -> str:
    lines = [
        f"COMMISSIONING TEST RECORD",
        f"Record ID: {record.record_id}",
        f"System: {record.system_type}",
        f"Project: {record.project_name}",
        f"Date: {record.test_date}",
        f"Tester: {record.tester}",
        f"Overall Status: {record.overall_status}",
        f"{'='*60}",
        f"Passed: {record.pass_count}  |  Failed: {record.fail_count}",
        f"{'='*60}",
    ]
    for r in record.results:
        lines.append(
            f"Step {r.step}: {r.description}\n"
            f"  Acceptance: {r.acceptance}\n"
            f"  Measured:   {r.measured_value or 'N/A'}\n"
            f"  Status:     {r.status}\n"
            + (f"  Notes:      {r.notes}\n" if r.notes else "")
        )
    return "\n".join(lines)
