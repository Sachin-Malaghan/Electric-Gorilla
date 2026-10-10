# Game Design Document: 3D Outdoor Melee Wave Combat

**Version:** 1.0  
**Author:** Maya, Lead Designer  
**Status:** Approved for Implementation  
**Document Path:** `Docs/Design/GDD_OutdoorWaveCombat.md`  

---

## 1. Overview & Core Loop

### 1.1 High Concept
A third-person 3D outdoor melee wave combat arena game built in Unreal Engine 5. The player engages in tactical, stamina-gated melee combat against incoming waves of melee enemies in an outdoor arena. Survival requires precise stamina management, spacing, dodge roll timing, and alternating between light and heavy attacks.

### 1.2 Core Game Loop
1. **Spawn / Preparation:** Player spawns in the center of the outdoor arena with full Health (100) and full Stamina (100).
2. **Wave Start:** The wave spawner initiates Wave $N$ (1 of 3) and spawns enemies at defined perimeter spawn points.
3. **Engage & Survive:** Player navigates the arena, evades incoming attacks, manages stamina consumption and regeneration, and eliminates enemies with light and heavy melee strikes.
4. **Wave Clear:** When all enemies in the current wave are defeated, a 3.0-second inter-wave rest countdown begins before the next wave spawns.
5. **Progression / Escalation:** Waves 1 through 3 ramp up enemy counts and health attributes.
6. **Resolution:**
   - **Victory:** Clearing all 3 waves transitions match state to `Victory`, presenting the victory screen with final score, statistics, and restart prompt.
   - **Defeat:** If Player Health drops to 0 or below at any point, match state transitions to `GameOver`, displaying the game over screen with score and restart prompt.

---

## 2. Player Mechanics & Locomotion

### 2.1 Locomotion Attributes
The player character is controlled via standard third-person inputs (WASD movement, mouse camera orientation). Movement modes govern stamina consumption.

| Parameter | Value | Unit / Behavior |
| :--- | :--- | :--- |
| **Base Walk Speed** | `400.0` | Unreal units / second (`cm/s`). Default locomotion state. |
| **Sprint Speed** | `700.0` | Unreal units / second (`cm/s`). Activated while holding Sprint key (`Left Shift`). |
| **Sprint Stamina Cost** | `20.0` | Stamina units per second. Continuously drained while sprinting. |
| **Sprint Minimum Stamina** | `1.0` | Player drops back to Base Walk Speed (400) if Stamina reaches `0.0`. |
| **Sprint Regen Delay** | `1.0` | Seconds after releasing sprint before stamina regeneration begins. |

### 2.2 Dodge Roll / Dash
A quick evasive burst providing brief invulnerability frames (i-frames) to escape attacks.

| Parameter | Value | Unit / Behavior |
| :--- | :--- | :--- |
| **Dodge Distance** | `400.0` | Total displacement in Unreal units along movement input vector (or backward if neutral). |
| **Dodge Duration** | `0.3` | Seconds total duration for the dash/roll action. |
| **Invulnerability Window** | `0.3` | Seconds matching full dodge duration (`bIsInvulnerable = true`). Damage taken is `0`. |
| **Dodge Stamina Cost** | `25.0` | Flat stamina cost per dodge activation. |
| **Dodge Gating** | Stamina $\ge 25.0$ | Dodge cannot be triggered if current Stamina $< 25.0$. |
| **Dodge Cooldown / Lockout** | `0.3` | Cannot trigger another dodge or attack during active dodge duration. |

---

## 3. Combat Attributes & Economy

### 3.1 Health & Stamina Pool

| Attribute | Base / Max | Description & Regeneration Rules |
| :--- | :--- | :--- |
| **Max Health** | `100.0` | Player hit points. Clamped in range `[0.0, 100.0]`. No passive regeneration. |
| **Max Stamina** | `100.0` | Player stamina resource pool. Clamped in range `[0.0, 100.0]`. |
| **Stamina Regen Rate** | `15.0` | Stamina units restored per second once regeneration is active. |
| **Stamina Regen Delay** | `1.0` | Seconds elapsed after any stamina expenditure before regeneration begins. Any expenditure resets this delay timer to `1.0s`. |

