# SHUNYA STUDIO AI
## Master Architecture & Production Build Specification
### Agentic AI Game Development Company for Unreal Engine

> **Purpose:** A build-ready architecture that another engineer can implement independently while we later build and learn the same system phase-by-phase.

---

# 1. Vision

Shunya Studio AI is a virtual game-development company in which specialized AI agents operate as employees across management, design, engineering, art, environment, animation, audio, QA, DevOps, and documentation.

The system develops a **real Unreal Engine project**, while a **2.5D virtual company** visualizes the agents' real operational state.

The 2.5D company is not a fake animation. If an agent is compiling, its employee avatar should reflect that state. If agents are collaborating, they can appear in a meeting room. If QA rejects a feature, the actual backend task returns to engineering.

## Core principles

- The agent backend, 2.5D studio, and Unreal project remain separate systems.
- The 2.5D office visualizes real backend events.
- Agents operate through typed tasks, tools, permissions, artifacts, and approval gates.
- Coding agents work in isolated Git branches/workspaces.
- QA and review are independent of implementation agents.
- High-risk operations require human approval.
- LLMs make decisions; deterministic application code enforces permissions and safety.

---

# 2. Three Major Products

```text
SHUNYA STUDIO AI
|
|-- 1. AGENT BACKEND
|      AI employees actually perform work
|
|-- 2. 2.5D STUDIO
|      Visual company + control center
|
`-- 3. UNREAL GAME PROJECT
       The actual game being developed
```

Do not tightly couple these three components.

---

# 3. Top-Level Architecture

```text
                         USER
                           |
                           v
                 +-------------------+
                 |  STUDIO INTERFACE |
                 |    2.5D Company   |
                 +---------+---------+
                           |
                     REST/WebSocket
                           |
                           v
+---------------------------------------------------------+
|                    STUDIO BACKEND                       |
|                                                         |
|  API Gateway                                            |
|       |                                                 |
|       v                                                 |
|  Studio Orchestrator                                    |
|       |                                                 |
|       |-- Task Manager                                  |
|       |-- Agent Registry                                |
|       |-- Workflow Engine                               |
|       |-- Permission Engine                             |
|       |-- Event Bus                                     |
|       `-- Human Approval System                         |
|                                                         |
|---------------------------------------------------------|
|                    AGENT RUNTIME                        |
|                                                         |
| Director -> Managers -> Specialists                     |
|                                                         |
| Model                                                   |
| Tools                                                   |
| Memory                                                  |
| RAG                                                     |
| Context                                                 |
| Guardrails                                              |
| Evaluation                                              |
|                                                         |
|---------------------------------------------------------|
|                     TOOL LAYER                          |
|                                                         |
| Files | Git | C++ | Unreal | Build | Test | Assets     |
|                                                         |
|---------------------------------------------------------|
|                KNOWLEDGE / MEMORY                       |
|                                                         |
| PostgreSQL | Vector Search | Redis | Artifact Storage  |
|                                                         |
|---------------------------------------------------------|
|                   UNREAL BRIDGE                         |
|                                                         |
| Python | CLI | UAT | Editor Plugin | Commandlets       |
+-------------------------+-------------------------------+
                          |
                          v
                   UNREAL PROJECT
```

---

# 4. Recommended Repository Structure

```text
shunya-studio/
|
|-- apps/
|   |-- studio-ui/
|   |-- studio-api/
|   |-- orchestrator/
|   `-- unreal-bridge/
|
|-- agents/
|   |-- management/
|   |-- design/
|   |-- engineering/
|   |-- art/
|   |-- environment/
|   |-- animation/
|   |-- audio/
|   |-- qa/
|   |-- devops/
|   `-- documentation/
|
|-- core/
|   |-- agent_runtime/
|   |-- orchestration/
|   |-- task_engine/
|   |-- permissions/
|   |-- memory/
|   |-- rag/
|   |-- events/
|   |-- models/
|   `-- evaluation/
|
|-- tools/
|   |-- filesystem/
|   |-- git/
|   |-- cpp/
|   |-- unreal/
|   |-- build/
|   |-- testing/
|   `-- asset_tools/
|
|-- knowledge/
|   |-- ingestion/
|   |-- embeddings/
|   |-- code_index/
|   `-- dependency_graph/
|
|-- infrastructure/
|   |-- docker/
|   |-- database/
|   |-- redis/
|   `-- monitoring/
|
|-- shared/
|   |-- schemas/
|   |-- protocols/
|   `-- utilities/
|
|-- tests/
|
`-- unreal/
    `-- ShunyaGame/
