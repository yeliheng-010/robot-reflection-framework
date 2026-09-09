"""Bounded simulation/reflection loop. Never connects to physical hardware."""

from pathlib import Path

from .adapters import DemoSimulator
from .contracts import Action, Outcome, State
from .policy import apply_correction, diagnose, passed, validate_feedback
from .reflectors import RuleReflector
from .storage import EventStore, save_json


class ReflectionLoop:
    def __init__(self, store, *, simulator, reflector, max_reflections):
        self.store = store
        self.simulator = simulator
        self.reflector = reflector
        self.max_reflections = max_reflections
        self.state = State()
        self.action = Action(state_ref=self.state.state_id)
        self.trials = 0
        self.reflections = 0
        self.visited = set()

    def finish(self, status, reason):
        result = Outcome(status=status, reason=reason, trials=self.trials,
                         reflections=self.reflections, final_action=self.action)
        self.store.emit("outcome.evaluated", result)
        return result

    def run(self):
        self.store.emit("task.created", {
            "goal": "grasp cube-01 and hold", "environment": "demo",
            "max_reflections": self.max_reflections,
        })
        self.store.emit("state.published", self.state)
        while True:
            self.visited.add(self.action.lift_speed_m_s)
            self.store.emit("action.proposed", self.action)
            feedback = self.preview()
            if passed(feedback):
                return self.finish("success", "Demo holding predicate passed")
            if self.reflections >= self.max_reflections:
                return self.finish("budget_exhausted", "Reflection budget exhausted")
            if not self.revise(feedback):
                return self.finish("stopped", "Reflector stopped or repeated a candidate")

    def preview(self):
        self.store.emit("simulation.started", {"action_ref": self.action.action_id,
                        "revision": self.action.revision, "state_ref": self.state.state_id})
        self.trials += 1
        feedback = validate_feedback(self.action, self.simulator.preview(self.action, self.state))
        self.store.emit("state.published", feedback.after_state)
        for evidence in feedback.evidence:
            self.store.emit("evidence.recorded", evidence)
        self.store.emit("feedback.assembled", feedback)
        self.store.emit("verification.completed", {
            "feedback_ref": feedback.feedback_id, "action_id": self.action.action_id,
            "revision": self.action.revision, "passed": passed(feedback),
        })
        return feedback

    def revise(self, feedback):
        diagnosis = diagnose(feedback)
        self.store.emit("diagnosis.completed", diagnosis)
        self.store.emit("context.built", {
            "action": self.action.model_dump(), "feedback": feedback.model_dump(),
        })
        self.reflections += 1
        proposal = self.reflector.reflect(self.action, feedback)
        self.store.emit("reflection.proposed", proposal)
        if proposal.decision == "stop":
            return False
        updated = apply_correction(self.action, proposal, feedback)
        if updated.lift_speed_m_s in self.visited:
            self.store.emit("correction.rejected", {"reason": "repeated_candidate"})
            return False
        self.store.emit("correction.applied", {
            "reflection_ref": proposal.reflection_id, "feedback_ref": feedback.feedback_id,
            "old_action": self.action.model_dump(), "new_action": updated.model_dump(),
            "revalidation_required": True,
        })
        self.action = updated
        return True


def run_demo(directory: Path, *, scenario="slip", max_reflections=3, reflector=None):
    if type(max_reflections) is not int or not 0 <= max_reflections <= 20:
        raise ValueError("max_reflections must be an integer from 0 to 20")
    simulator = DemoSimulator(scenario)
    reflector = reflector or RuleReflector()
    store = EventStore(directory)
    loop = ReflectionLoop(store, simulator=simulator, reflector=reflector,
                          max_reflections=max_reflections)
    try:
        save_json(directory / "manifest.json", {
            "version": "0.1.0", "run_id": store.run_id, "environment": "demo",
            "scenario": scenario, "reflector": type(reflector).__name__,
            "max_reflections": max_reflections,
            "description": "Deterministic protocol fixture, not a physics experiment",
        })
        try:
            result = loop.run()
        except (ValueError, RuntimeError, TimeoutError) as exc:
            store.emit("component.failed", {"error_type": type(exc).__name__})
            result = loop.finish("component_error", "Component failed; inspect events")
        save_json(directory / "summary.json", result.model_dump(mode="json"))
        return result
    finally:
        store.close()
