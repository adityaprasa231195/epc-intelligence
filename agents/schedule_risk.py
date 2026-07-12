"""
Predictive Schedule Risk Engine

Deterministic CPM-style analysis:
  risk_score = max(0, lead_time_days - buffer_days)
  delay_days  = max(0, actual_start - planned_start)

Gemini generates mitigation narratives for at-risk tasks.
"""
import json
import os
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import config
from core.groq_client import GroqClient

logger = logging.getLogger(__name__)

# Pre-written mitigation templates keyed by category — used as Gemini fallback
_MITIGATION_FALLBACK: dict[str, list[str]] = {
    "Generator": [
        "Expedite factory testing and arrange express freight shipment.",
        "Identify qualified alternative generator supplier in the region.",
        "Negotiate temporary rental generator to bridge installation gap.",
    ],
    "UPS": [
        "Request vendor priority production slot with contractual penalty clause.",
        "Evaluate equivalent-rated UPS from approved vendor short-list.",
        "Pre-install battery strings and controls while awaiting main units.",
    ],
    "Cooling": [
        "Deploy temporary precision cooling units to maintain schedule.",
        "Accelerate civil works to allow parallel cooling installation.",
        "Engage second cooling contractor to split workload.",
    ],
    "Default": [
        "Escalate to project director and issue formal delay notice to vendor.",
        "Identify alternative procurement source for equivalent specification.",
        "Review schedule float and compress non-critical tasks to recover.",
    ],
}


@dataclass
class ScheduleTask:
    task_id: str
    name: str
    planned_start: date
    planned_end: date
    actual_start: date
    lead_time_days: int
    buffer_days: int
    dependencies: list[str]
    status: str

    @property
    def risk_score(self) -> int:
        return max(0, self.lead_time_days - self.buffer_days)

    @property
    def delay_days(self) -> int:
        delta = self.actual_start - self.planned_start
        return max(0, delta.days)

    @property
    def is_at_risk(self) -> bool:
        return self.risk_score > 0 or self.delay_days > 0


@dataclass
class ScheduleRiskReport:
    at_risk: list[dict] = field(default_factory=list)
    critical_path_violations: list[dict] = field(default_factory=list)
    on_track: list[dict] = field(default_factory=list)
    overall_risk: str = "LOW"
    mitigations: dict[str, list[str]] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "total_tasks": len(self.at_risk) + len(self.on_track),
            "at_risk_count": len(self.at_risk),
            "critical_violations": len(self.critical_path_violations),
            "overall_risk": self.overall_risk,
        }


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _equipment_category(name: str) -> str:
    name_l = name.lower()
    if "generator" in name_l:
        return "Generator"
    if "ups" in name_l or "battery" in name_l:
        return "UPS"
    if "cool" in name_l or "chiller" in name_l or "crac" in name_l:
        return "Cooling"
    return "Default"


class ScheduleRiskEngine:
    """Deterministic schedule risk analyser + LLM mitigation generator."""

    def __init__(self) -> None:
        self._groq = GroqClient()
        self._tasks: list[ScheduleTask] = []
        self._load_schedule()

    def _load_schedule(self) -> None:
        path = os.path.join(config.SYNTHETIC_DIR, "project_schedule.json")
        if not os.path.exists(path):
            logger.warning("project_schedule.json not found at %s", path)
            return
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        for t in raw:
            self._tasks.append(
                ScheduleTask(
                    task_id=t["task_id"],
                    name=t["name"],
                    planned_start=_parse_date(t["planned_start"]),
                    planned_end=_parse_date(t["planned_end"]),
                    actual_start=_parse_date(t["actual_start"]),
                    lead_time_days=t["lead_time_days"],
                    buffer_days=t["buffer_days"],
                    dependencies=t["dependencies"],
                    status=t["status"],
                )
            )
        logger.info("Loaded %d schedule tasks", len(self._tasks))

    # ------------------------------------------------------------------
    # Critical path detection (zero-float tasks)
    # ------------------------------------------------------------------

    def _find_critical_path(self) -> set[str]:
        """
        Tasks whose delay directly causes the project end-date to slip.
        Simplified: tasks with DELAYED status that appear in others' dependency chains.
        """
        delayed_ids = {t.task_id for t in self._tasks if t.status == "DELAYED"}
        # find tasks whose dependencies include a delayed task
        critical: set[str] = set(delayed_ids)
        for t in self._tasks:
            if any(dep in delayed_ids for dep in t.dependencies):
                critical.add(t.task_id)
        return critical

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------

    def analyse(self, skip_mitigations: bool = False) -> ScheduleRiskReport:
        report = ScheduleRiskReport()
        critical_ids = self._find_critical_path()

        for task in self._tasks:
            row = {
                "task_id": task.task_id,
                "name": task.name,
                "status": task.status,
                "planned_start": task.planned_start.isoformat(),
                "planned_end": task.planned_end.isoformat(),
                "actual_start": task.actual_start.isoformat(),
                "lead_time_days": task.lead_time_days,
                "buffer_days": task.buffer_days,
                "risk_score": task.risk_score,
                "delay_days": task.delay_days,
                "on_critical_path": task.task_id in critical_ids,
                "dependencies": task.dependencies,
            }

            if task.task_id in critical_ids and (task.risk_score > 0 or task.delay_days > 0):
                report.critical_path_violations.append(row)
                report.at_risk.append(row)
            elif task.is_at_risk:
                report.at_risk.append(row)
            else:
                report.on_track.append(row)

        # Determine overall risk level
        if report.critical_path_violations:
            report.overall_risk = "HIGH"
        elif len(report.at_risk) > 3:
            report.overall_risk = "MEDIUM"
        else:
            report.overall_risk = "LOW"

        # Generate mitigations for at-risk tasks (skipped on page load to save API quota)
        if not skip_mitigations:
            for row in report.at_risk:
                report.mitigations[row["task_id"]] = self._generate_mitigations(row)

        return report

    # ------------------------------------------------------------------
    # Mitigation generation (Gemini + deterministic fallback)
    # ------------------------------------------------------------------

    def _generate_mitigations(self, task_row: dict) -> list[str]:
        prompt = (
            f"You are a data centre EPC project manager.\n"
            f"Task: {task_row['name']}\n"
            f"Status: {task_row['status']}\n"
            f"Lead time: {task_row['lead_time_days']} days | Buffer: {task_row['buffer_days']} days | "
            f"Risk score: {task_row['risk_score']} | Delay: {task_row['delay_days']} days\n"
            f"Critical path: {'YES' if task_row['on_critical_path'] else 'NO'}\n\n"
            "Generate exactly 3 specific, actionable mitigation options to recover schedule. "
            "Each option must be on a new line starting with a dash (-)."
        )
        result = self._groq.generate(prompt)
        if result.get("error"):
            category = _equipment_category(task_row["name"])
            return _MITIGATION_FALLBACK.get(category, _MITIGATION_FALLBACK["Default"])

        # Parse dash-separated list from Groq response
        lines = [
            line.lstrip("- ").strip()
            for line in result["text"].splitlines()
            if line.strip().startswith("-")
        ]
        if not lines:
            # Fallback if Groq didn't format with dashes
            category = _equipment_category(task_row["name"])
            return _MITIGATION_FALLBACK.get(category, _MITIGATION_FALLBACK["Default"])
        return lines[:3]