```

---

# 5. Agent Definition

Every virtual employee uses a common core definition.

```python
class AgentProfile:
    id: str
    name: str
    department: str
    role: str
    responsibilities: list[str]
    model_config: ModelConfig
    tools: list[Tool]
    permissions: PermissionSet
    short_term_memory: Memory
    long_term_memory: Memory
    knowledge_sources: list[str]
    max_iterations: int
    token_budget: int
    cost_budget: float
    supervisor_id: str | None
    escalation_policy: EscalationPolicy
    validation_policy: ValidationPolicy
```

Example:

```yaml
id: gameplay_programmer_01
name: Arjun
department: engineering
role: Senior Unreal Gameplay Programmer

responsibilities:
  - gameplay systems
  - Unreal C++
  - components
  - actors
  - abilities
  - replication

tools:
  - code_search
  - file_read
  - file_edit
  - compile
  - unreal_editor
  - git_diff
  - run_tests

permissions:
  read_code: true
  modify_code: true
  compile: true
  run_tests: true
  commit: false
  merge: false
  deploy: false

supervisor: technical_lead
```

The 2.5D avatar represents this real backend employee.

---

# 6. Agent Runtime State Machine

```text
IDLE
  |
  v
UNDERSTANDING
  |
  v
PLANNING
  |
  v
RETRIEVE CONTEXT
  |
  v
SELECT ACTION
  |
  v
CALL TOOL
  |
  v
OBSERVE
  |
  +---- SUCCESS ----> VERIFY
  |
  `---- FAILURE ----> RECOVER ----> retry/replan
                         |
                         v
                   TASK COMPLETE?
                    |          |
                   NO         YES
                    |          |
                    `----------+
                               v
                             REPORT
```

Every agent run must enforce:

- maximum iterations
- maximum execution time
- token budget
- monetary budget
- tool-call limit
- repeated-error detection
- cancellation
- human escalation

Never create an unbounded `while True -> ask LLM` production loop.

---

# 7. Company Hierarchy

```text
YOU
|
`-- STUDIO DIRECTOR
    |
    `-- PRODUCER
        |
        |-- GAME DESIGN
        |   |-- Lead Designer
        |   |-- Gameplay Designer
        |   |-- Combat Designer
        |   |-- Level Designer
        |   |-- Economy Designer
        |   `-- Narrative Designer
        |
        |-- ENGINEERING
        |   |-- Technical Director
        |   |-- Software Architect
        |   |-- Gameplay Programmer
        |   |-- Unreal Programmer
        |   |-- AI Programmer
        |   |-- Graphics Programmer
        |   |-- UI Programmer
        |   |-- Networking Programmer
        |   `-- Tools Programmer
        |
        |-- ART
        |   |-- Art Director
        |   |-- Concept Agent
        |   |-- Character Agent
        |   |-- Prop Agent
        |   |-- Material Agent
        |   `-- VFX Agent
        |
        |-- ENVIRONMENT
        |   |-- Environment Director
        |   |-- World Builder
        |   |-- Landscape Agent
        |   |-- Foliage Agent
        |   |-- Lighting Agent
        |   `-- Optimization Agent
        |
        |-- ANIMATION
        |   |-- Animation Lead
        |   |-- Rigging Agent
        |   |-- Gameplay Animation Agent
        |   `-- Cinematic Agent
        |
        |-- AUDIO
        |   |-- Audio Director
        |   |-- SFX Agent
        |   `-- Music Agent
        |
        |-- QA
        |   |-- QA Lead
        |   |-- Functional QA
        |   |-- Gameplay QA
        |   |-- Regression QA
        |   |-- Performance QA
        |   `-- Crash Investigator
        |
        |-- DEVOPS
        |   |-- Build Engineer
        |   |-- CI Agent
        |   `-- Release Agent
        |
        `-- DOCUMENTATION
            |-- Technical Writer
            `-- Knowledge Curator
```

These are agent definitions. They do not all need to be permanently running processes.

---

# 8. Feature Workflow

Example user request:

> Create an enemy camp system.

```text
USER
 |
 v
STUDIO DIRECTOR
Interpret game objective
 |
 v
PRODUCER
Create feature / epic
 |
 v
DESIGN LEAD
Create EnemyCampSpecification
 |
 v
TECHNICAL DIRECTOR
Create TechnicalDesign
 |
 v
