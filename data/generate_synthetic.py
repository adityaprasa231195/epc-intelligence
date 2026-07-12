"""
Synthetic data generator — stdlib only (csv, json, random, datetime).
Run: python data/generate_synthetic.py

Produces inside data/synthetic/:
  - procurement_items.csv    (50 rows, 3-4 deliberate DEVIATION rows)
  - project_schedule.json    (15 tasks, 2 critical-path violations)
  - supplier_locations.json  (10 suppliers, 2 at-risk shipments)
  - rfis.json                (20 RFIs with resolutions)
"""
import csv
import json
import os
import random
from datetime import date, timedelta

random.seed(42)  # reproducible for demo

SYNTHETIC_DIR = os.path.join(os.path.dirname(__file__), "synthetic")
os.makedirs(SYNTHETIC_DIR, exist_ok=True)

# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _date_str(d: date) -> str:
    return d.isoformat()

def _future(days: int) -> date:
    return date.today() + timedelta(days=days)

def _past(days: int) -> date:
    return date.today() - timedelta(days=days)


# -----------------------------------------------------------------------
# 1. procurement_items.csv
# -----------------------------------------------------------------------

EQUIPMENT_SPECS = [
    # (name, category, spec_requirement, unit)
    ("UPS System A", "Power", "500kVA", "kVA"),
    ("UPS System B", "Power", "500kVA", "kVA"),
    ("Generator Set 1", "Power", "2000kW", "kW"),
    ("Generator Set 2", "Power", "2000kW", "kW"),
    ("Precision AC Unit 1", "Cooling", "150kW", "kW"),
    ("Precision AC Unit 2", "Cooling", "150kW", "kW"),
    ("Chiller Unit A", "Cooling", "500RT", "RT"),
    ("Chiller Unit B", "Cooling", "500RT", "RT"),
    ("Cooling Tower 1", "Cooling", "600RT", "RT"),
    ("Cooling Tower 2", "Cooling", "600RT", "RT"),
    ("Main LV Switchboard", "Electrical", "4000A", "A"),
    ("Sub LV Switchboard 1", "Electrical", "2000A", "A"),
    ("Sub LV Switchboard 2", "Electrical", "2000A", "A"),
    ("Busduct Riser A", "Electrical", "3200A", "A"),
    ("Busduct Riser B", "Electrical", "3200A", "A"),
    ("PDU Rack Unit 1", "IT Power", "32A", "A"),
    ("PDU Rack Unit 2", "IT Power", "32A", "A"),
    ("PDU Rack Unit 3", "IT Power", "32A", "A"),
    ("Top-of-Rack Switch 1", "Network", "48port-25G", "port"),
    ("Top-of-Rack Switch 2", "Network", "48port-25G", "port"),
    ("Core Router A", "Network", "100G", "G"),
    ("Core Router B", "Network", "100G", "G"),
    ("Fire Suppression Tank", "Safety", "5000L", "L"),
    ("FM200 Cylinder 1", "Safety", "100kg", "kg"),
    ("FM200 Cylinder 2", "Safety", "100kg", "kg"),
    ("VESDA Detector Array", "Safety", "Zone-A", "Zone"),
    ("BMS Controller", "Controls", "BACnet-IP", "Protocol"),
    ("DCIM Software License", "Controls", "1000-rack", "racks"),
    ("Containment System A", "Civil", "Hot-Aisle", "Type"),
    ("Containment System B", "Civil", "Hot-Aisle", "Type"),
    ("Raised Floor Panel 1", "Civil", "600x600mm", "mm"),
    ("Raised Floor Panel 2", "Civil", "600x600mm", "mm"),
    ("Cable Tray Section 1", "Civil", "300mm-GI", "mm"),
    ("Cable Tray Section 2", "Civil", "300mm-GI", "mm"),
    ("Cable Tray Section 3", "Civil", "300mm-GI", "mm"),
    ("Server Rack 42U A", "Infrastructure", "42U-800W", "U"),
    ("Server Rack 42U B", "Infrastructure", "42U-800W", "U"),
    ("Server Rack 42U C", "Infrastructure", "42U-800W", "U"),
    ("Lighting Panel LP1", "Electrical", "63A", "A"),
    ("Lighting Panel LP2", "Electrical", "63A", "A"),
    ("Earthing Strip 1", "Electrical", "50x6mm-Cu", "mm"),
    ("Earthing Strip 2", "Electrical", "50x6mm-Cu", "mm"),
    ("Transfer Switch ATS1", "Power", "4000A-Auto", "A"),
    ("Transfer Switch ATS2", "Power", "4000A-Auto", "A"),
    ("UPS Battery String 1", "Power", "192V-500Ah", "Ah"),
    ("UPS Battery String 2", "Power", "192V-500Ah", "Ah"),
    ("Fibre Patch Panel 1", "Network", "96port-LC", "port"),
    ("Fibre Patch Panel 2", "Network", "96port-LC", "port"),
    ("Emergency Lighting 1", "Safety", "90min-LED", "min"),
    ("Emergency Lighting 2", "Safety", "90min-LED", "min"),
]

