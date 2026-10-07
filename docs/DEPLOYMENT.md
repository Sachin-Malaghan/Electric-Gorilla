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
| `SHUNYA_MODEL_PROVIDER`, `ANTHROPIC_API_KEY` | `anthropic` for real agents. `scripted` runs only the two built-in requests. |
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
- With real agents, set the per-agent `cost_budget` values in `agents/` (via `tools/dev/gen_agents.py`) before the first run.

## 8. Not production-ready yet

No multi-user accounts or audit of who approved what beyond a name string; no TLS built in; PostgreSQL / Redis / Docker paths are written but untested; no metrics exporter; real-agent runs are unproven; the game build is Development configuration only.
