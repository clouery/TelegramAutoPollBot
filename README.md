# Telegram Auto-Poll Bot

A Telegram bot that sends configurable polls on demand. Designed for recurring polls (e.g., weekly training attendance) — automatically inserts the next Tuesday's date into the question.

Built with [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot).

## Features

- **`/sendpoll`** — Send a poll to a configured chat or channel
- **`{date}` placeholder** — Auto-replaces with the next Tuesday's date (or any format you choose)
- **Configurable** — Question text, options, anonymity, multiple answers, close timer, timezone
- **Health server** — Built-in lightweight HTTP server for deployment platforms that require an open port (Render, Railway, etc.)
- **Minimal dependencies** — Only `python-telegram-bot` and `python-dotenv`

## Getting Started

### Prerequisites

- Python 3.9+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A target chat/channel ID (use [@getidsbot](https://t.me/getidsbot))

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
| `CHAT_ID` | Target chat/channel ID | **Required** |
| `POLL_QUESTION` | Poll question (max 300 chars). Use `{date}` as placeholder | `What's your favorite programming language?` |
| `POLL_OPTIONS` | Comma-separated options (2–10) | `Python, TypeScript, Rust, Go` |
| `POLL_TIMEZONE` | IANA timezone | `Asia/Singapore` |
| `POLL_IS_ANONYMOUS` | Hide voters? (`true`/`false`) | `true` |
| `POLL_ALLOWS_MULTIPLE` | Allow multiple answers? (`true`/`false`) | `false` |
| `POLL_CLOSE_DAYS` | Days until auto-close (1–30) | `7` |
| `POLL_DATE_FORMAT` | strftime format for `{date}` | `%Y-%m-%d` |

### Running

```bash
python bot.py
```

Or use the provided script:

```bash
./run_bot.sh
```

Send `/start` to your bot in Telegram to verify it's running, then `/sendpoll` to post a poll.

## Deployment

The bot includes a health-check HTTP server on `PORT` (default `8000`) — compatible with Render, Railway, Fly.io, and similar platforms. Set the start command to:

```
python bot.py
```

## Example

A weekly training attendance poll:

```
POLL_QUESTION=Training on {date}?
POLL_OPTIONS=Coming, Not Coming
POLL_TIMEZONE=Asia/Singapore
POLL_IS_ANONYMOUS=false
POLL_CLOSE_DAYS=2
POLL_DATE_FORMAT=%A, %B %d
```

On Tuesday it sends:

> **Training on Tuesday, July 14?**
> ☐ Coming
> ☐ Not Coming

## License

MIT