### 3.2 Player Attacks

| Attribute | Light Attack | Heavy Attack | Notes |
| :--- | :--- | :--- | :--- |
| **Input Binding** | Left Mouse Button (`LMB`) / Primary Attack | Right Mouse Button (`RMB`) / Secondary Attack | Standard C++ binding |
| **Stamina Cost** | `15.0` | `35.0` | Action fails if current Stamina $<$ Stamina Cost |
| **Damage Dealt** | `25.0` | `60.0` | Flat damage applied to hit target |
| **Cooldown** | `0.0` s (chainable animation lock 0.4s) | `3.0` s | Heavy Attack enters a strict 3.0s cooldown timer |
| **Attack Range** | `150.0` units | `180.0` units | Melee sweep radius/sphere check in front of character |
| **Attack Arc** | `90.0` degrees | `120.0` degrees | Forward cone check |
| **Stamina Regen Reset** | Resets delay to `1.0s` | Resets delay to `1.0s` | Triggers combat delay |

---

## 4. Enemy & Wave Progression

### 4.1 Base Melee Enemy Attributes
Enemies are direct-chase melee units. Per studio architectural guidelines (no `AIModule` or `NavMesh`), enemies steer directly toward the player actor in `Tick`.

| Attribute | Base Value | Unit / Specification |
| :--- | :--- | :--- |
| **Enemy Base Health** | `50.0` | Hit points for standard enemy. |
| **Movement Speed** | `320.0` | Unreal units / second (`cm/s`). Steers toward player vector. |
| **Attack Range** | `120.0` | Unreal units. Enemy halts movement and strikes if distance $\le 120.0$. |
| **Attack Damage** | `15.0` | Flat damage dealt to player on hit. |
| **Attack Cadence / Cooldown** | `1.5` | Seconds cooldown between consecutive enemy attacks. |
| **Attack Windup / Strike Time** | `0.2` | Seconds delay from attack initiation to damage evaluation. |
| **Score Value** | `100` | Points awarded upon defeat (subject to wave multiplier). |

### 4.2 Wave Progression & Structure
The match comprises exactly three (3) waves. Wave completion triggers a brief transition interval before the subsequent wave spawns.

| Wave Number | Enemy Count | Health Multiplier | Enemy Health | Total Wave HP | Inter-Wave Delay | Notes |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Wave 1** | `3` | `1.00x` | `50.0` | `150.0` | `3.0s` | Introductory wave. Basic spacing practice. |
| **Wave 2** | `5` | `1.00x` | `50.0` | `250.0` | `3.0s` | Increased density. Demands crowd kiting. |
| **Wave 3** | `8` | `1.25x` | `62.5` | `500.0` | `N/A` | Final wave. Enhanced tankiness and swarm pressure. |

**Total Enemies in Match:** 16 enemies  
**Total Match Health Pool:** 900 HP  

### 4.3 Enemy Spawning Layout
- Spawn locations are arranged in a circular perimeter ring at radius `R = 1200.0` units around arena center `(X=0, Y=0, Z=0)`.
- Enemies spawn sequentially with a `0.5s` stagger to prevent physics interpenetration:
  - Wave 1: 3 spawns at angles $0^\circ, 120^\circ, 240^\circ$.
  - Wave 2: 5 spawns at angles $0^\circ, 72^\circ, 144^\circ, 216^\circ, 288^\circ$.
  - Wave 3: 8 spawns at angles $0^\circ, 45^\circ, 90^\circ, 135^\circ, 180^\circ, 225^\circ, 270^\circ, 315^\circ$.

---

## 5. Scoring System

