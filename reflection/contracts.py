"""Typed messages. Python objects internally; JSON at storage/API boundaries."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def new_id() -> str:
    return str(uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class State(Message):
    state_id: str = Field(default_factory=new_id)
    environment: Literal["demo"] = "demo"
    epoch: int = Field(default=1, ge=1)
    frame_id: Literal["robot_base"] = "robot_base"
    observed_at: str = Field(default_factory=utc_now)
    object_id: str = "cube-01"
    holding: bool = False


class Action(Message):
    action_id: str = Field(default_factory=new_id)
    revision: int = Field(default=1, ge=1, strict=True)
    state_ref: str = "unbound"
    skill: Literal["grasp"] = "grasp"
    object_id: str = "cube-01"
    lift_speed_m_s: float = Field(default=0.08, ge=0.01, le=0.1)


class Evidence(Message):
    evidence_id: str = Field(default_factory=new_id)
    source: Literal["demo_fixture"] = "demo_fixture"
    claim: Literal["object_relative_displacement"] = "object_relative_displacement"
    value: float = Field(ge=0)
    threshold: float = Field(default=0.02, gt=0)
    unit: Literal["m"] = "m"
    frame_id: Literal["gripper_frame"] = "gripper_frame"


class Feedback(Message):
    feedback_id: str = Field(default_factory=new_id)
    trial_id: str = Field(default_factory=new_id)
    action_id: str
    action_revision: int = Field(ge=1)
    before_state_ref: str
    after_state: State
    status: Literal["success", "failure", "unknown"]
    stage: Literal["lifting"] = "lifting"
    error_code: Literal["OBJECT_SLIP", "MISSING_EVIDENCE"] | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    measured_grip_force_n: float | None = Field(default=None, ge=0)
    missing_evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_status(self):
        if self.status == "success" and (self.error_code or not self.evidence):
            raise ValueError("Success requires evidence and no error code")
        if self.status != "success" and not self.error_code:
            raise ValueError("Non-success requires an error code")
        return self


class Diagnosis(Message):
    diagnosis_id: str = Field(default_factory=new_id)
    feedback_ref: str
    symptom: str
    hypotheses: list[str]
    evidence_refs: list[str]
    unknowns: list[str]


class Reflection(Message):
    reflection_id: str = Field(default_factory=new_id)
    feedback_ref: str
    action_id: str
    base_revision: int = Field(ge=1, strict=True)
    decision: Literal["revise", "stop"]
    hypothesis: str = Field(min_length=1)
    hypothesis_status: Literal["untested"] = "untested"
    reason: str = Field(min_length=1)
    evidence_refs: list[str]
    parameter: Literal["lift_speed_m_s"] = "lift_speed_m_s"
    old_speed_m_s: float = Field(ge=0.01, le=0.1)
    new_speed_m_s: float | None = Field(default=None, ge=0.01, le=0.1)

    @model_validator(mode="after")
    def revision_needs_value(self):
        if self.decision == "revise" and self.new_speed_m_s is None:
            raise ValueError("Revision requires new_speed_m_s")
        return self


class Outcome(Message):
    status: Literal["success", "stopped", "budget_exhausted", "component_error"]
    reason: str
    trials: int = Field(ge=0)
    reflections: int = Field(ge=0)
    environment: Literal["demo"] = "demo"
    final_action: Action


class Event(Message):
    schema_version: Literal["0.1.0"] = "0.1.0"
    event_id: str = Field(default_factory=new_id)
    run_id: str
    sequence: int = Field(ge=1)
    event_type: str
    emitted_at: str = Field(default_factory=utc_now)
    parent_event_ids: list[str]
    payload: dict
