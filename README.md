# 🚂 New Year Train — Discord Bot

A public Discord bot that automatically posts Happy New Year messages for all 38 UTC timezone stops, per-guild configurable with per-stop enable/disable toggles.

## Features

- **38 timezone stops** — UTC+14 down to UTC-12, every inhabited timezone
- **Dynamic per-year scheduling** — fire times computed automatically; no manual updates ever needed
- **Multi-guild** — each server has independent channel, on/off toggle, and stop configuration
- **Per-stop enable/disable** — disable individual stops, ranges, or all non-key stops so quiet servers don't look spammed
- **Delivery log** — each guild's sent history is tracked separately; one bot, many servers
- **5-min early pre-train** and **5-min post post-train** bookend messages
- **Stale guard** — if the bot was down at fire time, jobs >3 min late are skipped silently
- **tmux deployment** — `start.sh` manages a named tmux session

---

## Project Structure

```bash
new-year-train/
├── bot.py                  # Entry point — init DB, seed stops, load cogs
├── cogs/
│   ├── train.py            # Scheduler loop + user-facing slash commands
│   └── admin.py            # Admin/owner maintenance commands
├── utils/
│   ├── db.py               # SQLite schema + all DB helpers
│   └── stops_data.py       # Stop definitions, schedule builder, message formatters
├── data/                   # SQLite DB lives here (git-ignored)
├── start.sh                # tmux session manager
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/newyeartrain-bot.git
cd newyeartrain-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

```bash
cp .env.example .env
nano .env
# Fill in DISCORD_TOKEN
```

### 3. Bot permissions (when generating invite link)

Required permissions: `Send Messages`, `View Channel`, `Use Application Commands`  
Required intents: **Guilds** only — no privileged intents needed.

### 4. Run

**Simple (foreground):**

```bash
source .venv/bin/activate
python bot.py
```

**Via tmux (recommended for servers):**

```bash
./start.sh           # start in tmux
./start.sh stop      # kill session
./start.sh restart   # stop then start
./start.sh logs      # tail bot.log
./start.sh attach    # attach to session
```

On first run, the DB is created, all 38 stops are seeded, and schedules for the current and next year are built automatically.

---

## Per-Server Setup (server admins)

After inviting the bot, a server admin runs two commands:

```bash
/train_setup #channel       — set posting channel and enable the bot
/train_toggle enabled:False — pause without changing channel
/train_setchannel #channel  — update channel later
```

---

## Per-Stop Enable/Disable

The `stops` argument accepts a comma-separated mix of:

| Token | What it affects |
| --- | --- |
| `all` | Every stop + pre/post |
| `all_stops` | Stops 1–38 (keeps pre/post) |
| `stop_11` | A single stop |
| `stop_5-stop_15` | A range (inclusive) |
| `pre_train` | Pre-train announcement |
| `post_train` | Post-train farewell |

```bash
/train_stops action:disable stops:all_stops
/train_stops action:enable  stops:stop_11,stop_24
/train_stops action:disable stops:stop_1-stop_10,stop_30-stop_38
/train_stops action:enable  stops:all
```

Disabled stops are silently skipped by the scheduler — they won't fire for that guild. The global schedule is unaffected (other guilds still receive those stops normally).

---

## Slash Command Reference

All commands require **Manage Channels**.

| Command | Description |
| --- | --- |
| `/train_setup #channel` | Enable bot + set channel |
| `/train_toggle enabled` | Pause/resume the whole train |
| `/train_setchannel #channel` | Change posting channel |
| `/train_stops action stops` | Enable/disable specific stops |
| `/train_status` | Show current config + progress |
| `/train_schedule` | List upcoming fire times |
| `/train_preview stop` | Preview a message (0=pre, 1–38=stop, 39=post) |
| `/train_rebuild year` | Force-rebuild global schedule |
| `/train_reset year` | Clear delivery log for this server+year (testing) |
| `/train_sendnow year job_type` | Immediately send a job to this server's channel |
| `/train_dbinfo` | Database stats |
| `/train_guilds` | List all registered servers |

---

## How Scheduling Works

Each stop fires at the exact UTC moment when that timezone's midnight hits:

```bash
fire_utc = Jan 1 00:00:00 UTC  −  utc_offset_minutes
```

| Timezone | fire_utc |
| --- | --- |
| UTC+14 (Line Islands) | Dec 31, 10:00 UTC |
| UTC+8  (Singapore)    | Dec 31, 16:00 UTC |
| UTC±0  (London)       | Jan 1,  00:00 UTC |
| UTC−12 (Baker Island) | Jan 1,  12:00 UTC |

These UTC times are identical every year — only the year changes. The bot auto-builds the next year's schedule on startup.

---

## Git + Deploy Workflow

```bash
# Update
cd ~/new-year-train
git pull
./start.sh restart

# Check logs
./start.sh logs
# or inside tmux:
./start.sh attach
```

---

## Testing

```bash
/train_reset 2026          # re-arm all jobs for your guild
/train_sendnow 2026 pre_train           # fire pre-train message now
/train_sendnow 2026 stop_11             # fire Singapore's stop now
/train_preview 11                       # preview without sending
/train_stops action:disable stops:all  # silence everything
/train_stops action:enable  stops:all  # re-enable everything
```
