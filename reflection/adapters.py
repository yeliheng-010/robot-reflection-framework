"""Replace Simulator with a real physics adapter; demo outcomes are fixtures."""

from typing import Protocol

from .contracts import Action, Evidence, Feedback, State


class Simulator(Protocol):
    def preview(self, action: Action, initial: State) -> Feedback: ...


class DemoSimulator:
    SCENARIOS = ("slip", "success", "persistent", "missing")
    STABLE_SPEED = 0.04
    SLIP_DISPLACEMENT = 0.06
    STABLE_DISPLACEMENT = 0.005

    def __init__(self, scenario: str = "slip"):
        if scenario not in self.SCENARIOS:
            raise ValueError("Unknown demo scenario")
        self.scenario = scenario

    def preview(self, action: Action, initial: State) -> Feedback:
        if action.state_ref != initial.state_id or action.object_id != initial.object_id:
            raise ValueError("Action does not match the initial state")
        # Deterministic fixtures exercise the protocol, not grasping physics.
        stable = self.scenario == "success" or (
            self.scenario == "slip" and action.lift_speed_m_s <= self.STABLE_SPEED
        )
        missing = self.scenario == "missing"
        evidence = [] if missing else [Evidence(
            value=self.STABLE_DISPLACEMENT if stable else self.SLIP_DISPLACEMENT
        )]
        return Feedback(
            action_id=action.action_id,
            action_revision=action.revision,
            before_state_ref=initial.state_id,
            after_state=State(object_id=initial.object_id, holding=stable),
            status="unknown" if missing else ("success" if stable else "failure"),
            error_code="MISSING_EVIDENCE" if missing else (None if stable else "OBJECT_SLIP"),
            evidence=evidence,
            missing_evidence=["object_pose", "grip_force"] if missing else ["grip_force"],
        )