ENGINEERING MANAGER
Create task graph
 |
 +-------------------+
 v                   v
AI Programmer     Gameplay Programmer
 |                   |
 +---------+---------+
           v
         REVIEW
           |
           v
         BUILD
           |
           v
           QA
           |
           v
       ACCEPTANCE
           |
           v
     HUMAN APPROVAL
```

---

# 9. Task System

Tasks are the heart of the company.

```json
{
  "task_id": "GAME-142",
  "type": "IMPLEMENTATION",
  "title": "Implement health component",
  "owner": "gameplay_programmer_01",
  "created_by": "engineering_manager",
  "priority": "HIGH",
  "status": "IN_PROGRESS",
  "dependencies": ["GAME-140"],
  "acceptance_criteria": [
    "Health defaults to 100",
    "Damage cannot reduce health below 0",
    "Death event fires once",
    "Component works in multiplayer"
  ]
}
```

## Task State Machine

```text
BACKLOG
  -> PLANNED
  -> ASSIGNED
  -> IN_PROGRESS
  -> REVIEW
  -> BUILD
  -> QA
  -> ACCEPTED
  -> DONE

REVIEW -> CHANGES_REQUESTED -> IN_PROGRESS
QA -> FAILED -> BUG_CREATED -> ENGINEERING
```

---

# 10. Structured Agent Communication

Agents should not rely only on free-form chat.

```json
{
  "type": "TASK_HANDOFF",
  "sender": "qa_agent_01",
  "receiver": "gameplay_programmer_01",
  "task_id": "BUG-92",
  "summary": "Player can reload while dead.",
  "evidence": {
    "test": "Combat.Reload.DeadPlayer",
    "expected": false,
    "actual": true
  },
  "severity": "HIGH"
}
```

Structured payloads are authoritative. Human-readable messages are presentation.

---

# 11. Event-Driven Architecture

Every meaningful state change produces an event.

```json
{
  "event": "AGENT_STATUS_CHANGED",
  "agent_id": "gameplay_programmer_01",
  "from": "PLANNING",
  "to": "CODING",
  "task": "GAME-142",
  "timestamp": "..."
}
```

Core events:

```text
AGENT_CREATED
AGENT_STARTED
AGENT_STATUS_CHANGED
AGENT_TOOL_CALLED
AGENT_WAITING
AGENT_FAILED
AGENT_COMPLETED

TASK_CREATED
TASK_ASSIGNED
TASK_STARTED
TASK_COMPLETED
TASK_FAILED

BUILD_STARTED
BUILD_FAILED
BUILD_PASSED

TEST_STARTED
TEST_FAILED
TEST_PASSED

BUG_CREATED

MEETING_STARTED
MEETING_ENDED

APPROVAL_REQUIRED
APPROVAL_GRANTED
```

Initial implementation can use Redis Streams/PubSub and WebSockets. Do not introduce Kafka until scale justifies it.

---

# 12. 2.5D Virtual Company

The UI is a projection of backend state.

```text
BACKEND STATE / EVENTS
        |
        v
2.5D VISUALIZATION
```

The frontend must not fake agent activity.

## Suggested Office

```text
                    EXECUTIVE FLOOR

              +---------------------+
              | Director / Producer |
              +---------------------+

DESIGN WING                         ENGINEERING WING

+---------------+                  +------------------+
| Game Design   |                  | Gameplay         |
| Narrative     |                  | Engine           |
| Level Design  |                  | Graphics         |
+---------------+                  | AI               |
                                   +------------------+

ART WING                            QA LAB

+---------------+                  +------------------+
| Character     |                  | Functional QA    |
| Environment   |                  | Performance      |
| Animation     |                  | Regression       |
| VFX           |                  +------------------+
+---------------+

                 MEETING ROOMS

                 BUILD / SERVER ROOM
```

## Agent State -> Animation

| Agent State | Visual State |
|---|---|
| IDLE | Sitting / coffee |
| PLANNING | Whiteboard |
| READING | Looking at monitor/docs |
| CODING | Typing |
| SEARCHING | Reviewing documents |
| MEETING | Walks to meeting room |
| COMPILING | Build/wait animation |
| TESTING | QA laboratory |
| DEBUGGING | Debug workstation |
| BLOCKED | Warning/question indicator |
| WAITING_APPROVAL | Approval notification |
| FAILED | Error indicator |
| SUCCESS | Completion indicator |
| OFFLINE | Empty desk |

Do not expose private model chain-of-thought. Show operational traces instead.

Example:

```text
14:42 Read InventoryComponent.h
14:43 Searched inventory references
14:44 Created implementation plan
14:46 Modified InventoryComponent.cpp
14:47 Build started
14:48 Build failed
14:48 Parsed compiler error
14:49 Applying correction
```

---

# 13. Employee Detail Panel

Clicking an employee should show:

```text
ARJUN
Senior Gameplay Programmer

