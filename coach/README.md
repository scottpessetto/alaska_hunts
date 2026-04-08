# Mountain Running Coach Automation

Automated coaching system for Penguin Ridge training. Runs on Mac mini via cron jobs + Claude Code CLI.

## How It Works

1. **5:15 AM** — Garmin data pull (sleep, HR, HRV, activities)
2. **5:20 AM** — Strava data pull (activities, splits)
3. **5:45 AM** — Claude Code generates daily briefing → sends via WhatsApp/text
4. **Sunday 6 AM** — Claude Code generates weekly deep analysis
5. **Evening** — You run `checkin` to log how the day went

Claude Code reads all your data + a rolling `athlete_context.md` memory file, so every analysis builds on previous insights.

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

### 3. Move your existing files
```bash
# Copy your existing coach.md into config/
cp /path/to/your/coach.md config/coach.md

# Adapt your Garmin/Strava scripts to write YAML output
# See scripts/pull_garmin.sh and pull_strava.sh for the expected interface
```

### 4. Convert your spreadsheet
Edit `config/training_plan.yaml` with your weekly plan and HR zones. See the example structure in the file.

### 5. Set up Twilio (for text/WhatsApp delivery)
```bash
cp config/twilio.env.example config/twilio.env
# Edit config/twilio.env with your Twilio credentials
```

### 6. Make scripts executable
```bash
chmod +x scripts/*.sh scripts/*.py
```

### 7. Seed the athlete context
Edit `memory/athlete_context.md` with your current stats, or let Claude Code populate it after the first daily briefing.

### 8. Test manually
```bash
# Test check-in
python3 scripts/checkin.py

# Test daily briefing (make sure claude CLI is installed)
bash scripts/daily_briefing.sh

# Test text delivery
python3 scripts/send_text.py --message "Test from coach system" --dry-run
```

### 9. Install cron jobs
```bash
crontab -e
```
Add:
```cron
15 5 * * *  ~/claude/coach/scripts/pull_garmin.sh  >> ~/claude/coach/logs/cron.log 2>&1
20 5 * * *  ~/claude/coach/scripts/pull_strava.sh  >> ~/claude/coach/logs/cron.log 2>&1
45 5 * * *  ~/claude/coach/scripts/daily_briefing.sh >> ~/claude/coach/logs/cron.log 2>&1
0  6 * * 0  ~/claude/coach/scripts/weekly_analysis.sh >> ~/claude/coach/logs/cron.log 2>&1
```

### 10. Add shell alias
```bash
echo 'alias checkin="python3 ~/claude/coach/scripts/checkin.py"' >> ~/.zshrc
```

## Daily Usage

**Morning**: Read your briefing (arrives via text/WhatsApp at ~5:45 AM).

**Evening**: Run your check-in after your workout:
```bash
checkin              # Full check-in
checkin --quick      # Quick mode (effort, energy, notes)
checkin --date 2026-04-07  # Backdate
```

## File Structure

```
config/         → Philosophy, plan, race profile, Twilio creds
data/           → Raw daily data (Garmin, Strava, check-ins)
output/         → Generated briefings and analyses
memory/         → Rolling athlete context + weekly snapshots
scripts/        → All executable scripts
prompts/        → Prompt templates for Claude Code
logs/           → Cron output logs
```

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
