import pandas as pd
import requests
import os

state = {
    "previous_allocations": {},
    "emergency_reserve": 0
}

PRIORITY = {
    "hospital": 5,
    "domestic": 4,
    "agriculture": 3,
    "industry": 2
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_data():
    zones = pd.read_excel(os.path.join(BASE_DIR, "zones.xlsx"))
    reservoirs = pd.read_excel(os.path.join(BASE_DIR, "reservoirs.xlsx"))
    rainfall = pd.read_excel(os.path.join(BASE_DIR, "rainfall.xlsx"))
    demand = pd.read_excel(os.path.join(BASE_DIR, "demand.xlsx"))
    policies = pd.read_excel(os.path.join(BASE_DIR, "policies.xlsx"))

    for df in [zones, reservoirs, rainfall, demand, policies]:
        df.columns = df.columns.str.strip().str.lower()

    return zones, reservoirs, rainfall, demand, policies


def get_active_policy(policies):
    return policies.iloc[0]


def compute_usable_supply(reservoirs, rainfall, reserve):

    total_supply = (
        reservoirs["current_level_ml"].sum()
        + reservoirs["inflow_ml"].sum()
        - reservoirs["outflow_ml"].sum()
    )

    drought_flag = rainfall.iloc[0]["drought_flag"]

    total_supply -= reserve

    if str(drought_flag).lower() == "yes":
        total_supply *= 0.8

    return round(total_supply, 2), drought_flag


def aggregate_demand(demand_df):
    grouped = demand_df.groupby("sector")["demand_ml"].sum()
    return grouped.to_dict()


def detect_anomalies(demand_df):
    anomalies = set()

    for _, row in demand_df.iterrows():
        if row["demand_ml"] > row["avg_past_demand_ml"] * 1.4:
            anomalies.add(f"Spike detected in {row['zone_id']} ({row['sector']})")

    return list(anomalies)


def weighted_allocation(demand_dict, supply):

    total_demand = sum(demand_dict.values())
    allocations = {}

    if total_demand <= supply:
        allocations = demand_dict.copy()
    else:
        weighted_total = sum(
            demand_dict[s] * PRIORITY[s] for s in demand_dict
        )

        for sector in demand_dict:
            share = (
                demand_dict[sector] * PRIORITY[sector]
            ) / weighted_total
            allocations[sector] = round(share * supply, 2)

    return allocations, total_demand


def enforce_zero_cut(zones, demand_dict, allocations):

    critical_zones = zones[zones["zero_cut_rule"] == "yes"]

    for _, row in critical_zones.iterrows():
        sector = row["zone_type"]
        if sector in allocations:
            if allocations[sector] < demand_dict.get(sector, 0):
                allocations[sector] = demand_dict[sector]

    return allocations


def enforce_hospital_min(policy, allocations):
    min_required = policy["hospital_min_guarantee_ml"]

    if allocations.get("hospital", 0) < min_required:
        allocations["hospital"] = min_required

    return allocations


def enforce_agriculture_cap(policy, allocations, supply):

    max_pct = policy["max_agriculture_share_pct"]
    max_allowed = supply * (max_pct / 100)

    if allocations.get("agriculture", 0) > max_allowed:
        allocations["agriculture"] = round(max_allowed, 2)

    return allocations


def apply_peak_policy(policy, demand_df, allocations):

    peak_active = demand_df["peak_flag"].str.lower().eq("yes").any()

    if peak_active:
        reduction_pct = policy["peak_hour_reduction_pct"]
        reduction_factor = (100 - reduction_pct) / 100

        for sector in allocations:
            if sector != "hospital":
                allocations[sector] = round(
                    allocations[sector] * reduction_factor, 2
                )

    return allocations


def policy_check(allocations, supply):
    if sum(allocations.values()) > supply:
        return False, "Allocation denied: exceeds usable supply."
    return True, "Policy compliant."


def source_selection():
    return {
        "hospital": "surface",
        "domestic": "surface",
        "agriculture": "groundwater",
        "industry": "groundwater"
    }


def generate_explanation(summary):

    prompt = f"""
You are a strict governance reporting AI.
Use ONLY the provided data.
Do not invent logic.

Decision Summary:
{summary}
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "gemma3:4b",
                "prompt": prompt,
                "stream": False
            }
        )

        result = response.json()

        if "response" in result:
            return result["response"]
        else:
            return f"Ollama error: {result}"

    except Exception as e:
        return f"AI Reporting Error: {str(e)}"


def run_water_bot():

    zones, reservoirs, rainfall, demand, policies = load_data()

    policy = get_active_policy(policies)
    state["emergency_reserve"] = policy["min_reserve_ml"]

    supply, drought = compute_usable_supply(
        reservoirs,
        rainfall,
        state["emergency_reserve"]
    )

    demand_dict = aggregate_demand(demand)

    allocations, total_demand = weighted_allocation(demand_dict, supply)

    allocations = enforce_zero_cut(zones, demand_dict, allocations)
    allocations = enforce_hospital_min(policy, allocations)
    allocations = enforce_agriculture_cap(policy, allocations, supply)
    allocations = apply_peak_policy(policy, demand, allocations)

    compliant, message = policy_check(allocations, supply)

    anomalies = detect_anomalies(demand)

    decision_summary = {
        "usable_supply": supply,
        "total_demand": total_demand,
        "drought": drought,
        "allocations": allocations,
        "anomalies": anomalies,
        "compliance_status": message
    }

    explanation = generate_explanation(decision_summary)

    return {
        "allocations": allocations,
        "anomalies": anomalies,
        "report": explanation,
        "summary": decision_summary
    }
