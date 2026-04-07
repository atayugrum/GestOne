# GestOne

## Project identity
GestOne is a macOS-first multimodal desktop control application.
It uses computer vision and voice input to control the computer through:
- hand gestures
- two-hand gestures
- head movement
- voice commands

The priority is a practical, local-first productivity tool that is easy to demo, easy to extend, and efficient to build.

---

## Product goals
Build a clean, modular MVP that can later evolve into a polished GitHub portfolio project and a LinkedIn demo project.

Primary goals:
1. Reliable local interaction
2. Minimal latency
3. Clear modular architecture
4. Low-friction manual testing
5. Efficient Claude Code collaboration with low token usage

---

## Platform
- Target platform: macOS only
- Language: Python
- App type: local desktop application
- No cloud dependency unless explicitly requested later

---

## Build philosophy
Always prefer:
- the smallest working implementation,
- minimal but clean abstractions,
- direct, testable code,
- incremental delivery.

Do not overengineer.
Do not add speculative architecture.
Do not introduce complexity before it is needed.

---

## Current roadmap
Build in phases.

### Phase 0 — Setup
- initialize project structure
- create config system
- create shared interfaces and basic modules
- create CLAUDE.md
- no README polish yet

### Phase 1 — Core hand control
- webcam capture
- one-hand detection
- basic gesture detection
- gesture-to-command mapping
- debounce / cooldown
- macOS command dispatch

### Phase 2 — Mouse control
- cursor control from hand landmarks
- pinch to click
- optional scroll mode
- smoothing and sensitivity tuning

### Phase 3 — Head tracking
- face/head tracking
- simple head gesture mapping
- stable signal filtering

### Phase 4 — Voice commands
- lightweight voice command support
- mode switching
- command dispatch integration

### Phase 5 — Minimal dashboard
- lightweight local settings UI
- mode toggles
- sensitivity / cooldown controls
- editable command mappings

### Final phase — Polish
- README
- usage docs
- cleanup
- launch/run notes
- demo notes

---

## Scope constraints
Unless explicitly requested, do NOT add:
- cloud services
- authentication
- database servers
- web backend/frontend stacks
- Docker
- CI/CD
- analytics infrastructure
- plugin systems
- model training pipelines
- packaging/release pipelines
- advanced logging stacks

Use local files and simple config unless a stronger need appears.

---

## Architecture expectations
Prefer a small modular structure with clear boundaries.

Expected concepts:
- app entrypoint
- config
- input capture
- gesture/head/voice detectors
- command dispatcher
- mode manager
- lightweight dashboard
- shared utilities only if truly needed

Keep files purposeful and small.
Avoid large monolithic files unless there is a strong reason.

---

## Token efficiency rules
When working in Claude Code:

1. Be concise.
2. Do not explain obvious concepts.
3. Do not propose many alternatives unless asked.
4. Do not rewrite unchanged files.
5. Return only the files changed in the current step.
6. Keep summaries short.
7. Prefer minimal diffs and local edits.
8. Do not perform unrelated refactors.
9. Do not add README or polish work until explicitly requested.
10. If scope is ambiguous, choose the smallest defensible implementation.

---

## Output rules
Unless asked otherwise, responses should use this structure:

PLAN
- short bullet plan only

FILES
[path/to/file]
```language
...
```

NOTES
- only short essential notes

Do not add long explanations.

---

## Code quality rules
- Write runnable code
- Keep imports clean
- Handle common failure paths
- Use explicit constants/config for thresholds, cooldowns, and mappings
- Prefer simple debugging output over heavy logging
- Add comments only where they genuinely help

---

## UX rules
GestOne should feel minimal and practical.

UI/UX priorities:
- fast startup
- simple controls
- low visual clutter
- obvious mode state
- safe command triggering
- reduced accidental activations

---

## Interaction model
GestOne may include these modes over time:
- gesture mode
- mouse mode
- media mode
- head mode
- voice mode

Modes should be explicit and easy to toggle.
Avoid hidden behavior.

---

## Safety and usability
Focus strongly on:
- debounce
- cooldown
- confidence thresholds
- smoothing
- accidental trigger prevention
- graceful fallback when camera/microphone access fails

---

## Collaboration rule
Always build the smallest working version of the requested phase first.
Do not jump ahead to future phases unless explicitly instructed.
