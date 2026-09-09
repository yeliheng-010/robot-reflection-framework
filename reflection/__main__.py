import argparse
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from . import contracts
from .adapters import DemoSimulator
from .engine import run_demo
from .storage import read_run, save_json


def main():
    parser = argparse.ArgumentParser(description="Robot feedback/reflection prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--scenario", choices=DemoSimulator.SCENARIOS, default="slip")
    demo.add_argument("--reflector", choices=("rule", "http"), default="rule")
    demo.add_argument("--max-reflections", type=int, default=3)
    demo.add_argument("--output", type=Path)
    replay = commands.add_parser("replay")
    replay.add_argument("events", type=Path)
    schemas = commands.add_parser("schemas")
    schemas.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        execute(args)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"Error: {type(exc).__name__}: {exc}\n")


def execute(args):
    if args.command == "replay":
        events = read_run(args.events)
        print(f"Validated {len(events)} events; replay did not execute actions.")
        print(events[-1].model_dump_json(indent=2))
    elif args.command == "schemas":
        args.output.mkdir(parents=True, exist_ok=True)
        for name in ("State", "Action", "Evidence", "Feedback", "Diagnosis", "Reflection", "Outcome", "Event"):
            save_json(args.output / f"{name}.schema.json", getattr(contracts, name).model_json_schema())
        print(f"Exported schemas to {args.output.resolve()}")
    else:
        reflector = None
        if args.reflector == "http":
            from .http_reflector import HttpReflector
            reflector = HttpReflector()
        directory = args.output or Path("runs") / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8])
        outcome = run_demo(directory, scenario=args.scenario,
                           max_reflections=args.max_reflections, reflector=reflector)
        print(outcome.model_dump_json(indent=2))
        print(f"Artifacts: {directory.resolve()}")
        if outcome.status == "component_error":
            raise RuntimeError("Run terminated because a component failed")


if __name__ == "__main__":
    main()
