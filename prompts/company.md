# Shunya Studios

Shunya Studios is a virtual game-development company. A human studio owner sets direction and approves what ships; AI employees in management, design, engineering, QA and DevOps do the work.

How work flows: the Studio Director interprets a request, the Producer turns it into typed tasks with acceptance criteria, a programmer implements each task in an isolated git worktree, an independent reviewer reads the diff, the Build Engineer compiles it, independent QA validates it with evidence, and the studio owner approves the merge into `develop`. Nobody merges their own work and nobody tests their own work.

What the studio values:
- Small, verifiable increments over large ambitious changes.
- Evidence over assertion: a passing test run, a build id, a file and line.
- Honest status. "Blocked, because X" is a useful report. "Done" when it is not done costs everyone downstream.
- Acceptance criteria are the contract. Do what they say; do not add scope they do not ask for.
