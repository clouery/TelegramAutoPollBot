# Telegram Vote Bot

A Telegram bot that posts inline-button voting messages to your channel — like [CountMeInBot](https://t.me/countmeinbot). Designed for recurring attendance checks (e.g., weekly training) — automatically inserts the next Tuesday's date.

Built with [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot).

## Features

- **`/sendpoll`** — DM the bot privately → posts a voting message with inline buttons to your channel (no commands visible to channel users)
- **Live tally** — The message updates in real time with names of who voted as people tap buttons
- **`{date}` placeholder** — Auto-replaces with the next Tuesday's date (or any format you choose)
- **Non-anonymous** — Everyone can see who voted for what (like CountMeInBot)
- **Health server** — Built-in lightweight HTTP server for deployment platforms that require an open port (Render, Railway, etc.)
- **Minimal dependencies** — Only `python-telegram-bot` and `python-dotenv`

## Getting Started

### Prerequisites

- Python 3.9+
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
| `POLL_OPTIONS` | Comma-separated options (2–10), each becomes a button | `Coming, Not Coming` |
| `POLL_TIMEZONE` | IANA timezone | `Asia/Singapore` |
| `POLL_DATE_FORMAT` | strftime format for `{date}` | `%Y-%m-%d` |
| `POLL_DAY` | Day of week to auto-send (0=Sun..6=Sat) | *(manual only, no auto)* |
| `POLL_TIME` | Time to auto-send in HH:MM 24h | *(manual only, no auto)* |
| `TEMPLATE_MESSAGE` | Optional announcement message sent before the vote | *(empty)* |
| `TEMPLATE_PARSE_MODE` | Parse mode for template (`HTML` / `MarkdownV2`) | *(empty)* |
| `BOT_OWNER_IDS` | Comma-separated Telegram user IDs allowed to use `/sendpoll` (empty = anyone) | *(empty)* |

### Running

```bash
python bot.py
```

Then:
1. DM the bot on Telegram and send `/start` (first time only)
2. DM `/sendpoll` → the voting message appears in your channel

Users tap the buttons on the message to vote. The message updates live showing names.

## Bot must be channel admin

For the bot to post messages in your channel, **add it as an admin**:

1. Open your channel → Channel Info → Administrators → Add Admin
2. Search for your bot's username and add it

## Deployment (Render)

The bot includes a health-check HTTP server on `PORT` (default `8000`) — compatible with Render, Railway, and similar platforms.

On Render, set the start command to `python bot.py` and add your env vars (same as `.env`) in the Render dashboard.

## Example

A weekly training attendance vote:

```
POLL_QUESTION=Training on {date}?
POLL_OPTIONS=Coming, Not Coming
POLL_TIMEZONE=Asia/Singapore
POLL_DATE_FORMAT=%A, %B %d
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
