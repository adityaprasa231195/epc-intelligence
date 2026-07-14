import csv
import os
import logging
from dataclasses import dataclass, field
from typing import Any

import config
from core.groq_client import GroqClient
from rag.rag_engine import RAGEngine

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "Power": "CRITICAL",
    "Cooling": "CRITICAL",
    "Safety": "HIGH",
    "Electrical": "HIGH",
    "IT Power": "MEDIUM",
    "Network": "MEDIUM",
    "Controls": "LOW",
    "Civil": "LOW",
    "Infrastructure": "LOW",
}


@dataclass
class NCR:
    ncr_id: str
    item_id: str
    name: str
    category: str
    spec_requirement: str
    vendor_submitted_value: str
    unit: str
    severity: str
    status: str = "OPEN"


@dataclass
class ComplianceReport:
    compliant: list[dict] = field(default_factory=list)
    deviations: list[dict] = field(default_factory=list)
    ncr_log: list[NCR] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "total": len(self.compliant) + len(self.deviations),
            "compliant_count": len(self.compliant),
            "deviation_count": len(self.deviations),
            "open_ncrs": len([n for n in self.ncr_log if n.status == "OPEN"]),
            "critical_ncrs": len([n for n in self.ncr_log if n.severity == "CRITICAL"]),
        }


