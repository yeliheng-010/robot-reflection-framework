"""Deterministic validation owns the execution decision, not the reflector."""

from .contracts import Action, Diagnosis, Feedback, Reflection


def validate_feedback(action: Action, feedback: Feedback) -> Feedback:
    feedback = Feedback.model_validate(feedback.model_dump())
    if (feedback.action_id, feedback.action_revision) != (action.action_id, action.revision):
        raise ValueError("Feedback belongs to a different action version")
    if feedback.before_state_ref != action.state_ref:
        raise ValueError("Feedback belongs to a different initial state")
    if feedback.after_state.object_id != action.object_id:
        raise ValueError("Feedback belongs to a different object")
    return feedback


def passed(feedback: Feedback) -> bool:
    return (feedback.status == "success" and feedback.after_state.holding
            and "object_pose" not in feedback.missing_evidence
            and bool(feedback.evidence)
            and all(e.value <= e.threshold for e in feedback.evidence))


def diagnose(feedback: Feedback) -> Diagnosis:
    hypotheses = ["Lifting speed may affect grip stability",
                  "Contact geometry or grip may be unstable"]
    return Diagnosis(
        feedback_ref=feedback.feedback_id,
        symptom=feedback.error_code or "GOAL_NOT_CONFIRMED",
        hypotheses=hypotheses if feedback.error_code == "OBJECT_SLIP" else [],
        evidence_refs=[e.evidence_id for e in feedback.evidence],
        unknowns=feedback.missing_evidence,
    )


def apply_correction(action: Action, proposal: Reflection, feedback: Feedback) -> Action:
    proposal = Reflection.model_validate(proposal.model_dump())
    if proposal.decision != "revise":
        raise ValueError("No revision requested")
    if (proposal.action_id, proposal.base_revision) != (action.action_id, action.revision):
        raise ValueError("Stale correction")
    if proposal.feedback_ref != feedback.feedback_id:
        raise ValueError("Correction cites a different feedback bundle")
    available = {e.evidence_id for e in feedback.evidence}
    if not proposal.evidence_refs or not set(proposal.evidence_refs) <= available:
        raise ValueError("Correction requires existing evidence")
    if proposal.old_speed_m_s != action.lift_speed_m_s:
        raise ValueError("Old parameter does not match")
    if proposal.new_speed_m_s == action.lift_speed_m_s:
        raise ValueError("No-op correction")
    data = action.model_dump()
    data.update(revision=action.revision + 1, lift_speed_m_s=proposal.new_speed_m_s)
    return Action.model_validate(data)
