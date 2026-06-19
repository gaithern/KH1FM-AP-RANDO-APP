# KH1FM-AP-RANDO-APP

Website and Discord bot for generating Kingdom Hearts: Final Mix Archipelago
randomizer seeds, plus the vendored Archipelago engine + KH1 world that powers
generation. Both the dev and prod sites run on PythonAnywhere (PA).

## Repository layout

```
webapp/                  Vendored Archipelago engine (mirrored from the
                          gaithernOrg/ArchipelagoKH1FM fork) + 5 custom files
  ap_tools.py             } custom glue: extracts the inner zip from an
  flask_app.py            } AP-generated output, exposes the Flask endpoints
  mysql_tools.py          } the bot/website call (/generate, /daily_seed,
  html_tools.py           } /register, /daily_duo_*), player/daily-seed
  envr.py                 } persistence, HTML helpers, and env-driven config

discord_bot.py           The Discord bot (commands: generate, daily_seed,
                          register, daily_duo_*)
discord_bot_settings.py  Bot config, all from os.environ

.github/workflows/
  deploy-dev.yml          Auto-deploys webapp/ to the dev PA site
  deploy-prod.yml         Manually-triggered deploy of webapp/ + the bot to prod
  sync-kh1-world.yml      Pulls engine updates from ArchipelagoKH1FM into main
```

`ap_tools.py`, `envr.py`, `flask_app.py`, `html_tools.py`, and `mysql_tools.py`
are the only files in `webapp/` that aren't part of the upstream Archipelago
engine — everything else is a mirror of
[gaithernOrg/ArchipelagoKH1FM](https://github.com/gaithernOrg/ArchipelagoKH1FM).

## Branching model

There is one branch: **`main`**. It is always what's deployed to the **dev**
site. **Prod** lags behind until someone manually triggers a deploy.

```
ArchipelagoKH1FM (separate repo, main)
        |  sync-kh1-world.yml (every 15 min, mirrors the whole engine
        |  except the 5 glue files above)
        v
   this repo's main  ---push (webapp/** changed)--->  deploy-dev.yml --> dev site (auto)
        |
        +----------------workflow_dispatch (manual)--> deploy-prod.yml --> prod site
```

We used to keep separate `dev`/`main` branches mirroring two hand-synced PA
folders (`mysite`/`mysite_dev`), ~300MB each. That was collapsed into the
single-branch model above — there's now one source of truth, and "promoting
to prod" just means running the prod workflow against whatever's on `main`.

## Why `main` doesn't directly push to ArchipelagoKH1FM

`gaithernOrg/ArchipelagoKH1FM` is a public fork that occasionally sends PRs
upstream to `ArchipelagoMW/Archipelago`. The sync only ever reads from it
(checkout, no token needed since it's public) — nothing in this repo's
automation writes back to it.

## GitHub Actions workflows

### `sync-kh1-world.yml`
- Runs every 15 minutes (cron) or on demand (`workflow_dispatch`).
- Checks out `ArchipelagoKH1FM@main` and rsyncs it into `webapp/`, excluding
  the 5 glue files (so our Flask/bot integration is never overwritten) and
  `.git`/`.github`/`__pycache__`.
- If anything changed, commits and pushes straight to `main` using a
  dedicated deploy key (`REPO_PUSH_DEPLOY_KEY`) — pushes authenticated with
  the default `GITHUB_TOKEN` don't trigger other workflows, so a real deploy
  key is required for this to chain into `deploy-dev.yml`.

### `deploy-dev.yml`
- Triggers on push to `main` that touches `webapp/**`, or manually.
- rsyncs `webapp/` to `/home/<user>/mysite_dev/` on PA (deletes anything
  removed locally; excludes runtime-only paths like `logs/`, `output/`,
  `Players/`, `host.yaml`).
- Installs/updates every `requirements.txt` found under the deployed tree —
  not just the top-level one. Archipelago's `ModuleUpdate.update()` checks
  **all** of them (the top-level file plus one per `worlds/*` folder) at
  import time, and if any pin isn't satisfied it tries to interactively
  prompt for confirmation, which crashes the whole app with `EOFError` in a
  headless WSGI process. Installing only the top-level file was the cause of
  a full dev-site outage once (see commit history around the `protobuf`
  fix) — don't reintroduce that filtering.
- Reloads the dev PA web app via PA's API.

### `deploy-prod.yml`
- `workflow_dispatch` only — never runs automatically. This is the
  "promote to prod" button.
- Same rsync + dependency-install pattern, targeting `/home/<user>/mysite/`.
- Also syncs `discord_bot.py`/`discord_bot_settings.py` to the prod bot's
  home directory, reloads the prod web app, and restarts the prod bot's
  PA Always-on Task.

## Deploying to prod

1. GitHub → **Actions** → **Deploy prod site** → **Run workflow** (branch
   `main`), or: `gh workflow run deploy-prod.yml --ref main`
2. Takes a few minutes: rsync, dependency install across all `requirements.txt`
   files, web app reload, bot restart.

There's no staged approval step (a paid GitHub plan is required for required
reviewers on a private repo) — manual trigger is the only gate.

## Configuration / secrets

Nothing is hardcoded. `webapp/envr.py` and `discord_bot_settings.py` read
everything from `os.environ`; the actual values live in each PA web app's
**Environment variables** section (WSGI file) and in the bot's Always-on Task
command line (PA has no separate env var UI for tasks).

GitHub Actions secrets used by the workflows above:
- `PA_USERNAME`, `PA_API_TOKEN` — PA account + API token, for reload/restart calls
- `PA_SSH_PRIVATE_KEY` — deploys files over SSH to PA
- `PA_BOT_TASK_ID` — prod bot's Always-on Task ID, for restarting it
- `REPO_PUSH_DEPLOY_KEY` — lets `sync-kh1-world.yml`'s push trigger
  `deploy-dev.yml` (see above)

## Local dev bot

The dev Discord bot currently runs locally (not on PA) — pull `main` and run
`python discord_bot.py` after a relevant change; restart it manually to pick
up new code. Only the prod bot is restarted automatically by
`deploy-prod.yml`.