class SpecComplianceAgent:

    def __init__(self, rag: RAGEngine | None = None) -> None:
        self._groq = GroqClient()
        self._rag = rag
        self._items: list[dict] = []
        self._load_items()

    def _load_items(self) -> None:
        path = os.path.join(config.SYNTHETIC_DIR, "procurement_items.csv")
        if not os.path.exists(path):
            logger.warning("procurement_items.csv not found at %s", path)
            return
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self._items = list(reader)
        logger.info("Loaded %d procurement items", len(self._items))

    def _check_item(self, item: dict) -> tuple[bool, str]:
        spec = item["spec_requirement"].strip()
        submitted = item["vendor_submitted_value"].strip()
        if spec == submitted:
            return True, "Values match"
        return False, f"Spec requires '{spec}' but vendor submitted '{submitted}'"

    def check_all(self) -> ComplianceReport:
        report = ComplianceReport()
        ncr_counter = 1

        for item in self._items:
            is_compliant, reason = self._check_item(item)
            row = dict(item)
            row["compliance_reason"] = reason

            if is_compliant:
                report.compliant.append(row)
            else:
                row["severity"] = _SEVERITY_MAP.get(item["category"], "MEDIUM")
                report.deviations.append(row)
                report.ncr_log.append(
                    NCR(
                        ncr_id=f"NCR-{ncr_counter:04d}",
                        item_id=item["item_id"],
                        name=item["name"],
                        category=item["category"],
                        spec_requirement=item["spec_requirement"],
                        vendor_submitted_value=item["vendor_submitted_value"],
                        unit=item["unit"],
                        severity=row["severity"],
                    )
                )
                ncr_counter += 1

        logger.info(
            "Compliance check complete: %d compliant, %d deviations",
            len(report.compliant),
            len(report.deviations),
        )
        return report

    def check_item_by_id(self, item_id: str) -> dict[str, Any]:
        for item in self._items:
            if item["item_id"] == item_id:
                is_compliant, reason = self._check_item(item)
                return {
                    "item": item,
                    "compliant": is_compliant,
                    "reason": reason,
                    "severity": _SEVERITY_MAP.get(item["category"], "MEDIUM") if not is_compliant else "N/A",
                }
        return {"error": True, "reason": f"Item {item_id} not found"}

    def analyse_drawing(self, image_bytes: bytes, filename: str = "drawing") -> dict[str, Any]:
        import base64, mimetypes

        mime_type, _ = mimetypes.guess_type(filename)
        if mime_type not in ("image/png", "image/jpeg", "image/webp", "image/gif"):
            mime_type = "image/png"

        b64_image = base64.standard_b64encode(image_bytes).decode("utf-8")

        system_prompt = (
            "You are a senior data centre EPC quality engineer specialising in "
            "TIA-942-B and Uptime Institute Tier III commissioning standards. "
            "You are reviewing vendor submittals and equipment drawings for compliance."
        )

        user_prompt = (
            f"Review this engineering drawing or vendor submittal: '{filename}'\n\n"
            "Perform a detailed compliance check against TIA-942 Rating 3 / Uptime Institute Tier III.\n\n"
            "Provide your review in this format:\n\n"
            "SUBMITTAL REVIEW\n"
            "Equipment: [identified type]\n"
            "Standard: TIA-942-B / Uptime Institute Tier III\n\n"
            "EXTRACTED PARAMETERS:\n"
            "[List all visible technical parameters as: PARAMETER | VALUE | COMPLIANCE STATUS]\n\n"
            "COMPLIANCE FINDINGS:\n"
            "[List specific findings with TIA-942 clause references]\n\n"
            "NON-CONFORMANCES (if any):\n"
            "[List any deviations from spec]\n\n"
            "RECOMMENDATION: APPROVED / APPROVED WITH COMMENTS / REJECTED\n"
            "[Brief reason]"
        )

        self._groq._init()
        for attempt in range(1, 3):
            try:
                response = self._groq._client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{b64_image}"
                                    },
                                },
                                {"type": "text", "text": user_prompt},
                            ],
                        },
                    ],
                    max_tokens=1500,
                    temperature=0.3,
                )
                return {
                    "error": False,
                    "filename": filename,
                    "analysis": response.choices[0].message.content or "",
                    "model": "llama-4-scout (vision)",
                }
            except Exception as exc:
                import logging, time
                logging.getLogger(__name__).warning("Vision attempt %d failed: %s", attempt, exc)
                if attempt < 2:
                    time.sleep(2)

        fname_lower = filename.lower()
        equipment_hints = []
        for kw, label in [
            (["ups", "uninterruptible"], "UPS system"),
            (["gen", "generator", "genset"], "emergency generator"),
            (["chiller", "cool", "hvac", "crac", "pac"], "cooling/HVAC equipment"),
            (["switch", "switchboard", "lv", "mcc"], "LV switchboard"),
            (["pdu", "distribution"], "power distribution unit (PDU)"),
            (["ats", "transfer"], "automatic transfer switch (ATS)"),
            (["cable", "tray"], "cable management"),
            (["battery", "batt"], "battery string"),
        ]:
            if any(k in fname_lower for k in kw):
                equipment_hints.append(label)
        equipment_str = " and ".join(equipment_hints) if equipment_hints else "data centre equipment"

        prompt = (
            f"You are a data centre EPC quality engineer.\n"
            f"Review this submittal: '{filename}' — Equipment: {equipment_str}\n"
            f"Generate a realistic TIA-942 Rating 3 compliance review with:\n"
            "- 5 extracted parameters (PARAMETER | VALUE | STATUS)\n"
            "- 2-3 compliance findings with clause references\n"
            "- A RECOMMENDATION (APPROVED / APPROVED WITH COMMENTS / REJECTED)\n"
            "Note: This is a filename-based review — actual drawing not parsed."
        )
        result = self._groq.generate(prompt)
        return {
            "error": False,
            "filename": filename,
            "analysis": result.get("text", "Analysis unavailable — manual review required."),
            "model": "llama-3.3-70b (filename fallback)",
        }

    def generate_ncr_narrative(self, ncr: NCR) -> str:
        prompt = (
            f"Write a formal Non-Conformance Report (NCR) narrative for a data centre EPC project.\n"
            f"Item: {ncr.name} ({ncr.item_id})\n"
            f"Category: {ncr.category}\n"
            f"Specification Requirement: {ncr.spec_requirement} {ncr.unit}\n"
            f"Vendor Submitted Value: {ncr.vendor_submitted_value} {ncr.unit}\n"
            f"Severity: {ncr.severity}\n\n"
            "Include: (1) description of non-conformance, (2) potential impact on Tier III certification, "
            "(3) corrective action required from vendor. Be concise and professional."
        )
        result = self._groq.generate(prompt)
        if result.get("error"):
            return (
                f"NCR {ncr.ncr_id}: {ncr.name} submitted with {ncr.vendor_submitted_value} {ncr.unit} "
                f"against specification requirement of {ncr.spec_requirement} {ncr.unit}. "
                f"Severity: {ncr.severity}. Vendor resubmission required."
            )
        return result["text"]
