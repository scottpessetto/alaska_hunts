#!/usr/bin/env python3
"""
Send text/WhatsApp message via Twilio.

Usage:
    echo "Your briefing here" | python3 send_text.py
    python3 send_text.py --message "Quick test"
    python3 send_text.py --file output/daily/2026-04-08.md
    python3 send_text.py --file output/daily/2026-04-08.md --whatsapp
"""

import argparse
import os
import sys
from pathlib import Path

COACH_DIR = Path.home() / "claude" / "coach"
ENV_FILE = COACH_DIR / "config" / "twilio.env"
SMS_MAX_LEN = 1500  # Twilio SMS max is 1600, leave margin


def load_env():
    """Load Twilio credentials from twilio.env file."""
    env = {}
    if not ENV_FILE.exists():
        print(f"Error: {ENV_FILE} not found. Create it with:")
        print("  TWILIO_SID=your_sid")
        print("  TWILIO_TOKEN=your_token")
        print("  FROM_NUMBER=+1234567890")
        print("  TO_NUMBER=+1234567890")
        sys.exit(1)

    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()

    required = ["TWILIO_SID", "TWILIO_TOKEN", "FROM_NUMBER", "TO_NUMBER"]
    missing = [k for k in required if k not in env]
    if missing:
        print(f"Error: Missing keys in {ENV_FILE}: {', '.join(missing)}")
        sys.exit(1)

    return env


def truncate_for_sms(text: str) -> str:
    """Truncate message for SMS, keeping the most useful part."""
    if len(text) <= SMS_MAX_LEN:
        return text
    return text[:SMS_MAX_LEN - 40] + "\n\n... [truncated - full briefing saved locally]"


def send_message(body: str, whatsapp: bool = False):
    """Send via Twilio."""
    try:
        from twilio.rest import Client
    except ImportError:
        print("Error: twilio package not installed. Run: pip install twilio")
        sys.exit(1)

    env = load_env()
    client = Client(env["TWILIO_SID"], env["TWILIO_TOKEN"])

    from_number = env["FROM_NUMBER"]
    to_number = env["TO_NUMBER"]

    if whatsapp:
        from_number = f"whatsapp:{from_number}"
        to_number = f"whatsapp:{to_number}"
    else:
        body = truncate_for_sms(body)

    message = client.messages.create(
        body=body,
        from_=from_number,
        to=to_number,
    )

    print(f"Message sent: {message.sid} ({len(body)} chars, {'WhatsApp' if whatsapp else 'SMS'})")


def main():
    parser = argparse.ArgumentParser(description="Send coaching text via Twilio")
    parser.add_argument("--message", "-m", type=str, help="Message text")
    parser.add_argument("--file", "-f", type=str, help="Read message from file")
    parser.add_argument(
        "--whatsapp", "-w", action="store_true", help="Send via WhatsApp"
    )
    parser.add_argument("--dry-run", action="store_true", help="Print message without sending")
    args = parser.parse_args()

    # Get message content
    if args.file:
        path = Path(args.file)
        if not path.exists():
            path = COACH_DIR / args.file
        if not path.exists():
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        body = path.read_text()
    elif args.message:
        body = args.message
    elif not sys.stdin.isatty():
        body = sys.stdin.read()
    else:
        print("Error: Provide --message, --file, or pipe stdin.")
        sys.exit(1)

    if not body.strip():
        print("Error: Empty message.")
        sys.exit(1)

    if args.dry_run:
        print(f"--- DRY RUN ({'WhatsApp' if args.whatsapp else 'SMS'}) ---")
        print(body if args.whatsapp else truncate_for_sms(body))
        print(f"--- END ({len(body)} chars) ---")
        return

    send_message(body, whatsapp=args.whatsapp)


if __name__ == "__main__":
    main()