Score reflects combat efficiency, survival, and pacing:
- **Enemy Defeat Base Score:** `100` points per enemy kill.
- **Wave Multiplier:**
  - Wave 1: `1.0x` (100 pts / enemy $\rightarrow$ 300 pts max)
  - Wave 2: `1.2x` (120 pts / enemy $\rightarrow$ 600 pts max)
  - Wave 3: `1.5x` (150 pts / enemy $\rightarrow$ 1,200 pts max)
- **Wave Completion Bonus:**
  - Wave 1 Clear: `250` points.
  - Wave 2 Clear: `500` points.
  - Wave 3 Clear: `1,000` points.
- **Flawless Wave Bonus (No damage taken during wave):** `500` bonus points per flawless wave.
- **Time Bonus (Victory Only):** If total match time is under `120.0` seconds:
  $$\text{Bonus} = \max(0, \lfloor(120.0 - \text{ElapsedSeconds}) \times 10\rfloor)$$

---

## 6. Win / Loss Conditions & Match States

### 6.1 State Machine
The match rules (encapsulated in an `FMatchRules` or `FWaveCombatRules` plain struct per ADR-002) track states via `EMatchState`:
1. `NotStarted`: Pre-match initialization.
2. `InProgress`: Active wave combat and inter-wave countdowns.
3. `Victory`: Cleared Wave 3 with Player Health $> 0$.
4. `GameOver`: Player Health reaches $\le 0$.

### 6.2 Win Condition (Victory)
- **Trigger:** Wave 3 is active, remaining enemy count reaches `0`, and Player Health $> 0$.
- **Actions:**
  - Set match state to `Victory`.
  - Finalize total score and match time.
  - Display Canvas Victory screen with summary statistics.
  - Enable Restart input (`R` key / Primary action).

### 6.3 Loss Condition (Game Over)
- **Trigger:** Player Health $\le 0$ at any moment during `InProgress`.
- **Actions:**
  - Set match state to `GameOver`.
  - Halt enemy wave spawns and enemy movement.
  - Display Canvas Game Over screen with wave reached and final score.
  - Enable Restart input (`R` key / Primary action).

### 6.4 Match Restart
- Pressing `R` in `Victory` or `GameOver` state resets the match:
  - Player Health reset to `100.0`, Stamina reset to `100.0`.
  - Player position reset to arena origin `(0, 0, 100)`.
  - Destroy existing enemy actors.
  - Reset Wave counter to `1`, Score to `0`, Match Timer to `0.0`.
  - Transition match state to `InProgress`.

---

## 7. Canvas HUD Layout Specifications

Per studio architecture constraints, UI is implemented via an `AHUD` subclass utilizing `Canvas->DrawRect` and `Canvas->DrawText`. No UMG or Slate is used.

### 7.1 Coordinate System & Formatting Standards
- Standard viewport reference: `1920 x 1080` (dynamic scaling based on `Canvas->ClipX` and `Canvas->ClipY`).
- Screen padding: `20` units margins from viewport edges.

### 7.2 In-Game Combat HUD Layout (`InProgress`)

```
+-----------------------------------------------------------------------------------+
| [HEALTH BAR: 100 / 100]                                     WAVE: 2 / 3           |
| [STAMINA BAR: 100 / 100]                                    ENEMIES: 3 REMAINING  |
|                                                             SCORE: 01450          |
|                                                             TIME: 01:24           |
|                                                                                   |
|                                                                                   |
|                                                                                   |
|                                                                                   |
|                                        +                                          |
|                                    (Crosshair)                                    |
|                                                                                   |
|                                                                                   |
|                                                                                   |
|                                                                                   |
|                                                                                   |
|                                                                                   |
| [HEAVY ATK: READY]                                                                |
+-----------------------------------------------------------------------------------+
```

