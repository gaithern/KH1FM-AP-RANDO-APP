# KH1FM-AP-RANDO-APP

Website backend and Discord bot for generating Kingdom Hearts Final Mix
Archipelago seeds. Dev and prod both run on PythonAnywhere (PA).

## Layout

```
app/                Our code: Flask app, DB access, draft feature, OAuth
  schema/           MySQL schema for the draft feature (apply by hand)
webapp/             Archipelago engine, mirrored from ArchipelagoKH1FM. Never edit.
discord_bot.py      The Discord bot
.github/workflows/  Sync and deploy workflows
```

`webapp/` is overwritten every 15 minutes by the sync, so all our code goes in
`app/`.

## How it runs on PA

| Repo folder | Prod             | Dev                  |
|-------------|------------------|----------------------|
| `webapp/`   | `~/mysite/`      | `~/mysite_dev/`      |
| `app/`      | `~/kh1app/`      | `~/kh1app_dev/`      |

The WSGI file puts both folders on `sys.path`, `app/` first, then imports
`flask_app`. Config comes from environment variables (see `app/envr.py` and
`discord_bot_settings.py`).

## Workflows

- **sync-kh1-world.yml**: every 15 min, mirrors ArchipelagoKH1FM into
  `webapp/` and pushes to `main`.
- **deploy-dev.yml**: runs on every push to `main` that touches `webapp/` or
  `app/`. Deploys to dev and reloads it.
- **deploy-prod.yml**: manual only. Deploys to prod, reloads it and restarts
  the bot. Run it from the Actions tab or with
  `gh workflow run deploy-prod.yml --ref main`.

Don't change these two things in the deploy's pip step:
- It installs **every** `requirements.txt`, not just the top-level one.
  Archipelago checks all of them at startup and crashes the site if any are
  unmet.
- It does **not** use `-U`. Upgrading broke exact pins from other files and
  took prod down once.

## Dev bot

The dev bot runs locally: `python discord_bot.py`. Restart it by hand after
changes. Only the prod bot restarts on deploy.
