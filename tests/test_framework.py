import json
import tempfile
import unittest
from pathlib import Path

from reflection.adapters import DemoSimulator
from reflection.contracts import Action, Feedback, Reflection, State
from reflection.engine import run_demo
from reflection.policy import apply_correction
from reflection.policy import passed, validate_feedback
from reflection.reflectors import RuleReflector
from reflection.storage import read_run


class FrameworkTests(unittest.TestCase):
    def run_case(self, scenario="slip", **options):
        with tempfile.TemporaryDirectory() as directory:
            result = run_demo(Path(directory), scenario=scenario, **options)
            events = read_run(Path(directory) / "events.jsonl")
            return result, events

    def test_slip_recovers_with_new_revision(self):
        result, events = self.run_case()
        self.assertEqual("success", result.status)
        self.assertEqual(2, result.trials)
        self.assertEqual(1, result.reflections)
        actions = [e.payload for e in events if e.event_type == "action.proposed"]
        self.assertEqual([1, 2], [a["revision"] for a in actions])
        self.assertEqual([0.08, 0.03], [a["lift_speed_m_s"] for a in actions])

    def test_budget_zero_does_not_reflect(self):
        result, _ = self.run_case(max_reflections=0)
        self.assertEqual("budget_exhausted", result.status)
        self.assertEqual(0, result.reflections)
        self.assertEqual(1, result.trials)

    def test_missing_feedback_never_counts_as_success(self):
        result, _ = self.run_case("missing")
        self.assertEqual("stopped", result.status)

    def test_success_does_not_invent_reflection(self):
        result, _ = self.run_case("success")
        self.assertEqual("success", result.status)
        self.assertEqual(0, result.reflections)

    def test_persistent_failure_terminates(self):
        result, _ = self.run_case("persistent")
        self.assertNotEqual("success", result.status)
        self.assertLessEqual(result.trials, 4)

    def test_trials_preserve_initial_state(self):
        state = State()
        simulator = DemoSimulator("slip")
        first = simulator.preview(Action(state_ref=state.state_id), state)
        second = simulator.preview(Action(state_ref=state.state_id), state)
        self.assertFalse(state.holding)
        self.assertEqual(first.before_state_ref, second.before_state_ref)
        self.assertNotEqual(first.after_state.state_id, second.after_state.state_id)

    def test_feedback_roundtrip(self):
        state = State()
        report = DemoSimulator("slip").preview(Action(state_ref=state.state_id), state)
        self.assertEqual(report, Feedback.model_validate_json(report.model_dump_json()))
        self.assertIsNone(report.measured_grip_force_n)

    def test_success_with_missing_pose_does_not_pass(self):
        state = State()
        report = DemoSimulator("success").preview(Action(state_ref=state.state_id), state)
        report = report.model_copy(update={"missing_evidence": ["object_pose"]})
        self.assertFalse(passed(report))

    def test_feedback_for_other_object_is_rejected(self):
        state = State()
        action = Action(state_ref=state.state_id)
        report = DemoSimulator("success").preview(action, state)
        report = report.model_copy(update={"after_state": State(object_id="other")})
        with self.assertRaises(ValueError):
            validate_feedback(action, report)

    def test_action_rejects_invalid_numbers_and_extra_fields(self):
        for data in ({"lift_speed_m_s": float("nan")}, {"revision": 0},
                     {"lift_speed_m_s": -1.0}, {"force_n": 99}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                Action(**data)

    def correction_fixture(self):
        state = State()
        action = Action(state_ref=state.state_id)
        feedback = DemoSimulator("slip").preview(action, state)
        proposal = RuleReflector().reflect(action, feedback)
        return action, feedback, proposal

    def test_stale_revision_rejected(self):
        action, feedback, proposal = self.correction_fixture()
        proposal = proposal.model_copy(update={"base_revision": 9})
        with self.assertRaises(ValueError):
            apply_correction(action, proposal, feedback)

    def test_fabricated_evidence_rejected(self):
        action, feedback, proposal = self.correction_fixture()
        proposal = proposal.model_copy(update={"evidence_refs": ["invented"]})
        with self.assertRaises(ValueError):
            apply_correction(action, proposal, feedback)

    def test_same_parameter_is_not_a_correction(self):
        action, feedback, proposal = self.correction_fixture()
        proposal = proposal.model_copy(update={"new_speed_m_s": action.lift_speed_m_s})
        with self.assertRaises(ValueError):
            apply_correction(action, proposal, feedback)

    def test_unsafe_correction_rejected(self):
        action, feedback, proposal = self.correction_fixture()
        proposal = proposal.model_copy(update={"new_speed_m_s": 0.8})
        with self.assertRaises(ValueError):
            apply_correction(action, proposal, feedback)

    def test_output_directory_never_overwrites_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_demo(root)
            before = (root / "events.jsonl").read_bytes()
            with self.assertRaises(FileExistsError):
                run_demo(root)
            self.assertEqual(before, (root / "events.jsonl").read_bytes())

    def test_reflector_failure_is_recorded(self):
        class BrokenReflector:
            def reflect(self, action, feedback):
                raise ValueError("bad model output")
        result, events = self.run_case(reflector=BrokenReflector())
        self.assertEqual("component_error", result.status)
        self.assertIn("component.failed", [e.event_type for e in events])

    def test_replay_rejects_broken_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_demo(root)
            rows = (root / "events.jsonl").read_text().splitlines()
            event = json.loads(rows[-1])
            event["parent_event_ids"] = ["does-not-exist"]
            rows[-1] = json.dumps(event)
            bad = root / "bad.jsonl"
            bad.write_text("\n".join(rows), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_run(bad)


if __name__ == "__main__":
    unittest.main()
