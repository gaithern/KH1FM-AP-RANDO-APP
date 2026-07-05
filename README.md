# KH1FM-AP-RANDO-APP

Website and Discord bot for generating Kingdom Hearts: Final Mix Archipelago
randomizer seeds, plus the vendored Archipelago engine + KH1 world that powers
generation. Both the dev and prod sites run on PythonAnywhere (PA).

## Repository layout

```
webapp/                  Vendored Archipelago engine (mirrored from the
                          gaithernOrg/ArchipelagoKH1FM fork) + custom glue files
  ap_tools.py             } extracts the inner zip from an AP-generated
  flask_app.py            } output, exposes the Flask endpoints the
  mysql_tools.py          } bot/website call (/generate, /daily_seed,
  html_tools.py           } /register, /daily_duo_*, /draft/*), player/
  envr.py                 } daily-seed/draft-game persistence, HTML
  oauth_tools.py          } scraping helpers, Discord OAuth (website
                          } login), and env-driven config
  draft_tools.py          } KH1 item draft feature: DB access, pluggable
  draft_formats.py        } draft-format strategies (snake draft first),
  draft_item_pool.py      } the draftable item pool (from worlds/kh1's
  draft_send_tools.py     } item table), and live in-room item delivery
                          } via `!admin /send_multiple`
  schema/draft_tables.sql } draft feature's MySQL schema (apply manually -
                          } see below)

discord_bot.py           The Discord bot (commands: generate, daily_seed,
                          register, daily_duo_*)
discord_bot_settings.py  Bot config, all from os.environ

.github/workflows/
  deploy-dev.yml          Auto-deploys webapp/ to the dev PA site
  deploy-prod.yml         Manually-triggered deploy of webapp/ + the bot to prod
  sync-kh1-world.yml      Pulls engine updates from ArchipelagoKH1FM into main
```

`ap_tools.py`, `envr.py`, `flask_app.py`, `html_tools.py`, `mysql_tools.py`,
`oauth_tools.py`, `draft_tools.py`, `draft_formats.py`, `draft_item_pool.py`,
`draft_send_tools.py`, and `schema/` are the only things in `webapp/` that
aren't part of the upstream Archipelago engine — everything else is a mirror
of [gaithernOrg/ArchipelagoKH1FM](https://github.com/gaithernOrg/ArchipelagoKH1FM).
All of them are excluded from `sync-kh1-world.yml`'s rsync so the engine sync
never overwrites or deletes them.

## KH1 item draft feature

Lets a host create a draft game, seat other Discord-logged-in players, run a
snake draft over a configurable KH1 item pool (`draft_item_pool.py`,
categories sourced from `worlds/kh1/Items.py`), then upload one YAML to
generate a single seed. Each seated player gets their own room of that same
seed (same per-player-room pattern as Daily Seed —
`mysql_tools.get_players_daily_seed`), and the backend connects to each room
as admin (`draft_send_tools.py`, via `CommonClient.py`'s `CommonContext`
directly rather than shelling out to a subprocess) to deliver that player's
own drafted items via `!admin /send_multiple`. The admin password is a fresh
secret generated per game and baked into the multidata at generation time
(`ap_tools.generate(..., server_password=...)`) — never sent to the frontend.

Before this feature works on a given environment (dev/prod), run
`webapp/schema/draft_tables.sql` once against that environment's MySQL
database, and set a `DRAFT_YAMLS_ROOT` env var (parallel to the existing
`YAMLS_ROOT`) pointing at a writable directory for staged host YAMLs.

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
- The pip install step deliberately omits `-U`/`--upgrade`. Each
  `requirements.txt` is installed in a separate `pip install` invocation
  (one per file), and `-U` forces pip to bump *any* package to the latest
  version matching that file's constraint — including packages another
  file pins exactly with `==`. A loose bound like `typing-extensions>=4.7`
  in one world's requirements file upgrading the shared `typing-extensions`
  past another file's `typing_extensions==4.15.0` pin caused the same
  `ModuleUpdate` `EOFError` outage on prod. Without `-U`, pip only touches
  a package when the current file's own requirement isn't already
  satisfied, so exact pins from other files can't get clobbered.
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