Status: CODING
Task: GAME-142 - Implement Inventory Component
Elapsed: 00:07:31

Model: configured model
Tokens: 18,240
Cost: $...
Files inspected: 12
Files modified: 3
Tool calls: 27

Current Action:
Running compilation

[TASK]
[FILES]
[DIFF]
[ACTIVITY]
[LOGS]
[MEMORY]
[TOOLS]
[PERMISSIONS]

[PAUSE]
[CANCEL]
[REQUEST REPORT]
```

---

# 14. Virtual Meetings

Meetings should represent real multi-agent collaboration.

```text
CollaborationSession
- participants
- objective
- shared_context
- decisions
- action_items
```

When `MEETING_STARTED` occurs, the corresponding avatars walk into a conference room.

The actual collaboration happens in the backend.

When `MEETING_ENDED` occurs, agents return to their work locations.

---

# 15. Model Provider Abstraction

Do not scatter vendor-specific API calls throughout the system.

```python
class IModelProvider:
    async def generate(...):
        pass

    async def structured_generate(...):
        pass

    async def stream(...):
        pass
```

Implementations may include:

```text
OpenAIProvider
LocalModelProvider
OtherProvider
```

Agents depend on the interface rather than the vendor.

---

# 16. Tool Architecture

```python
class Tool:
    name: str
    description: str
    input_schema: dict
    required_permissions: list[str]

    async def execute(self, context, arguments):
        ...
```

Tool registry:

```text
ToolRegistry
|
|-- FileTools
|-- CodeTools
|-- GitTools
|-- UnrealTools
|-- BuildTools
|-- TestTools
|-- SearchTools
|-- AssetTools
`-- ProjectTools
```

## Important Tools

### Files

```text
read_file
search_files
create_file
patch_file
```

### C++

```text
find_symbol
find_references
parse_ast
inspect_dependencies
analyze_call_graph
```

### Git

```text
git_status
git_diff
create_branch
create_worktree
commit
rollback
```

### Unreal

```text
get_editor_state
get_current_level
find_actor
inspect_actor
spawn_actor
set_property
inspect_asset
inspect_blueprint
load_level
save_level
start_pie
stop_pie
capture_screenshot
```

### Build

```text
compile_project
build_target
cook_project
package_project
parse_build_errors
```

### Testing

```text
run_unit_tests
run_automation_tests
run_gameplay_test
run_gauntlet_test
run_performance_test
```

Normal agents should not receive unrestricted shell access.

---

# 17. Unreal Bridge

Create a dedicated service/module:

```text
unreal-bridge
```

Architecture:

```text
Agent
  |
  v
Tool
  |
  v
Unreal Bridge
  |
  +-- Unreal Python
  +-- Editor Plugin
  +-- C++
  +-- Commandlets
  +-- Unreal Automation Tool
  +-- Automation Framework
  `-- Gauntlet
  |
  v
Unreal Engine
```

## Unreal Plugin

Create:

```text
Plugins/
`-- ShunyaAgentBridge/
```

Responsibilities:

- editor state
- world state
- actor information
- asset metadata
- Blueprint metadata
- level information
- gameplay telemetry
- safe commands
- screenshots
- automated test execution
- performance metrics

Do not expose arbitrary Unreal memory manipulation.

---

# 18. Separate Editor and Runtime APIs

## Editor

```text
Create assets
Modify levels
Change Blueprints
Import assets
Build lighting
Compile
Save project
```

## Runtime

```text
Spawn player
Move player
Shoot weapon
Read health
Read FPS
Trigger interaction
Inspect logs
Capture telemetry
```

They must have separate permissions.

---

# 19. Git Isolation

```text
main
 |
develop
 |
 |-- agent/GAME-142
 |-- agent/GAME-143
 `-- agent/BUG-92
```

Agents work inside isolated branches/worktrees or sandboxes.

Never allow a coding agent to directly modify `main`.

---

# 20. Production Coding Workflow

```text
TASK
 |
 v
