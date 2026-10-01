# Knowledge index

Where to look, by question.

| Question | Document |
|---|---|
| What is the game? | `Design/GDD.md` |
| What are the numbers? | `Design/Tuning.md` |
| How does the drone behave? | `Design/ThreatSpec.md` |
| Where is everything in the level? | `Design/LevelLayout.md` |
| What text appears on screen? | `Design/Narrative.md` |
| How does it control? | `Design/ControlsAndFeel.md` |
| How is the code organised? | `Tech/TechnicalDesign.md`, `README.md` (class reference) |
| What should assets look like? | `Art/StyleGuide.md`, `Art/ConceptBoard.png` |
| How is the level built and lit? | `Environment/Brief.md` |
| What sounds exist? | `Audio/Brief.md` |
| What moves, and how? | `Animation/Brief.md` |
| Does it work? | `QA/PlaytestReport.md`, `QA/PerformanceReport.md`, `QA/RegressionReport.md`, `QA/SignOff.md` |
| What shipped? | `Release/ReleaseNotes-0.1.0.md` |
| Why is it built this way? | `adr/` |
| How do we write code here? | `CodingStandards.md` |

## Decisions (ADRs)
- ADR-001 - Gameplay state lives in replicated, server-authoritative components.
- ADR-002 - Match rules are a plain struct, not an actor.

## Keeping this current
Add a row when a new document is merged. If a document and the code disagree, the code wins: fix the document.