#### Layout Specifications:
1. **Top-Left Status Bars (Player Vitals):**
   - **Health Bar:**
     - Position: `X = 20`, `Y = 20`. Width: `300` px, Height: `24` px.
     - Background: Dark Gray `FLinearColor(0.1f, 0.1f, 0.1f, 0.8f)`.
     - Fill: Bright Green `FLinearColor(0.1f, 0.85f, 0.15f, 1.0f)` (interpolates to Red `FLinearColor(0.9f, 0.1f, 0.1f, 1.0f)` when $< 30\%$).
     - Text Overlay: `"HP: {Current} / {Max}"` centered vertically at `X = 24`, `Y = 24`.
   - **Stamina Bar:**
     - Position: `X = 20`, `Y = 52`. Width: `300` px, Height: `18` px.
     - Background: Dark Gray `FLinearColor(0.1f, 0.1f, 0.1f, 0.8f)`.
     - Fill: Golden Yellow `FLinearColor(0.95f, 0.75f, 0.1f, 1.0f)`.
     - Text Overlay: `"STAMINA: {Current} / {Max}"` centered at `X = 24`, `Y = 54`.

2. **Top-Right Match Status:**
   - Position: Right-aligned (`Canvas->ClipX - 250`), `Y = 20`.
   - Line 1 (`Y = 20`): `"WAVE: {CurrentWave} / 3"`, White `FLinearColor::White`.
   - Line 2 (`Y = 44`): `"ENEMIES: {RemainingEnemies}"`, Yellow `FLinearColor(1.0f, 0.9f, 0.2f, 1.0f)`.
   - Line 3 (`Y = 68`): `"SCORE: {Score}"`, White `FLinearColor::White`.
   - Line 4 (`Y = 92`): `"TIME: {MM:SS}"`, Light Gray `FLinearColor(0.8f, 0.8f, 0.8f, 1.0f)`.

3. **Center Reticle:**
   - Centered at `(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.5f)`.
   - Crosshair dimensions: 4px dot or crosshair lines of length 6px, White `FLinearColor(1.0f, 1.0f, 1.0f, 0.75f)`.

4. **Bottom-Left Ability Indicator:**
   - Position: `X = 20`, `Canvas->ClipY - 60`.
   - Heavy Attack Indicator:
     - Ready: Text `"[RMB] HEAVY ATTACK: READY"`, Cyan `FLinearColor(0.2f, 0.9f, 1.0f, 1.0f)`.
     - On Cooldown: Text `"[RMB] HEAVY ATTACK: {CooldownRemaining}s"`, Gray `FLinearColor(0.5f, 0.5f, 0.5f, 0.8f)`.

5. **Inter-Wave Announcement (Center Overlay):**
   - When Wave $N$ clears and countdown is running:
   - Centered at `Y = Canvas->ClipY * 0.35f`.
   - Text: `"WAVE {CompletedWave} CLEARED!"` (Size Scale 2.0x, Gold).
   - Text (`Y + 40`): `"NEXT WAVE IN: {SecondsRemaining}s"` (Size Scale 1.5x, White).

### 7.3 Game Over Screen Layout (`GameOver`)
- **Full Screen Overlay:** Semi-transparent Black box `FLinearColor(0.0f, 0.0f, 0.0f, 0.75f)` over full `(ClipX, ClipY)`.
- **Card / Content Anchor:** Centered vertically and horizontally:
  - Header: `"GAME OVER"`, Red `FLinearColor(0.95f, 0.1f, 0.1f, 1.0f)`, Scale 3.0x, at `Y = ClipY * 0.30f`.
  - Wave Reached: `"DEFEATED ON WAVE: {Wave} / 3"`, White, Scale 1.5x, at `Y = ClipY * 0.42f`.
  - Final Score: `"FINAL SCORE: {Score}"`, Yellow, Scale 1.5x, at `Y = ClipY * 0.48f`.
  - Enemies Slain: `"ENEMIES DEFEATED: {TotalEnemiesDefeated}"`, White, Scale 1.2x, at `Y = ClipY * 0.54f`.
  - Prompt: `"PRESS [R] TO RESTART ARENA"`, Light Cyan, Scale 1.5x, at `Y = ClipY * 0.65f`.