Create isolated workspace
 |
 v
Retrieve relevant architecture
 |
 v
Search code
 |
 v
Impact analysis
 |
 v
Generate implementation plan
 |
 v
Review plan when necessary
 |
 v
Modify files
 |
 v
Format / static analysis
 |
 v
Compile
 |
 +-- FAILED --> diagnose --> modify --> compile
 |
 v
Unit tests
 |
 v
Unreal tests
 |
 v
Diff review
 |
 v
Independent QA
 |
 v
Human approval
 |
 v
Merge
```

---

# 21. Memory Architecture

Do not treat one vector database as all memory.

```text
MEMORY
|
|-- Working Memory
|     current task
|
|-- Conversation Memory
|     current interaction
|
|-- Project Memory
|     architecture
|     GDD
|     standards
|     decisions
|
|-- Semantic Memory
|     embeddings
|
|-- Episodic Memory
|     previous task history
|
|-- Operational Memory
|     builds
|     tests
|     failures
|
`-- Structured Memory
      PostgreSQL
```

---

# 22. Knowledge Retrieval

```text
                     QUERY
                       |
          +------------+-------------+
          |            |             |
          v            v             v
      Semantic       Symbol        Graph
       Search        Search        Search
          |            |             |
          +------------+-------------+
                       |
                       v
                    RERANK
                       |
                       v
             MINIMAL RELEVANT CONTEXT
                       |
                       v
                     AGENT
```

For a large C++ project, semantic search alone is insufficient.

---

# 23. C++ / Unreal Knowledge Graph

Nodes:

```text
Class
Function
Method
Variable
File
Module
Unreal Actor
Component
Blueprint
Asset
Level
```

Edges:

```text
CALLS
INHERITS
OWNS
READS
WRITES
INCLUDES
REFERENCES
SPAWNS
DEPENDS_ON
IMPLEMENTS
```

Example:

```text
APlayerCharacter
      |
      +-- OWNS --> UHealthComponent
      |
      `-- CALLS --> TakeDamage()
                       |
                       `-- WRITES --> Health
```

Eventually combine:

```text
Semantic RAG
+
Static dependency graph
+
Call graph
+
Git history
+
Runtime traces
```

for impact analysis.

---

# 24. Database Design

Use PostgreSQL as the source of truth.

Core tables/entities:

```text
users
projects
departments
agents
agent_capabilities
agent_permissions

tasks
task_dependencies
task_assignments
task_runs
agent_runs

tool_calls
events
messages
artifacts

builds
tests
bugs
approvals

documents
knowledge_chunks
memories
cost_records
```

Use vector search for semantic retrieval, not as the primary database.

---

# 25. Redis

Use Redis for transient coordination:

```text
task queues
locks
agent presence
temporary state
rate limits
caching
event fan-out
```

Do not store authoritative long-term project knowledge only in Redis.

---

# 26. Backend API

Conceptual endpoints:

```text
/projects

/agents
/agents/{id}
/agents/{id}/pause

/tasks
/tasks/{id}
/tasks/{id}/cancel

/runs
/runs/{id}

/builds
/tests
/bugs

/approvals

/events

/unreal/status
/unreal/command

/knowledge/search

/studio/state

/ws/studio
```

---

# 27. Agent Permissions

Use capability-based authorization.

## Game Designer

```text
read_docs       YES
write_docs      YES
read_code       YES
write_code      NO
unreal_read     YES
unreal_modify   NO
git_commit      NO
merge           NO
deploy          NO
```

## Gameplay Programmer

```text
read_code       YES
write_code      YES
compile         YES
tests           YES
unreal_editor   YES
commit          CONDITIONAL
merge           NO
deploy          NO
```

## Release Agent

```text
package         YES
deploy_dev      YES
deploy_prod     HUMAN APPROVAL
```

---

# 28. Human Approval Gates

Create explicit approval objects containing:

```text
Approval ID
Task
Agent
Requested action
Risk level
Diff / artifact
Evidence
Reason
```

Require approval for operations such as:

- merge to protected branches
- deleting important assets
- project configuration changes
- dependency changes
- large refactors
- production packaging/release
- production deployment
- unusually expensive operations

---

# 29. Sandboxing

Preferred model:

```text
Agent
  |
  v
Sandbox / Isolated Workspace
  |
  v
Working Copy
  |
  v
Controlled Tools
```

Avoid:

```text
Agent
  |
  v
Unrestricted access to developer machine
```

