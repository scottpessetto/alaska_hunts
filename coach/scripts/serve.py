#!/usr/bin/env python3
"""
Lightweight web server for browsing coaching data from iPhone over Tailscale.

Usage:
    python3 serve.py              # Start on port 8080
    python3 serve.py --port 9090  # Custom port

Access from iPhone: http://your-mac-mini:8080 (over Tailscale)

Serves:
  /                  → Dashboard with latest briefing + links
  /daily             → List of daily briefings
  /weekly            → List of weekly analyses
  /daily/2026-04-08  → Specific daily briefing
  /weekly/2026-W15   → Specific weekly analysis
  /context           → Current athlete context
  /checkin           → Recent check-ins
"""

import argparse
import html
import re
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

COACH_DIR = Path.home() / "claude" / "coach"

STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, system-ui, sans-serif;
    background: #0d1117; color: #e6edf3;
    max-width: 720px; margin: 0 auto; padding: 16px;
    line-height: 1.6;
  }
  a { color: #58a6ff; text-decoration: none; }
  a:hover { text-decoration: underline; }
  h1 { font-size: 1.4em; margin-bottom: 12px; color: #f0f6fc; }
  h2 { font-size: 1.15em; margin: 16px 0 8px; color: #8b949e; }
  .card {
    background: #161b22; border: 1px solid #30363d;
    border-radius: 8px; padding: 16px; margin: 12px 0;
  }
  .card h3 { font-size: 1em; margin-bottom: 8px; color: #58a6ff; }
  .nav { display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }
  .nav a {
    background: #21262d; border: 1px solid #30363d;
    padding: 8px 16px; border-radius: 6px; font-size: 0.9em;
  }
  .nav a:hover { background: #30363d; text-decoration: none; }
  .content { white-space: pre-wrap; font-size: 0.9em; }
  .list a { display: block; padding: 6px 0; border-bottom: 1px solid #21262d; }
  .label { color: #8b949e; font-size: 0.85em; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0; }
  th, td { border: 1px solid #30363d; padding: 6px 10px; text-align: left; font-size: 0.85em; }
  th { background: #161b22; }
</style>
"""


def md_to_html(text: str) -> str:
    """Minimal Markdown to HTML conversion for briefings."""
    lines = text.split("\n")
    out = []
    in_table = False

    for line in lines:
        stripped = line.strip()

        # Tables
        if stripped.startswith("|") and "|" in stripped[1:]:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.match(r"^[-:]+$", c) for c in cells):
                continue  # skip separator row
            if not in_table:
                out.append("<table>")
                in_table = True
                tag = "th"
            else:
                tag = "td"
            row = "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells)
            out.append(f"<tr>{row}</tr>")
            continue
        elif in_table:
            out.append("</table>")
            in_table = False

        # Headers
        if stripped.startswith("# "):
            out.append(f"<h1>{html.escape(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{html.escape(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            out.append(f"<h3>{html.escape(stripped[4:])}</h3>")
        elif stripped.startswith("- "):
            out.append(f"<li>{html.escape(stripped[2:])}</li>")
        elif stripped.startswith("*") and stripped.endswith("*"):
            out.append(f"<p><em>{html.escape(stripped.strip('*'))}</em></p>")
        elif stripped == "":
            out.append("<br>")
        elif stripped == "---":
            out.append("<hr>")
        else:
            # Bold
            converted = re.sub(
                r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html.escape(stripped)
            )
            out.append(f"<p>{converted}</p>")

    if in_table:
        out.append("</table>")

    return "\n".join(out)


def list_files(directory: Path, pattern: str = "*.md") -> list[Path]:
    """List files sorted newest first."""
    if not directory.exists():
        return []
    return sorted(directory.glob(pattern), reverse=True)


class CoachHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.rstrip("/") or "/"

        if path == "/":
            self.serve_dashboard()
        elif path == "/daily":
            self.serve_list("daily")
        elif path == "/weekly":
            self.serve_list("weekly")
        elif path.startswith("/daily/"):
            self.serve_file("daily", path[7:])
        elif path.startswith("/weekly/"):
            self.serve_file("weekly", path[8:])
        elif path == "/context":
            self.serve_context()
        elif path == "/checkin":
            self.serve_checkins()
        else:
            self.send_error(404)

    def serve_page(self, title: str, body: str):
        content = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
{STYLE}
</head><body>
<div class="nav">
  <a href="/">Dashboard</a>
  <a href="/daily">Daily</a>
  <a href="/weekly">Weekly</a>
  <a href="/context">Context</a>
  <a href="/checkin">Check-ins</a>
</div>
{body}
</body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def serve_dashboard(self):
        # Latest daily briefing
        daily_files = list_files(COACH_DIR / "output" / "daily")
        latest_daily = ""
        if daily_files:
            latest_daily = f"""<div class="card">
<h3><a href="/daily/{daily_files[0].stem}">{daily_files[0].stem} Daily Briefing</a></h3>
{md_to_html(daily_files[0].read_text())}
</div>"""

        # Latest weekly
        weekly_files = list_files(COACH_DIR / "output" / "weekly")
        latest_weekly = ""
        if weekly_files:
            latest_weekly = f"""<div class="card">
<h3><a href="/weekly/{weekly_files[0].stem}">Latest Weekly: {weekly_files[0].stem}</a></h3>
<p class="label">Click to view full analysis</p>
</div>"""

        # Days to race
        race_countdown = ""
        race_file = COACH_DIR / "config" / "race_profile.yaml"
        if race_file.exists():
            for line in race_file.read_text().splitlines():
                if line.startswith("date:"):
                    try:
                        race_date = date.fromisoformat(line.split(":")[1].strip().strip('"'))
                        days = (race_date - date.today()).days
                        if days > 0:
                            race_countdown = f'<div class="card"><h3>Penguin Ridge</h3><p style="font-size:2em;color:#58a6ff;">{days} days</p></div>'
                    except (ValueError, IndexError):
                        pass

        body = f"""<h1>Running Coach</h1>
{race_countdown}
{latest_daily}
{latest_weekly}"""

        self.serve_page("Running Coach", body)

    def serve_list(self, section: str):
        files = list_files(COACH_DIR / "output" / section)
        items = ""
        for f in files:
            items += f'<a href="/{section}/{f.stem}">{f.stem}</a>\n'

        body = f"""<h1>{"Daily Briefings" if section == "daily" else "Weekly Analyses"}</h1>
<div class="card list">
{items if items else "<p class='label'>No files yet</p>"}
</div>"""
        self.serve_page(f"{section.title()} - Coach", body)

    def serve_file(self, section: str, name: str):
        filepath = COACH_DIR / "output" / section / f"{name}.md"
        if not filepath.exists():
            self.send_error(404)
            return
        body = f"""<div class="card">{md_to_html(filepath.read_text())}</div>"""
        self.serve_page(f"{name} - Coach", body)

    def serve_context(self):
        filepath = COACH_DIR / "memory" / "athlete_context.md"
        if not filepath.exists():
            body = '<p class="label">No athlete context yet</p>'
        else:
            body = f"""<div class="card">{md_to_html(filepath.read_text())}</div>"""
        self.serve_page("Athlete Context", body)

    def serve_checkins(self):
        files = list_files(COACH_DIR / "data" / "checkins", "*.yaml")[:14]
        items = ""
        for f in files:
            content = f.read_text()
            # Extract a quick summary line
            effort = ""
            energy = ""
            for line in content.splitlines():
                if line.startswith("perceived_effort:"):
                    effort = line.split(":")[1].strip()
                if line.startswith("energy_level:"):
                    energy = line.split(":")[1].strip()
            summary = ""
            if effort:
                summary += f" | Effort: {effort}/10"
            if energy:
                summary += f" | Energy: {energy}/10"
            items += f'<div class="card"><h3>{f.stem}</h3><pre class="content">{html.escape(content)}</pre></div>\n'

        body = f"""<h1>Recent Check-ins</h1>
{items if items else '<p class="label">No check-ins yet</p>'}"""
        self.serve_page("Check-ins - Coach", body)

    def log_message(self, format, *args):
        """Quiet logging — only errors."""
        if args and str(args[0]).startswith("4"):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="Coach web server")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Bind address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--dir", type=str, default=None, help="Override coach directory"
    )
    args = parser.parse_args()

    global COACH_DIR
    if args.dir:
        COACH_DIR = Path(args.dir)

    server = HTTPServer((args.host, args.port), CoachHandler)
    print(f"Coach server running at http://{args.host}:{args.port}")
    print(f"Serving data from {COACH_DIR}")
    print("Access from iPhone via Tailscale at http://your-mac-mini:8080")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
