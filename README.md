# MP3 Bot

Telegram bot that extracts the audio of a video as an MP3 file (Python, python-telegram-bot, FFmpeg).

## Files
- main.py      start-up
- handlers.py  bot logic (confirmation, progress, cooldown, help)
- converter.py download, FFmpeg, upload
- texts.py     every text of the bot
- config.py    settings read from .env

## Run locally
1. Install Python 3.10+ and FFmpeg (`ffmpeg -version` must work).
2. `python -m venv .venv` and activate it.
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set BOT_TOKEN.
5. `python main.py`

## Groups
In BotFather: /setprivacy -> Disable, then add the bot to the group again.

## Railway
Push the project to GitHub, create a service from the repo, add the variable BOT_TOKEN. The Dockerfile installs FFmpeg.