---

# 30. Guardrails

```text
INPUT
  |
  v
Request validation
  |
  v
Authority check
  |
  v
Tool permission check
  |
  v
Argument/path validation
  |
  v
Sandboxed execution
  |
  v
Output schema validation
  |
  v
Human approval if necessary
```

The LLM is not the authorization layer.

---

# 31. Observability

Every operation should carry:

```text
trace_id
run_id
task_id
agent_id
tool_id
timestamp
latency
tokens
cost
status
error
```

End-to-end trace example:

```text
User Request
     |
     v
TRACE-123
     |
     |-- Studio Director
     |-- Producer
     |-- Architect
     |-- Developer
     |     |-- search
     |     |-- edit
     |     `-- compile
     |
     `-- QA
```

---

# 32. Cost Control

Every task should have budgets.

```text
GAME-142

Maximum model cost: configured budget
Maximum LLM calls: 50
Maximum runtime: 30 minutes
Maximum retries: 5
```

Supervisor agents can stop or escalate runaway workers.

---

# 33. Model Routing

Do not automatically use the most expensive model for every task.

```text
Task Classification
       |
       |-- trivial --> fast/cheap model
       |
       |-- normal --> standard model
       |
       `-- difficult --> stronger reasoning model
```

Examples:

```text
Rename variable
-> inexpensive model

Generate documentation
-> standard model

Architect networking system
-> stronger reasoning

Investigate difficult crash
-> stronger reasoning
```

---

# 34. Prompt Architecture

Do not create one giant prompt.

Compose prompts:

```text
BASE AGENT POLICY
+
COMPANY POLICY
+
DEPARTMENT POLICY
+
ROLE POLICY
+
PROJECT CONTEXT
+
TASK
+
RETRIEVED KNOWLEDGE
```

Suggested structure:

```text
prompts/
|-- base.md
|-- departments/
|   |-- engineering.md
|   `-- qa.md
|-- roles/
|   |-- gameplay_programmer.md
|   `-- technical_director.md
`-- projects/
    `-- shunya_game.md
```

---

# 35. Context Engineering

Gameplay programmer context should contain:

```text
Task
Acceptance criteria
Relevant source files
Relevant architecture
Coding standards
Dependency graph
Recent related changes
```

Avoid sending:

```text
Entire repository
Entire GDD
All previous conversations
Complete company history
```

Retrieve the smallest useful context.

---

# 36. Artifact System

Agents produce versioned artifacts.

Examples:

```text
GameDesignDocument
TechnicalDesign
ImplementationPlan
CodePatch
TestPlan
TestReport
BugReport
PerformanceReport
BuildArtifact
GeneratedAsset
ArchitectureDecision
```

Every artifact stores:

```text
ID
type
creator
task
version
timestamp
status
storage_location
```

---

# 37. Architecture Decision Records

Example:

```text
ADR-014

Decision:
Use Unreal Gameplay Ability System

Reason:
...

Alternatives:
- Custom ability framework
- Component-based abilities

Trade-offs:
...

Affected systems:
- Combat
- Networking
- UI
- Save system
```

Agents should retrieve relevant ADRs before architectural changes.

---

# 38. QA Architecture

Never allow this to be the complete QA process:

```text
Developer -> writes feature -> says it works
```

Use:

```text
Developer
   |
   v
Reviewer
   |
   v
Build
   |
   v
QA Agent
   |
   v
Gameplay Tests
   |
   v
Regression
   |
   v
Performance
   |
   v
Acceptance
```

---

# 39. QA Evidence

Example:

```json
{
  "test": "Player.Health.LavaDamage",
  "result": "PASS",
  "expected_health": 80,
  "actual_health": 80,
  "logs": "...",
  "screenshot": "...",
  "build": "B182",
  "commit": "..."
}
```

Agents should provide evidence rather than only claiming success.

---

# 40. Art Pipeline

```text
Art Director
   |
   v
Art Specification
   |
   v
Concept Generation
   |
   v
Review
   |
   v
Asset Generation
   |
   v
Asset Processing
   |
   v
Content/AI_Staging
   |
   v
Unreal Import
   |
   v
Material Setup
   |
   v
Visual QA
   |
   v
Performance QA
   |
   v
Promote to production content
```

Do not allow generated assets to go directly into production content without review.

---

# 41. Environment Pipeline

```text
Environment Brief
   |
   v
World Layout
   |
   v
Blockout
   |
   v
Landscape
   |
   v
