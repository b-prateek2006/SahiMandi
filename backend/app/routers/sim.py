"""Simulation API router for running 30-day season replays and fetching chart data."""

import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sim.run_simulation import run_simulation


router = APIRouter(prefix="/sim", tags=["simulation"])

# In-memory run cache (no 10th table added)
SIMULATION_RUNS: dict[str, dict] = {}
LATEST_RUN_ID: str | None = None


class RunSimulationInput(BaseModel):
    days: int = Field(default=30, ge=1, le=365)
    seed: int = Field(default=42)
    policy: str | None = Field(default="BOTH")


@router.post("/run")
def execute_simulation(data: RunSimulationInput = RunSimulationInput()):
    global LATEST_RUN_ID
    result = run_simulation(days=data.days, seed=data.seed)
    run_id = f"run_{uuid.uuid4().hex[:10]}"
    SIMULATION_RUNS[run_id] = result
    LATEST_RUN_ID = run_id
    return {
        "run_id": run_id,
        "days": result["days"],
        "seed": result["seed"],
        "headline": result["headline"],
    }


@router.get("/latest")
def get_latest_simulation():
    global LATEST_RUN_ID
    if LATEST_RUN_ID and LATEST_RUN_ID in SIMULATION_RUNS:
        return SIMULATION_RUNS[LATEST_RUN_ID]
    result = run_simulation(days=30, seed=42)
    run_id = "run_default"
    SIMULATION_RUNS[run_id] = result
    LATEST_RUN_ID = run_id
    return result


@router.get("/{run_id}/results")
def get_simulation_results(run_id: str):
    if run_id == "latest":
        return get_latest_simulation()
    if run_id not in SIMULATION_RUNS:
        raise HTTPException(status_code=404, detail="Simulation run not found.")
    return SIMULATION_RUNS[run_id]
