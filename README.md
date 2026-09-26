# Telegram Vote Bot

A Telegram bot that posts inline-button voting messages to your channel — like [CountMeInBot](https://t.me/countmeinbot). Designed for recurring attendance checks (e.g., weekly training), with an automatic `{date}` placeholder that resolves to the next occurrence of a configurable weekday.

Built with [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot).

**Manual only.** There is no scheduler and no auto-send. The `/sendpoll` command is the only way to post a voting message. Render's free tier is kept alive by an external cron pinging the health endpoint (see below).

## Features

- **`/sendpoll`** — DM the bot privately → posts a voting message with inline buttons to your channel (no commands visible to channel users)
- **Live tally** — The message updates in real time with names of who voted as people tap buttons
- **`{date}` placeholder** — Auto-replaces with the next occurrence of `POLL_DAY` (default: Tuesday)
- **Non-anonymous** — Everyone can see who voted for what (like CountMeInBot)
- **Health server** — Hardened HTTP server (`GET`/`HEAD`/`OPTIONS`) for platforms that require an open port (Render, Railway, etc.)
- **Minimal dependencies** — Only `python-telegram-bot` and `python-dotenv`

## Project layout

Flat modules; `python bot.py` is the single entry point.

| Module | Responsibility |
|---|---|
| `bot.py` | Slim entry point: load dotenv, configure logging, load config, build the vote store, start the health server, wire PTB handlers, `run_polling` |
| `config.py` | Environment parsing + validation into a frozen `Config` dataclass (no import-time side effects) |
| `poll.py` | Pure domain logic: weekday math, `{date}` formatting, vote-text/keyboard building, callback-data parsing |
| `storage.py` | `VoteStore`: atomic load/save/mutate; preserves the existing on-disk JSON schema |
| `health.py` | `ThreadingHTTPServer` health endpoint (`GET`/`HEAD`/`OPTIONS`) |
| `handlers.py` | PTB handler factories (`/start`, `/sendpoll`, vote callback) with injected `Config` + `VoteStore` |

## Getting Started

### Prerequisites

- Python 3.9+ (works on 3.14 too)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A target channel ID (use [@getidsbot](https://t.me/getidsbot))
- The bot must be added as an **admin** of your channel

### Installation

```bash
git clone https://github.com/yourusername/TelegramAutoPollBot.git
cd TelegramAutoPollBot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your settings:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather | **Required** |
| `CHAT_ID` | Target channel ID (starts with `-100`) | **Required** |
| `POLL_QUESTION` | Voting question. Use `{date}` as placeholder | `What's your favorite programming language?` |
| `POLL_OPTIONS` | Comma-separated options (2–10, each ≤100 chars), each becomes a button | `Python, TypeScript, Rust, Go` |
| `POLL_TIMEZONE` | IANA timezone | `Asia/Singapore` |
| `POLL_DATE_FORMAT` | strftime format for `{date}` | `%Y-%m-%d` |
| `POLL_DAY` | Target weekday for `{date}`: `0`=Sun .. `6`=Sat | `2` (Tuesday) |
| `TEMPLATE_MESSAGE` | Optional announcement message sent before the vote | *(empty)* |
| `TEMPLATE_PARSE_MODE` | Parse mode for template (`HTML` / `MarkdownV2`) | *(empty)* |
| `BOT_OWNER_IDS` | Comma-separated Telegram user IDs allowed to use `/sendpoll` (empty = anyone) | *(empty)* |
| `LOG_LEVEL` | Logging level | `INFO` |
| `PORT` | Health server port | `10000` |
| `VOTE_STORE_FILE` | Path to the vote store JSON | `vote_store.json` |

> `POLL_TIME` no longer exists — the bot never auto-sends.

### Running

```bash
python bot.py
```

Then:

1. DM the bot on Telegram and send `/start` (first time only)
2. DM `/sendpoll` → the voting message appears in your channel

Users tap the buttons on the message to vote. The message updates live showing names.

### Tests

Tests use `tmp_path` and never touch the real `.env`, the network, or your on-disk store. `pytest` is a development-only dependency.

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

## Bot must be channel admin

For the bot to post messages in your channel, **add it as an admin**:

1. Open your channel → Channel Info → Administrators → Add Admin
2. Search for your bot's username and add it

## Health endpoint

The bot starts an embedded HTTP server on `PORT` (default `10000`).

- `GET /health` → `200` with body `OK` (`text/plain; charset=utf-8`, `Cache-Control: no-store`)
- `HEAD /health` → `200`, same headers, no body
- `OPTIONS /health` → `204` with `Allow: GET, HEAD, OPTIONS`

Every path responds the same way; the server binds synchronously at startup so a port conflict fails loudly instead of silently.

## Deployment (Render) / keep-alive

The bot runs as a Render **free Web Service**. Free web services sleep after inactivity, so an **external cron** must ping the service to keep it awake.

- Set the Render start command to `python bot.py`.
- Add your env vars (same as `.env`) in the Render dashboard. Render injects `PORT`; the app reads it (falling back to `10000`).
- Configure the keep-alive ping at [cron-job.org](https://cron-job.org):
  - **Method: `GET`** (required; `HEAD` and `OPTIONS` are also supported)
  - **URL:** `https://<your-service>.onrender.com/health`
  - **Timeout:** ≥ 60 seconds (cold starts can be slow)
  - **Interval:** every 10 minutes

## Example

A weekly training attendance vote:

```
POLL_QUESTION=Training on {date}?
POLL_OPTIONS=Coming, Not Coming
POLL_TIMEZONE=Asia/Singapore
POLL_DATE_FORMAT=%A, %B %d
POLL_DAY=2
TEMPLATE_MESSAGE=Hey everyone!\n\nTraining is this Tuesday as usual!
```

You DM `/sendpoll` → channel sees:

> 📊 **Training on Tuesday, July 14?**
>
> Tap a button below to vote!
>
> [ Coming ] [ Not Coming ]

As people tap, the message updates:

> 📊 **Training on Tuesday, July 14?**
>
> Coming (3👥):
>   Alice
>   Bob
>   Charlie
>
> Not Coming (1👥):
>   Theo
>
> 👥 4 people responded
>
> [ Coming ] [ Not Coming ]

## License

MIT