Architecture
   |
   v
Props
   |
   v
Materials
   |
   v
Foliage
   |
   v
Lighting
   |
   v
Navigation
   |
   v
Gameplay Validation
   |
   v
Performance
   |
   v
Visual QA
```

---

# 42. 2.5D Frontend Technology

Two reasonable clients can coexist.

## Premium Client

```text
Unreal Engine
+ 2.5D/isometric environment
+ UMG
+ character animation
+ WebSocket backend connection
```

## Optional Web Dashboard

```text
React
+ PixiJS or Phaser
+ WebSocket
```

Backend remains independent:

```text
                STUDIO BACKEND
                      ^
                      |
              REST / WebSocket
                      |
          +-----------+-----------+
          |                       |
          v                       v
   Unreal 2.5D Client        Web Dashboard
```

---

# 43. 2.5D Employee Representation

Conceptual Unreal class:

```text
AStudioEmployee

AgentID
Department
CurrentTask
Status
Destination
AnimationState
```

Backend event:

```text
agent_07.status = MEETING
agent_07.room = conference_room_1
```

Frontend:

```text
Find employee
-> pathfind
-> walk to conference room
-> play meeting animation
```

Do not couple animation timing to LLM latency.

---

# 44. Recommended V1 Technology Stack

| Area | V1 Choice |
|---|---|
| Backend | Python 3.12+ |
| API | FastAPI |
| Schemas | Pydantic |
| Agent orchestration | Agent SDK behind custom interfaces |
| Database | PostgreSQL |
| Vector retrieval | pgvector initially |
| Cache / queue | Redis |
| Source control | Git |
| Containers | Docker / Docker Compose |
| Unreal | UE5 + C++ + Blueprint + Python + Editor Plugin |
| 2.5D client | Unreal Engine |
| Communication | REST + WebSocket |
| Python testing | pytest |
| Unreal testing | Automation Framework + Gauntlet |
| CI/CD | GitHub Actions initially |

---

# 45. What NOT to Build Initially

Do not start with:

```text
Kubernetes
Kafka
50 microservices
50 permanent agents
multiple vector databases
custom model training
fine-tuning
distributed agent clusters
```

Start as a modular monolith and split only when real scaling requirements appear.

---

# 46. V1 Deployment

```text
DEVELOPER PC

Docker Compose
|-- studio-api
|-- orchestrator
|-- worker
|-- postgres
`-- redis

Windows Host
|-- Unreal Editor
|-- Unreal Bridge
`-- 2.5D Studio Client
```

Do not containerize Unreal Editor initially.

---

# 47. Implementation Order

1. Create monorepo and Python backend.
2. Create PostgreSQL and Redis infrastructure.
3. Implement Agent, Task, Run, Tool, Artifact, and Event models.
4. Implement model-provider abstraction.
5. Implement one bounded single-agent loop.
6. Implement tool registry.
7. Implement safe filesystem tools.
8. Implement Git tools and isolated task workspaces.
9. Implement task state machine.
10. Implement Studio Director/Producer basics plus one Programmer.
11. Add structured manager-to-worker delegation.
12. Add WebSocket event stream.
13. Build crude 2.5D client with two employees.
14. Bind real backend states to avatars.
15. Implement Unreal Bridge.
16. Implement ShunyaAgentBridge Unreal editor plugin.
17. Add compile/build tools.
18. Create Unreal Programmer agent.
19. Create independent Reviewer.
20. Create QA agent.
21. Add Unreal automated testing.
22. Add PostgreSQL project memory.
23. Add document/code RAG.
24. Add C++ symbol index.
25. Add dependency/call graph.
26. Add Producer task decomposition.
27. Add Design department.
28. Add Environment department.
29. Add Art pipeline.
30. Add Animation and Audio.
31. Add performance testing.
32. Add approval system.
33. Add budget/cost system.
34. Add permissions and guardrails.
35. Add tracing/monitoring.
36. Add CI/CD.
37. Add failure recovery/escalation.
38. Add persistent company state and restart recovery.
39. Polish 2.5D company simulation.
40. Production hardening and security review.

---

# 48. First Meaningful Milestone

Do not try to implement every department first.

Target:

> **Create a simple Unreal health component.**

```text
User
 |
 v
Producer creates task
 |
 v
Programmer receives task
 |
 v
Inspect Unreal project
 |
 v
Create isolated Git workspace
 |
 v
Write C++
 |
 v
