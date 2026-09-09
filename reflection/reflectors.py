"""Offline baseline and dependency-injected reflection interface."""

from typing import Protocol

from .contracts import Action, Feedback, Reflection


class Reflector(Protocol):
    def reflect(self, action: Action, feedback: Feedback) -> Reflection: ...


class RuleReflector:
    TARGET_SPEED = 0.03

    def reflect(self, action: Action, feedback: Feedback) -> Reflection:
        can_revise = (feedback.error_code == "OBJECT_SLIP" and feedback.evidence
                      and action.lift_speed_m_s > self.TARGET_SPEED)
        return Reflection(
            feedback_ref=feedback.feedback_id,
            action_id=action.action_id,
            base_revision=action.revision,
            decision="revise" if can_revise else "stop",
            hypothesis="Lifting speed may affect grip stability",
            reason=("Test lower speed; measured grip force is unavailable."
                    if can_revise else "No supported new correction in this baseline."),
            evidence_refs=[e.evidence_id for e in feedback.evidence],
            old_speed_m_s=action.lift_speed_m_s,
            new_speed_m_s=self.TARGET_SPEED if can_revise else None,
        )
