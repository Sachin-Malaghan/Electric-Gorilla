# Deploying and operating the studio

The studio is one Python process plus the Unreal toolchain on the same Windows machine. This page is the runbook.

## 1. Install

```powershell
git clone https://github.com/Sachin-Malaghan/Electric-Gorilla.git studio
cd studio
.\scripts\install.ps1          # creates .venv, installs the package, copies .env.example to .env
.\.venv\Scripts\shunya doctor  # checks Python, Git, Unreal, paths, database, access settings
```

Put the folder somewhere with a **short path** (for example `C:\studio`): Unreal's build output nests about 150 characters below each task worktree and Windows allows 260. `doctor` tells you how much headroom you have.

## 2. Configure (`.env`)

| Setting | Why |
|---|---|
| `SHUNYA_API_TOKEN` | Set it. Every API call and the live event stream then need the token. The office page asks for it once and remembers it. Required if you listen on anything other than `127.0.0.1`. |
| `ANTHROPIC_API_KEY` | The key the employees work with. Set it here, or enter it under **Model** in the office (stored in `data/secrets.json` on the server, never sent back to the browser, never logged). With a key present the studio uses real Claude agents automatically. |
| `SHUNYA_MAX_SPEND_USD` | Hard cap on total model spend (default 25). When it is reached no further model call is made and work escalates to you; raise it under **Model** or here. 0 removes the cap. |
| `SHUNYA_MODEL_PROVIDER` | Normally leave unset. `scripted` forces the free scripted employees even when a key exists; `anthropic` requires a key. |
| `SHUNYA_AUTO_APPROVE_MAX_RISK` | Leave empty to approve every merge yourself, or `LOW` to let policy approve low-risk ones. Packaged builds always come to you. |
| `SHUNYA_MAX_ACTIVE_FEATURES` | How many feature requests may be in flight (default 3). More are refused with HTTP 429. |
| `SHUNYA_WORKSPACE_DIR`, `SHUNYA_DATA_DIR` | Where the game repository / worktrees / builds and the database / artifacts / logs live. |
| `DATABASE_URL`, `REDIS_URL` | PostgreSQL and Redis instead of SQLite and the in-process bus (see `infrastructure/docker`). Not exercised yet. |
| `SHUNYA_BRIDGE_TOKEN` | Must match `Token` in the game's `Config/DefaultEngine.ini` if you use the live-editor bridge. Change both from the default. |

## 3. Run

```powershell
.\.venv\Scripts\shunya serve
```

The server refuses to start on a non-loopback address without a token. To keep it running across logins, register it as a scheduled task or a service that runs that command in the studio folder.

- Office: `http://127.0.0.1:8400`
- Liveness: `GET /health` (no token; returns 503 if the database is unreachable)
- Operations: `GET /system` (token; versions, paths, event sequence, child processes, task counts, limits)
- Logs: `data/logs/studio.log`, rotated at 5 MB, five kept. One line per API request (`shunya.access`), warnings for refused tokens.

### Hosting it on a server

The studio drives Unreal Engine on the machine it runs on, so the server decides what it can do:

| Server | What works |
|---|---|
| **Windows with Unreal Engine 5.4+, Visual Studio C++ tools and a GPU** (a cloud GPU instance or a spare PC) | Everything: compiling, automation tests, asset creation, playtests, packaged builds. |
| Windows without a GPU | Compiling, automation tests and asset creation. Playtests and packaged-build smoke runs need a GPU and a logged-in desktop session. |
| Linux, or the Docker image | The office, planning, design documents and reviews. Every Unreal step is reported as SKIPPED - never as passed - so nothing can be verified or merged as low risk. |

Steps on a Windows server:

1. Install Unreal Engine (Epic Games Launcher, needs your Epic account) and Visual Studio 2022 with *Game development with C++*.
2. `scripts\install.ps1`, then edit `.env`: set `SHUNYA_API_TOKEN` (long and random), `ANTHROPIC_API_KEY`, `SHUNYA_MAX_SPEND_USD`. Leave `SHUNYA_HOST=127.0.0.1`.
3. `shunya doctor` until there are no failures.
4. `scripts\install-service.ps1` (elevated) so the studio starts at logon and restarts if it stops. Keep that user logged in (auto-logon) if you want playtests.
5. Put HTTPS in front with `infrastructure/Caddyfile` (replace the host name; open ports 80 and 443 only). Without HTTPS the access token and the API key you type into the office travel in clear text.
6. Open `https://<your host>`, enter the access token, and check **Model** shows the key and the cap.

Costs to expect: a GPU Windows instance is billed by the hour whether or not agents are working, and every agent step is billed by Anthropic. Start with the small health-component request and a cap of a few dollars.

## 4. What happens on stop, crash and restart

- **Stop (Ctrl+C / service stop):** running pipelines are cancelled and every child process tree the studio started (UnrealBuildTool and its compilers, editor sessions, packaging) is terminated.
- **Crash or kill:** child processes may be left running; check Task Manager for `dotnet`, `cl`, `UnrealEditor`. Nothing is lost: all state is in the database and the game repository.
- **Restart:** runs that were in flight are marked interrupted, every unfinished feature resumes from the status stored for each task, and pending approvals are still pending.

## 5. Back up and restore

```powershell
.\.venv\Scripts\shunya backup                 # data/backups/shunya-<timestamp>.zip  (database + artifacts)
```

Safe while the studio runs. The game itself is a git repository at `workspace/ShunyaGame`: back it up by adding a remote and pushing `develop` and `main`. To restore, stop the studio, unzip `shunya.db` and `artifacts/` into the data directory, and start it again.

## 6. Shipping the game

The release role packages the game with Unreal Automation Tool (build, cook, stage, pak) into `workspace/builds/v<version>/Windows/`, starts the packaged executable with the QA bot, and records the result. That folder runs on a PC without Unreal Engine installed. The merge that records a packaged build always needs your approval, whatever the auto-approve setting. Builds are Development configuration; a Shipping configuration and installers are not set up.

## 7. Security notes

- The API has one shared token, no users or roles. Treat it like a password and put the server behind your own TLS-terminating proxy if it leaves the machine.
- Agents have no shell and no merge tool; they act through typed tools checked by code. Content agents send data to a studio-owned editor script, never code.
- Agents cannot change `Config/`, `*.Build.cs`, `*.Target.cs`, `*.uproject`; changes there are reverted before every commit.
- The Anthropic key lives in `.env` or `data/secrets.json` on the server. Anyone with file access to the server, or with the access token, can use the studio to spend on it; the spending cap bounds the damage. Rotate the key if the token leaks.
- Per-agent budgets (`cost_budget` in `agents/`, via `tools/dev/gen_agents.py`) and per-task budgets apply underneath the studio-wide cap.

## 8. Not production-ready yet

No multi-user accounts or audit of who approved what beyond a name string; no TLS built in; PostgreSQL / Redis / Docker paths are written but untested; no metrics exporter; real-agent runs are unproven; the game build is Development configuration only.
