#!/usr/bin/env python3
"""
Daily athlete check-in CLI for Mountain Running Coach.

Usage:
    python3 checkin.py              # Check in for today
    python3 checkin.py --date 2026-04-07   # Check in for a specific date
    python3 checkin.py --quick       # Quick mode: effort, energy, notes only
"""

import argparse
import sys
from datetime import datetime, date
from pathlib import Path

COACH_DIR = Path.home() / "claude" / "coach"
CHECKINS_DIR = COACH_DIR / "data" / "checkins"


def prompt_bool(question: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        raw = input(question + suffix).strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please enter y or n.")


def prompt_int(question: str, min_val: int, max_val: int) -> int:
    while True:
        raw = input(f"{question} ({min_val}-{max_val}): ").strip()
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(f"  Must be between {min_val} and {max_val}.")
        except ValueError:
            print("  Please enter a number.")


def prompt_float(question: str, optional: bool = False):
    while True:
        raw = input(question + (" (enter to skip): " if optional else ": ")).strip()
        if raw == "" and optional:
            return None
        try:
            return float(raw)
        except ValueError:
            print("  Please enter a number.")


def prompt_choice(question: str, choices: list[str]) -> str:
    choices_str = "/".join(choices)
    while True:
        raw = input(f"{question} ({choices_str}): ").strip().lower()
        for c in choices:
            if raw == c or (len(raw) >= 1 and c.startswith(raw)):
                return c
        print(f"  Choose one of: {choices_str}")


def prompt_text(question: str, optional: bool = False):
    suffix = " (enter to skip): " if optional else ": "
    raw = input(question + suffix).strip()
    if raw == "" and optional:
        return None
    if raw == "" and not optional:
        while raw == "":
            raw = input("  Required. " + question + ": ").strip()
    return raw


def format_yaml(data: dict) -> str:
    """Format dict as YAML without requiring PyYAML."""
    lines = []
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, str):
            if "\n" in value or ":" in value or "#" in value:
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def display_summary(data: dict):
    print("\n" + "=" * 50)
    print("  CHECK-IN SUMMARY")
    print("=" * 50)
    for key, value in data.items():
        if value is not None:
            label = key.replace("_", " ").title()
            print(f"  {label}: {value}")
    print("=" * 50)


def collect_full_checkin(target_date: date) -> dict:
    print(f"\nDaily Check-in for {target_date.strftime('%A, %B %d, %Y')}")
    print("-" * 50)

    data = {"date": target_date.isoformat()}
    data["timestamp"] = datetime.now().isoformat(timespec="seconds")

    # Workout
    print("\n-- Workout --")
    data["workout_completed"] = prompt_bool("Workout completed?")
    if data["workout_completed"]:
        data["workout_type"] = prompt_choice(
            "Workout type",
            ["easy", "hills", "long", "tempo", "intervals", "cross", "rest"],
        )
        data["workout_notes"] = prompt_text("Workout notes", optional=True)
    else:
        data["workout_type"] = "rest"
        data["workout_notes"] = prompt_text("Why no workout?", optional=True)

    # Body metrics
    print("\n-- How You Feel --")
    data["perceived_effort"] = prompt_int("Perceived effort", 1, 10)
    data["energy_level"] = prompt_int("Energy level", 1, 10)

    # Sleep
    print("\n-- Sleep --")
    data["sleep_quality"] = prompt_int("Sleep quality", 1, 10)
    data["sleep_hours"] = prompt_float("Hours slept")

    # Nutrition & hydration
    print("\n-- Nutrition & Hydration --")
    data["nutrition_quality"] = prompt_int("Nutrition quality", 1, 10)
    data["hydration"] = prompt_choice("Hydration", ["poor", "fair", "good", "excellent"])

    # Mental state
    print("\n-- Mental --")
    data["stress_level"] = prompt_int("Stress level", 1, 10)
    data["mood"] = prompt_int("Mood", 1, 10)

    # Optional
    print("\n-- Optional --")
    data["weight_lbs"] = prompt_float("Weight (lbs)", optional=True)
    data["pain_niggles"] = prompt_text("Pain or niggles?", optional=True)
    data["notes"] = prompt_text("Any other notes?", optional=True)

    return data


def collect_quick_checkin(target_date: date) -> dict:
    print(f"\nQuick Check-in for {target_date.strftime('%A, %B %d, %Y')}")
    print("-" * 50)

    data = {"date": target_date.isoformat()}
    data["timestamp"] = datetime.now().isoformat(timespec="seconds")
    data["quick_mode"] = True

    data["workout_completed"] = prompt_bool("Workout completed?")
    if data["workout_completed"]:
        data["workout_type"] = prompt_choice(
            "Workout type",
            ["easy", "hills", "long", "tempo", "intervals", "cross", "rest"],
        )

    data["perceived_effort"] = prompt_int("Perceived effort", 1, 10)
    data["energy_level"] = prompt_int("Energy level", 1, 10)
    data["notes"] = prompt_text("Notes", optional=True)

    return data


def main():
    parser = argparse.ArgumentParser(description="Daily athlete check-in")
    parser.add_argument("--date", type=str, help="Date for check-in (YYYY-MM-DD)")
    parser.add_argument(
        "--quick", action="store_true", help="Quick mode: minimal fields"
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=None,
        help="Override coach directory (default: ~/claude/coach)",
    )
    args = parser.parse_args()

    # Resolve directories
    coach_dir = Path(args.dir) if args.dir else COACH_DIR
    checkins_dir = coach_dir / "data" / "checkins"
    checkins_dir.mkdir(parents=True, exist_ok=True)

    # Determine date
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = date.today()

    # Check for existing file
    output_path = checkins_dir / f"{target_date.isoformat()}.yaml"
    if output_path.exists():
        if not prompt_bool(f"\nCheck-in for {target_date} already exists. Overwrite?", default=False):
            print("Cancelled.")
            sys.exit(0)

    # Collect data
    if args.quick:
        data = collect_quick_checkin(target_date)
    else:
        data = collect_full_checkin(target_date)

    # Show summary and confirm
    display_summary(data)
    if not prompt_bool("\nSave this check-in?"):
        print("Discarded.")
        sys.exit(0)

    # Write YAML
    yaml_content = format_yaml(data)
    output_path.write_text(yaml_content)
    print(f"\nSaved to {output_path}")

    # Flag pain/niggles
    if data.get("pain_niggles"):
        print("\nNote: pain/niggle reported. This will be flagged in tomorrow's briefing.")


if __name__ == "__main__":
    main()