### 7.4 Victory Screen Layout (`Victory`)
- **Full Screen Overlay:** Semi-transparent Dark Navy box `FLinearColor(0.02f, 0.05f, 0.15f, 0.8f)` over full `(ClipX, ClipY)`.
- **Card / Content Anchor:** Centered vertically and horizontally:
  - Header: `"VICTORY ACHIEVED"`, Gold `FLinearColor(1.0f, 0.84f, 0.0f, 1.0f)`, Scale 3.0x, at `Y = ClipY * 0.30f`.
  - Subtitle: `"ALL WAVES CLEARED"`, White, Scale 1.5x, at `Y = ClipY * 0.40f`.
  - Final Score: `"FINAL SCORE: {Score}"`, Yellow, Scale 1.8x, at `Y = ClipY * 0.46f`.
  - Total Time: `"CLEAR TIME: {MM:SS}"`, Light Green, Scale 1.3x, at `Y = ClipY * 0.52f`.
  - Health Remaining: `"SURVIVING HEALTH: {Health} / 100"`, White, Scale 1.2x, at `Y = ClipY * 0.57f`.
  - Prompt: `"PRESS [R] TO PLAY AGAIN"`, Light Cyan, Scale 1.5x, at `Y = ClipY * 0.65f`.

---

## 8. Architectural & Headless Testing Guidelines

In compliance with ADR-001, ADR-002, and Studio Standards:
1. **Plain Rule Structs (ADR-002):**
   Combat attributes, stamina calculations, wave progression state, and scoring logic must reside in a plain USTRUCT (e.g., `FWaveCombatRules`) with deterministic pure/static helper functions. This permits 100% headless test coverage in `ShunyaGame.Wave.*` without requiring an active `UWorld` or graphics viewport.
2. **Component Separation (ADR-001):**
   `UHealthComponent` and `UStaminaComponent` manage resource pools and can be instantiated with `NewObject<>()` in headless automation tests.
3. **Decoupled HUD Formatting:**
   HUD text formatting (e.g., `FormatWaveString`, `FormatTime`, `FormatScore`) must be implemented as pure static helpers tested in `ShunyaGame.HUD.*` without calling `AHUD::DrawHUD()` or relying on `Canvas`.
4. **Enemy Steering Separation:**
   Enemy steering calculations (direction to player and position step at 320 units/s) should be exposed via a testable calculation method `CalculateSteeringVelocity(CurrentPos, TargetPos, DeltaTime)` testable without physics world simulation.
5. **Autoplay Bot Contract:**
   The `-ShunyaAutoPlay` bot exercises WASD movement, Sprint, Dodge, and LMB/RMB attack verbs, logging:
   `ShunyaPlaytest: {"result":"WIN","score":<Score>,"health":<HP>,"seconds":<Sec>,"avg_fps":<FPS>,"worst_frame_ms":<MS>,"missing_content":0}`

---

## 9. Traceability Matrix

| Acceptance Criterion | GDD Section | Key Specified Values |
| :--- | :--- | :--- |
| **Doc Location & Core Loop** | Section 1, 6, 7 | `Docs/Design/GDD_OutdoorWaveCombat.md`, Core loop, pacing, UI layouts |
| **Player Locomotion & Dodge** | Section 2.1, 2.2 | Base Walk: 400, Sprint: 700 (20/s cost), Dodge: 400 dist, 0.3s duration & i-frames (25 cost) |
| **Combat & Stamina Economy** | Section 3.1, 3.2 | Max HP: 100, Max Stamina: 100, Regen: 15/s (1.0s delay). Light: 15 cost, 25 dmg. Heavy: 35 cost, 60 dmg (3.0s cooldown) |
| **Enemies & Wave Pacing** | Section 4.1, 4.2 | 3 waves (W1: 3, W2: 5, W3: 8 at 1.25x HP). Move: 320, Range: 120, Dmg: 15, Cadence: 1.5s cooldown |
| **Win/Loss Conditions** | Section 6.1, 6.2, 6.3 | Health <= 0 triggers Game Over; Clearing Wave 3 triggers Victory; 'R' restarts match |