Compile Unreal project
 |
 +-- compile error --> parse --> diagnose --> fix
 |
 v
Compilation succeeds
 |
 v
Automated tests
 |
 v
Independent reviewer
 |
 v
Independent QA
 |
 v
Evidence/report
 |
 v
Human approval
```

The 2.5D studio simultaneously shows:

```text
Producer -> assigning ticket
Programmer -> coding
Build Agent -> building
QA -> testing
Result -> complete / rejected
```

If this pipeline works reliably, the foundation is ready to scale.

---

# 49. V1 Acceptance Criteria

Before adding many departments, require all of the following:

- [ ] User can create a feature request.
- [ ] Producer converts it into typed tasks.
- [ ] Tasks contain acceptance criteria.
- [ ] Programmer can inspect Unreal C++.
- [ ] Programmer edits only inside an isolated Git workspace.
- [ ] Unreal project can be compiled through a controlled tool.
- [ ] Compilation failures are captured and parsed.
- [ ] Agent can attempt bounded corrections.
- [ ] Automated tests can execute.
- [ ] Tests produce evidence.
- [ ] Independent reviewer can review the diff.
- [ ] QA independently validates the feature.
- [ ] Human can approve/reject final changes.
- [ ] Every operation is logged.
- [ ] Agent state appears in the 2.5D UI.
- [ ] User can pause/cancel tasks.
- [ ] Failed agents can recover or escalate.
- [ ] Task/company state survives application restart.

---

# 50. Stable Interfaces

Define interfaces before concrete implementations so separately built versions can converge.

```text
IAgent
ITool
IModelProvider
IMemoryProvider
IKnowledgeRetriever
ITaskRepository
IEventBus
IUnrealBridge
ISandbox
IArtifactStore
IApprovalService
```

For example, one implementation may use:

```text
RedisEventBus
```

while a development/test version uses:

```text
InMemoryEventBus
```

The rest of the architecture should remain unchanged.

---

# 51. North-Star Experience

The final product should feel like opening a game-development company, not opening a chatbot.

```text
+----------------------------------------------------------+
| SHUNYA STUDIOS                         Sprint 18 | 81%   |
+----------------------------------------------------------+
|                                                          |
|  DESIGN              ENGINEERING            QA LAB       |
|                                                          |
|   Designer             Dev  Dev              QA          |
|   Designer             Dev  Dev              QA          |
|                                                          |
|                    BUILD: PASS                           |
|                                                          |
|          +-----------------------------+                 |
|          |       MEETING ROOM          |                 |
|          | Producer Architect Designer |                 |
|          +-----------------------------+                 |
|                                                          |
| ART                 SERVER ROOM           AUDIO          |
|                                                          |
+----------------------------------------------------------+

PROJECT: SHUNYA

Epic: Enemy Combat V2
Progress: 78%

Agents: 14
Working: 8
Meeting: 3
Testing: 2
Blocked: 1

Build: PASS
Tests: 384 / 387
Open Bugs: 12
Critical: 0
```

The user enters:

> Add stealth takedowns to the player.

The real company workflow becomes:

```text
Studio Director
 -> Producer
 -> Game Design
 -> Technical Design
 -> Task Graph
 -> Engineering / Animation / Audio / VFX
 -> Build
 -> Review
 -> QA
 -> Performance
 -> Acceptance
 -> Human Approval
 -> Merge
```

The corresponding employees visibly work in their departments while those backend operations occur.

---

# 52. Final Engineering Rule

> **Build one reliable employee pipeline before building an entire AI company.**

The first production-quality vertical slice should be:

```text
Producer
   -> Unreal Programmer
   -> Build
   -> Reviewer
   -> QA
   -> Human Approval
```

Once that pipeline can repeatedly deliver a small Unreal feature with evidence, isolation, recovery, permissions, and traceability, expand the company department by department.

---

# 53. Learning Track Alignment

When the project is later taught phase-by-phase, every major concept should include:

1. What it is.
2. Why it exists.
3. How it works internally.
4. Implementation from scratch.
5. How it applies to Shunya Studio AI.
6. Alternatives.
7. Trade-offs.
8. Production problems and failure modes.
9. Debugging approaches.
10. System-design questions.
11. Interview questions from beginner to senior level.
12. Practical implementation exercises.

This keeps the production project and interview-preparation track aligned.

---

**Document:** Shunya Studio AI — Master Architecture & Production Build Specification  
**Version:** Initial Master Design / V1 Blueprint