# Row indices (0-based) that will be forced to DEVIATION for demo
FORCED_DEVIATIONS = {
    1: "480kVA",          # UPS System B  — under-spec
    6: "450RT",           # Chiller Unit A — under-spec
    18: "48port-10G",     # ToR Switch 1  — wrong speed
    44: "192V-400Ah",     # UPS Battery 1 — lower capacity
}

def build_procurement_csv() -> None:
    path = os.path.join(SYNTHETIC_DIR, "procurement_items.csv")
    fieldnames = [
        "item_id", "name", "category",
        "spec_requirement", "vendor_submitted_value",
        "unit", "status",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, (name, cat, spec_req, unit) in enumerate(EQUIPMENT_SPECS):
            if i in FORCED_DEVIATIONS:
                vendor_val = FORCED_DEVIATIONS[i]
                status = "DEVIATION"
            else:
                vendor_val = spec_req   # compliant
                status = "COMPLIANT"
            writer.writerow({
                "item_id": f"PROC-{i+1:03d}",
                "name": name,
                "category": cat,
                "spec_requirement": spec_req,
                "vendor_submitted_value": vendor_val,
                "unit": unit,
                "status": status,
            })
    print(f"  Created: {path}  ({len(EQUIPMENT_SPECS)} rows, {len(FORCED_DEVIATIONS)} deviations)")


# -----------------------------------------------------------------------
# 2. project_schedule.json
# -----------------------------------------------------------------------

SCHEDULE_TASKS = [
    # (name, depends_on, planned_duration_days, lead_time_days, buffer_days)
    ("Site Mobilisation",          [],               14, 0,  5),
    ("Structural Steel Works",     [0],              30, 0,  7),
    ("Civil & Flooring",           [1],              25, 0,  5),
    ("MEP Rough-In",               [2],              20, 0,  5),
    ("Generator Procurement",      [],               60, 65, 5),   # VIOLATION: lead > buffer
    ("Generator Installation",     [1, 4],           10, 0,  3),
    ("UPS Procurement",            [],               45, 48, 5),   # VIOLATION: lead > buffer
    ("UPS Installation",           [3, 6],           10, 0,  3),
    ("Cooling System Installation", [3],             20, 0,  5),
    ("Electrical Distribution",    [3, 7],           15, 0,  5),
    ("IT Infrastructure",          [9],              15, 0,  4),
    ("BMS & Controls",             [8, 9, 10],       10, 0,  3),
    ("Fire & Safety Systems",      [3],              10, 0,  3),
    ("Integrated System Testing",  [7, 8, 9, 10, 11, 12], 20, 0, 5),
    ("Commissioning & Handover",   [13],             10, 0,  3),
]

def build_schedule_json() -> None:
    tasks = []
    cursor = _past(90)  # project started 90 days ago

    for idx, (name, deps, duration, lead, buffer) in enumerate(SCHEDULE_TASKS):
        planned_start = cursor
        planned_end = cursor + timedelta(days=duration)

        # Tasks 4 and 6 are delayed (critical-path violations)
        if idx == 4:
            actual_start = planned_start + timedelta(days=8)
            status = "DELAYED"
        elif idx == 6:
            actual_start = planned_start + timedelta(days=10)
            status = "DELAYED"
        elif planned_end < date.today():
            actual_start = planned_start
            status = "COMPLETED"
        else:
            actual_start = planned_start
            status = "IN_PROGRESS" if planned_start <= date.today() else "NOT_STARTED"

        tasks.append({
            "task_id": f"SCH-{idx+1:03d}",
            "name": name,
            "planned_start": _date_str(planned_start),
            "planned_end": _date_str(planned_end),
            "actual_start": _date_str(actual_start),
            "lead_time_days": lead,
            "buffer_days": buffer,
            "dependencies": [f"SCH-{d+1:03d}" for d in deps],
            "status": status,
        })
        cursor = planned_end + timedelta(days=2)  # short lag between tasks

    path = os.path.join(SYNTHETIC_DIR, "project_schedule.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)
    print(f"  Created: {path}  ({len(tasks)} tasks, 2 critical-path violations)")


# -----------------------------------------------------------------------
# 3. supplier_locations.json
# -----------------------------------------------------------------------

SUPPLIERS = [
    # (name, equipment_type, origin_city, dest_city, lat, lon, shipment_status, eta_days)
    ("Cummins India",        "Generator Set",      "Pune",       "Mumbai",     18.52, 73.85, "IN_TRANSIT",  12),
    ("Vertiv India",         "UPS System",         "Pune",       "Mumbai",     18.52, 73.85, "IN_TRANSIT",   5),  # AT-RISK
    ("Schneider Electric",   "PDU Rack Unit",      "Bangalore",  "Mumbai",     12.97, 77.59, "DISPATCHED",  18),
    ("STULZ India",          "Precision AC Unit",  "Mumbai",     "Mumbai",     19.07, 72.87, "DELIVERED",    0),
    ("Paharpur Cooling",     "Cooling Tower",      "Kolkata",    "Mumbai",     22.57, 88.36, "IN_TRANSIT",   4),  # AT-RISK
    ("ABB India",            "LV Switchboard",     "Bangalore",  "Mumbai",     12.97, 77.59, "IN_TRANSIT",  22),
    ("Legrand India",        "Cable Tray",         "Chennai",    "Mumbai",     13.08, 80.27, "DISPATCHED",  15),
    ("Delta Electronics",    "Transfer Switch",    "Chennai",    "Mumbai",     13.08, 80.27, "IN_TRANSIT",   9),
    ("Havells India",        "Busduct Riser",      "Noida",      "Mumbai",     28.54, 77.39, "IN_TRANSIT",  11),
    ("Emerson Network",      "BMS Controller",     "Pune",       "Mumbai",     18.52, 73.85, "DELIVERED",    0),
]

def build_supplier_json() -> None:
    suppliers = []
    for i, (name, equip, orig, dest, lat, lon, status, eta) in enumerate(SUPPLIERS):
        suppliers.append({
            "supplier_id": f"SUP-{i+1:03d}",
            "name": name,
            "equipment_type": equip,
            "origin_city": orig,
            "destination_city": dest,
            "lat": lat,
            "lon": lon,
            "shipment_status": status,
            "eta_days": eta,
        })

    path = os.path.join(SYNTHETIC_DIR, "supplier_locations.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(suppliers, f, indent=2)
    print(f"  Created: {path}  ({len(suppliers)} suppliers, 2 at-risk shipments)")


# -----------------------------------------------------------------------
# 4. rfis.json
# -----------------------------------------------------------------------

RFIS_RAW = [
    ("RFI-001", "UPS Bypass Rating",
     "Drawing E-205 shows 800A bypass. Spec Section 16480 requires 1000A. Which takes precedence?",
     "Spec Section 16480 takes precedence. Vendor to resubmit with 1000A bypass rating. DR-001 raised.",
     "Spec 16480 Clause 4.2"),
    ("RFI-002", "Earthing Conductor Cross-Section",
     "Spec requires 50x6mm copper earthing strip but vendor has submitted 40x5mm. Is this acceptable?",
     "Not acceptable. 50x6mm is minimum per IS 3043. Vendor must comply. NCR-007 logged.",
     "Spec 16060 Clause 3.1"),
    ("RFI-003", "Cooling Tower Clearance",
     "Drawing M-110 shows 1.2m clearance between cooling towers. ASHRAE recommends 1.5m. Confirm?",
     "Revise layout to 1.5m minimum clearance per ASHRAE 90.1. M-110 Rev B issued.",
     "Spec 15720 Clause 2.4"),
    ("RFI-004", "Cable Tray Loading",
     "What is the maximum permissible cable load per metre for 300mm wide GI cable tray?",
     "Per IEC 61537: 300mm GI tray (1.5mm thickness) rated at 45kg/m. Confirmed with manufacturer.",
     "Spec 16130 Clause 5.3"),
    ("RFI-005", "Generator Auto-Start Delay",
     "Spec states mains failure to generator start within 10 seconds. Vendor confirms 15s. Acceptable?",
     "10 seconds is contractual requirement per Uptime Institute Tier III. Vendor must modify controller.",
     "Spec 16230 Clause 7.1"),
    ("RFI-006", "UPS Battery Room Ventilation",
     "VRLA batteries proposed. Spec requires forced ventilation. Is natural ventilation acceptable for VRLA?",
     "Natural ventilation acceptable for VRLA per IEEE 1187 if room volume exceeds 30m3. Confirmed.",
     "Spec 16480 Clause 6.5"),
    ("RFI-007", "Fire Suppression Discharge Time",
     "FM-200 system design shows 10-second discharge. TIA-942 requires less than 10 seconds. Confirm.",
     "Discharge must be ≤10 seconds per TIA-942-B Section 5.9. Redesign required — new calc submitted.",
     "TIA-942-B Section 5.9"),
    ("RFI-008", "Raised Floor Load Rating",
     "Drawing A-301 specifies 12kN/m2 raised floor. Server racks may exceed this. Confirm adequacy.",
     "12kN/m2 (1200 kg/m2) exceeds maximum rack density of 1000 kg/m2. Current spec is adequate.",
     "Spec 03300 Clause 4.1"),
    ("RFI-009", "Fibre Optic Cable Route",
     "Preferred cable route conflicts with structural beam at grid E-7. Alternate route via C-7 feasible?",
     "Route via C-7 approved. Drawing N-115 Rev C issued. No impact to critical path.",
     "Spec 27130 Clause 2.1"),
    ("RFI-010", "BMS Protocol Compatibility",
     "BMS controller supports BACnet/IP. DCIM vendor requires Modbus TCP. Interface gateway required?",
     "Provide BACnet/IP to Modbus TCP gateway — Anybus X-Gateway approved. Add to BOM.",
     "Spec 17500 Clause 3.2"),
    ("RFI-011", "Containment System Material",
     "Drawing M-205 shows aluminium containment. Spec says steel. Cost saving possible with aluminium?",
     "Steel containment required per fire rating requirements (FR-30). Aluminium not acceptable.",
     "Spec 15830 Clause 1.3"),
    ("RFI-012", "Generator Fuel Tank Capacity",
     "Spec requires 24h fuel autonomy at full load. Vendor tank is sized for 20h. Acceptable?",
     "24h autonomy is minimum per Tier III requirements. Vendor must upsize tank. NCR-012 raised.",
     "Spec 16230 Clause 4.8"),
    ("RFI-013", "VESDA Detector Spacing",
     "VESDA capillary tube spacing shown as 6m on drawing. AS 1603.6 recommends 5m. Confirm.",
     "Spacing must comply with AS 1603.6 maximum 5m. Drawing S-401 revised to 5m spacing.",
     "AS 1603.6 Clause 4.3"),
    ("RFI-014", "PDU Input Plug Type",
     "PDUs specified with IEC 309 3P+N+E 32A inlet. Busduct tap-offs are 63A. Adapter required?",
     "Provide 63A to 32A step-down pigtail adapter per IEC 60309. Add to electrical BOM.",
     "Spec 16490 Clause 2.6"),
    ("RFI-015", "Seismic Bracing for Racks",
     "Project site is in Zone II seismic area. Are server racks required to be seismically braced?",
     "Seismic bracing required per IS 1893 Zone II. Vendor to supply floor-anchoring kit for all racks.",
     "IS 1893 Clause 7.4"),
    ("RFI-016", "Emergency Power Off Button Location",
     "EPO button location not shown on drawings. Code requires at main entrance. Confirm location.",
     "EPO buttons to be located at each data hall entrance and at the main electrical room per NFPA 75.",
     "NFPA 75 Section 8.2"),
    ("RFI-017", "Hot Aisle Containment Door Width",
     "Containment end doors shown as 800mm wide. Racks are 800mm deep. Clearance issue — confirm.",
     "End doors must be minimum 900mm wide to accommodate rack depth plus cable management.",
     "Spec 15830 Clause 3.1"),
    ("RFI-018", "Grounding of Cable Trays",
     "Drawing E-310 does not show cable tray grounding lugs. Are grounding continuity bonds required?",
     "Continuous grounding required per NEC 392.60. Add grounding lugs at every 15m tray section.",
     "NEC 392.60"),
    ("RFI-019", "CRAC Unit Condensate Drainage",
     "Drawing M-115 shows condensate drain to nearest floor drain. Spec requires dedicated drain. Confirm.",
     "Dedicated condensate drain line required per spec. Drawing M-115 Rev D issued with dedicated route.",
     "Spec 15720 Clause 5.2"),
    ("RFI-020", "UPS System Parallel Redundancy",
     "Two UPS units specified in parallel. Confirm N+1 or 2N configuration required per Tier III?",
     "Tier III requires N+1 minimum. 2N configuration provided exceeds requirement — confirmed acceptable.",
     "Uptime Institute Tier III Section 3.5"),
]

def build_rfis_json() -> None:
    rfis = []
    for rfi_id, subject, question, resolution, clause in RFIS_RAW:
        rfis.append({
            "rfi_id": rfi_id,
            "subject": subject,
            "question": question,
            "resolution": resolution,
            "related_spec_clause": clause,
            "date": _date_str(_past(random.randint(5, 60))),
            "status": "CLOSED",
        })

    path = os.path.join(SYNTHETIC_DIR, "rfis.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rfis, f, indent=2)
    print(f"  Created: {path}  ({len(rfis)} RFIs)")


# -----------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------

if __name__ == "__main__":
    print("Generating synthetic project data...")
    build_procurement_csv()
    build_schedule_json()
    build_supplier_json()
    build_rfis_json()
    print("Done. All files written to data/synthetic/")
