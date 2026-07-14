import json
import os
import logging
from typing import Any

import config
from core.groq_client import GroqClient

logger = logging.getLogger(__name__)

_FALLBACK_ALTERNATIVES: dict[str, list[str]] = {
    "Generator Set":    ["Cummins India (Pune)", "Kirloskar Electric (Bangalore)", "Caterpillar India (Chennai)"],
    "UPS System":       ["Vertiv India (Pune)", "Schneider Electric (Bangalore)", "Emerson Network (Pune)"],
    "Precision AC Unit": ["STULZ India (Mumbai)", "Emerson Network (Pune)", "Uniflair (Bangalore)"],
    "Cooling Tower":    ["Paharpur Cooling (Kolkata)", "SPX Cooling (Mumbai)", "Evapco India (Pune)"],
    "LV Switchboard":   ["ABB India (Bangalore)", "Siemens India (Mumbai)", "L&T Electrical (Chennai)"],
    "PDU Rack Unit":    ["Schneider Electric (Bangalore)", "Vertiv India (Pune)", "Legrand India (Chennai)"],
    "Transfer Switch":  ["ABB India (Bangalore)", "Siemens India (Mumbai)", "Delta Electronics (Chennai)"],
    "BMS Controller":   ["Emerson Network (Pune)", "Honeywell India (Gurgaon)", "Johnson Controls (Mumbai)"],
    "Cable Tray":       ["Legrand India (Chennai)", "Niedax India (Mumbai)", "OBO Bettermann (Pune)"],
    "Busduct Riser":    ["Havells India (Noida)", "L&T Electrical (Chennai)", "Siemens India (Mumbai)"],
}

_FALLBACK_DEFAULT = ["Contact procurement team for approved vendor list", "Issue emergency RFQ to 3 alternate suppliers"]


class SupplyChainAgent:

    def __init__(self) -> None:
        self._groq = GroqClient()
        self._suppliers: list[dict] = []
        self._load_suppliers()

    def _load_suppliers(self) -> None:
        path = os.path.join(config.SYNTHETIC_DIR, "supplier_locations.json")
        if not os.path.exists(path):
            logger.warning("supplier_locations.json not found at %s", path)
            return
        with open(path, encoding="utf-8") as f:
            self._suppliers = json.load(f)
        logger.info("Loaded %d supplier records", len(self._suppliers))

    def get_at_risk(self, threshold_days: int = config.RISK_THRESHOLD_DAYS) -> list[dict]:
        return [
            s for s in self._suppliers
            if s["shipment_status"] != "DELIVERED" and s["eta_days"] < threshold_days
        ]

    def get_all(self) -> list[dict]:
        return list(self._suppliers)

    def get_delivered(self) -> list[dict]:
        return [s for s in self._suppliers if s["shipment_status"] == "DELIVERED"]

    def get_in_transit(self) -> list[dict]:
        return [s for s in self._suppliers if s["shipment_status"] in ("IN_TRANSIT", "DISPATCHED")]

    def get_alternatives(self, equipment_type: str, origin_country: str = "India") -> dict[str, Any]:
        prompt = (
            f"You are a data centre EPC procurement specialist in {origin_country}.\n"
            f"The primary supplier for '{equipment_type}' is at risk of missing the delivery deadline.\n"
            "Suggest exactly 3 alternative qualified suppliers available in India with:\n"
            "- Supplier name and city\n"
            "- Typical lead time in weeks\n"
            "- Any known certifications relevant to data centre equipment\n"
            "Format as a numbered list."
        )
        result = self._groq.generate(prompt)
        if result.get("error"):
            fallback = _FALLBACK_ALTERNATIVES.get(equipment_type, _FALLBACK_DEFAULT)
            return {
                "equipment_type": equipment_type,
                "source": "fallback",
                "alternatives": fallback,
            }
        return {
            "equipment_type": equipment_type,
            "source": "groq",
            "alternatives": result["text"],
        }

    def summary(self) -> dict[str, int]:
        at_risk = self.get_at_risk()
        return {
            "total_suppliers": len(self._suppliers),
            "delivered": len(self.get_delivered()),
            "in_transit": len(self.get_in_transit()),
            "at_risk": len(at_risk),
        }
