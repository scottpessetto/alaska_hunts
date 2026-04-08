# Mountain Running Coach Automation

Automated coaching system for Penguin Ridge training. Runs on Mac mini via cron jobs + Claude Code CLI. Access from iPhone over Tailscale.

## How It Works

1. **5:15 AM** — Garmin data pull (sleep, HR, HRV, activities)
2. **5:20 AM** — Strava data pull (activities, splits)
3. **5:45 AM** — Claude Code generates daily briefing → push notification to iPhone
4. **Sunday 6 AM** — Claude Code generates weekly deep analysis → push notification
5. **Evening** — You run `checkin` to log how the day went
6. **Anytime** — `coach-chat` for on-demand questions with full context

Claude Code reads all your data + a rolling `athlete_context.md` memory file, so every analysis builds on previous insights.

## iPhone Access via Tailscale

The web dashboard + push notifications let you access everything from your phone:

- **Push notifications** via [ntfy](https://ntfy.sh) — free, briefings delivered to your iPhone like texts
- **Web dashboard** at `http://your-mac-mini:8080` — browse briefings, weekly analyses, check-ins
- **SSH** via Termius/Prompt — run `checkin` or `coach-chat` from your phone

All traffic stays on your private Tailscale network. No cloud services, no monthly fees.

## Setup on Mac Mini

### 1. Copy to Mac mini
```bash
cp -r coach/ ~/claude/coach/
cd ~/claude/coach
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Install Tailscale + ntfy
```bash
# Tailscale (if not already installed)
brew install tailscale

# ntfy for push notifications
brew install ntfy
# Start ntfy server (or use the free public ntfy.sh)
ntfy serve --listen-http :2586 &
```

On your iPhone:
- Install **Tailscale** app, sign in to your tailnet
- Install **ntfy** app, subscribe to your topic (e.g., `http://your-mac-mini:2586/coach`)

### 4. Configure notifications
```bash
cp config/ntfy.env.example config/ntfy.env
# Edit config/ntfy.env:
#   Self-hosted: NTFY_URL=http://localhost:2586/coach
#   Public:      NTFY_URL=https://ntfy.sh/your-secret-topic-abc123
```

### 5. Move your existing files
```bash
# Copy your existing coach.md into config/
cp /path/to/your/coach.md config/coach.md

# Adapt your Garmin/Strava scripts to write YAML output
# See scripts/pull_garmin.sh and pull_strava.sh for the expected interface
```

### 6. Convert your spreadsheet
Edit `config/training_plan.yaml` with your weekly plan and HR zones. See the example structure in the file.

### 7. Make scripts executable
```bash
chmod +x scripts/*.sh scripts/*.py
```

### 8. Seed the athlete context
Edit `memory/athlete_context.md` with your current stats, or let Claude Code populate it after the first daily briefing.

### 9. Test manually
```bash
# Test check-in
python3 scripts/checkin.py

# Test daily briefing (make sure claude CLI is installed)
bash scripts/daily_briefing.sh

# Test push notification
bash scripts/notify.sh --dry-run "Test notification"
bash scripts/notify.sh "Hello from coach"

# Test web dashboard
python3 scripts/serve.py
# Open http://localhost:8080 in browser
```

### 10. Install cron jobs
```bash
crontab -e
```
Add:
```cron
# Data pulls
15 5 * * *  ~/claude/coach/scripts/pull_garmin.sh  >> ~/claude/coach/logs/cron.log 2>&1
20 5 * * *  ~/claude/coach/scripts/pull_strava.sh  >> ~/claude/coach/logs/cron.log 2>&1

# Daily briefing + push notification
45 5 * * *  ~/claude/coach/scripts/daily_briefing.sh >> ~/claude/coach/logs/cron.log 2>&1

# Weekly deep analysis (Sunday)
0  6 * * 0  ~/claude/coach/scripts/weekly_analysis.sh >> ~/claude/coach/logs/cron.log 2>&1

# Web dashboard (keep running via launchd instead — see below)
```

### 11. Keep web dashboard running
For the web server, use a launchd plist instead of cron so it auto-restarts:

```bash
cat > ~/Library/LaunchAgents/com.coach.web.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.coach.web</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>serve.py</string>
        <string>--port</string>
        <string>8080</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/YOU/claude/coach/scripts</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOU/claude/coach/logs/web.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOU/claude/coach/logs/web.log</string>
</dict>
</plist>
EOF

# Edit the plist to replace YOU with your username, then load it:
launchctl load ~/Library/LaunchAgents/com.coach.web.plist
```

### 12. Add shell aliases
```bash
echo 'alias checkin="python3 ~/claude/coach/scripts/checkin.py"' >> ~/.zshrc
echo 'alias coach-chat="bash ~/claude/coach/scripts/coach-chat.sh"' >> ~/.zshrc
```

## Daily Usage

**Morning**: Push notification wakes you up with your briefing. Tap to read full version, or open `http://your-mac-mini:8080` for the dashboard.

**Anytime**: Ask your coach a question:
```bash
coach-chat                          # Interactive conversation
coach-chat "Should I skip today?"   # Quick one-shot answer
```

**Evening**: Run your check-in after your workout:
```bash
checkin              # Full check-in
checkin --quick      # Quick mode (effort, energy, notes)
checkin --date 2026-04-07  # Backdate
```

## File Structure

```
config/         → Philosophy, plan, race profile, ntfy config
data/           → Raw daily data (Garmin, Strava, check-ins)
output/         → Generated briefings and analyses
memory/         → Rolling athlete context + weekly snapshots
scripts/        → All executable scripts
prompts/        → Prompt templates for Claude Code
logs/           → Cron + web server logs
```

## Scripts

| Script | Purpose |
|--------|---------|
| `checkin.py` | Interactive evening check-in CLI |
| `coach-chat.sh` | On-demand coach conversation |
| `daily_briefing.sh` | Cron: morning briefing via Claude Code |
| `weekly_analysis.sh` | Cron: Sunday deep analysis |
| `pull_garmin.sh` | Cron: Garmin data pull wrapper |
| `pull_strava.sh` | Cron: Strava data pull wrapper |
| `notify.sh` | Push notification via ntfy (curl) |
| `serve.py` | Web dashboard for iPhone access |
| `send_text.py` | Legacy Twilio SMS/WhatsApp (optional) |

## Adapting Garmin/Strava Scripts

Your existing pull scripts need to output dated YAML files. Expected interface:

```bash
python3 pull_garmin.py --date 2026-04-08 --output data/garmin/2026-04-08.yaml
```

Expected YAML structure for Garmin:
```yaml
date: 2026-04-08
activities:
  - type: trail_running
    distance_mi: 7.1
    elevation_gain_ft: 1180
    avg_hr: 158
    duration_min: 62
sleep:
  total_hours: 7.5
  deep_hours: 1.8
  sleep_score: 78
resting_hr: 52
hrv_ms: 48
body_battery_morning: 72
```

Expected YAML structure for Strava:
```yaml
date: 2026-04-08
activities:
  - type: Run
    name: "Wednesday Hill Repeats"
    distance_mi: 7.1
    elevation_gain_ft: 1180
    avg_hr: 158
    suffer_score: 112
```
