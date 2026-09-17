# OpenCode Workflow Guide — dronePrjs / closedSpace

> **Goal:** Use OpenCode to complete the remaining 9 open ISCs on `closedSpace`,
> using a two-model strategy: one model for *reasoning/planning*, one for *building*.

---

## 1. What Is OpenCode?

OpenCode is a **terminal AI coding assistant** (v1.18.31 on this machine). You run it
inside a terminal and it opens a **TUI (Terminal User Interface)** — a full-screen
interactive app, like vim or htop, but for chatting with an AI that can read, write,
and run code in your project.

Key mental model:

```
┌─────────────────────────────────────────────────────────┐
│  CONVERSATION PANEL         │  CODE / DIFF PREVIEW       │
│                             │                            │
│  You type prompts here.     │  AI's file edits appear    │
│  AI replies here.           │  here before you approve.  │
│                             │                            │
├─────────────────────────────────────────────────────────┤
│  INPUT BAR  (type your message, press Enter to send)     │
└─────────────────────────────────────────────────────────┘
```

When the AI wants to **read a file**, **write code**, or **run a command**, it asks for
your approval. You press `y` to allow or `n` to deny — nothing happens to your files
without your say-so.

---

## 2. Launching OpenCode

Always launch from the **project root** so OpenCode sees the full codebase:

```bash
cd ~/Documents/AIStuff/wegofwd2020-hub/dronePrjs
opencode
```

Launch with a specific model from the start:

```bash
opencode -m ollama/qwen2.5-coder:32b
```

Continue your last session (picks up where you left off):

```bash
opencode -c
```

Continue a specific session by ID:

```bash
opencode session list          # see all sessions + their IDs
opencode -s <SESSION_ID>       # resume that session
```

---

## 3. Available Models on This Machine

Run `opencode models` to see the full list. As of now, the configured models are:

| Provider | Model | Best For |
|---|---|---|
| `ollama` | `qwen2.5-coder:32b` | **Planning / reasoning** — large, thorough |
| `ollama` | `qwen2.5-coder:7b` | **Building** — fast, good at Python codegen |
| `ollama` | `qwen3.5:9b` | General chat / quick questions |
| `ollama` | `llama3.2:latest` | Lightweight tasks |

### Adding Claude or GPT (optional upgrade)

If you want to add Anthropic (Claude) or OpenAI (GPT) models:

```bash
opencode providers login        # interactive — select a provider, paste your API key
opencode providers list         # verify it's saved
opencode models anthropic       # see Claude models now available
```

Recommended pair once Anthropic is added:
- **Plan:** `anthropic/claude-opus-4-8` — deep reasoning
- **Build:** `anthropic/claude-sonnet-4-6` — fast, precise Python

---

## 4. Inside the TUI — Essential Keys

| Key | Action |
|---|---|
| `Enter` | Send your message |
| `Esc` | Cancel / go back |
| `Ctrl+C` | Quit OpenCode |
| `Tab` | Switch between panels |
| `y` | Approve a file write or command |
| `n` | Deny a file write or command |
| `↑` / `↓` | Scroll through conversation |

### Slash Commands (type these in the input bar)

| Command | What it does |
|---|---|
| `/model` | Switch to a different model mid-session |
| `/new` | Start a fresh conversation (new session) |
| `/help` | Show all available commands |
| `/clear` | Clear the current conversation context |

---

## 5. The Two-Model Workflow

The core pattern: **think slowly, build fast**.

```
PHASE 1 — REASON (use the 32B model)
  Ask: "What does ISC-12 require? How should I design the state machine?"
  Goal: get a concrete plan with file names, function signatures, edge cases.
  Output: a short written plan you understand and agree with.

PHASE 2 — BUILD (switch to 7B model)
  Type: /model ollama/qwen2.5-coder:7b
  Give it the plan from Phase 1 as context.
  Ask it to implement one function at a time.
  Approve file writes as they come.
  Run tests after each function lands.
```

Why two models?
- The 32B model is slow but reasons better — good for "what should we build and why".
- The 7B model is fast and good at mechanical Python — good for "now write it".
- Switching in-session with `/model` keeps the conversation context intact.

---

## 6. closedSpace — Remaining Work

Of the 44 ISCs, **9 are still open**. Here they are grouped by what you can do *right now*:

### Group A — Build now (no Gazebo needed)

These need Python state-machine / handler code only. The kinematic sim in
`engine/sim/` is enough to test them.

| ISC | What passes | Key file to modify |
|---|---|---|
| ISC-12 | SLAM tracking loss → `SAFE_HOVER` within 200 ms | `closedSpace/mission/` or flight control layer |
| ISC-15 | Ground-station link loss > timeout → RTH + land | `closedSpace/operator/runner.py` |

### Group B — Need Phase 3 complete (Gazebo + PX4 SITL)

The Docker image hasn't been built yet (`make sim-build` is the first step).
Once it's up, these unlock via the reference mission soak.

| ISC | What passes |
|---|---|
| ISC-13 | Perception→command latency p99 < 50 ms over 2-min soak |
| ISC-14 | 0.5 m clearance held throughout reference mission |
| ISC-31 | Zero `COLLISION`-severity log entries after reference run |
| ISC-33 | Zero telemetry samples with `min_clearance_m < 0.5` |

### Group C — Hardware-deferred (skip for now)

| ISC | Why deferred |
|---|---|
| ISC-19 | Image resolution ≥ 4 MP — needs real camera |
| ISC-20 | Focus-quality score ≥ 95% — needs calibration on hardware |

### Group D — Manual / usability study

| ISC | What passes |
|---|---|
| ISC-42 | Untrained warehouse staffer completes mission in ≤ 15 min |

**Recommended order:** A → B (after `make sim-build`) → skip C → D last.

---

## 7. Step-by-Step: Tackling ISC-12 (your first task)

### Step 1 — Open OpenCode with the reasoning model

```bash
cd ~/Documents/AIStuff/wegofwd2020-hub/dronePrjs
opencode -m ollama/qwen2.5-coder:32b
```

### Step 2 — Orient the model (paste this as your first message)

```
I'm working on the closedSpace sub-project of dronePrjs.
Read closedSpace/ISA.md and closedSpace/mission/ to understand the codebase.
I want to implement ISC-12:
  "Mid-mission loss of SLAM tracking transitions the drone to SAFE_HOVER state
   within 200 ms (logged with state-transition timestamp)."
Before writing any code, give me:
1. Which existing files need to change
2. What the SAFE_HOVER state machine should look like
3. What the test should assert
4. Any edge cases I should handle
```

### Step 3 — Review the plan

Read the reply carefully. Push back if anything is unclear:

```
You said to add a slam_watchdog loop — where does it live relative to
the existing mission runner? Does it run in a separate thread or inline?
```

Iterate until you fully understand the plan.

### Step 4 — Switch to the build model

```
/model ollama/qwen2.5-coder:7b
```

### Step 5 — Build one piece at a time

```
Implement only the SLAM watchdog function we designed.
Add it to [file the plan named].
Include the OpenSpec docstring and exception handling per CLAUDE.md rules.
```

Approve the file write when prompted (`y`).

### Step 6 — Run tests immediately

In a **second terminal** (keep OpenCode open):

```bash
cd ~/Documents/AIStuff/wegofwd2020-hub/dronePrjs
pytest closedSpace/tests/ -x -q
```

If a test fails, paste the failure back into OpenCode:

```
Test failed:
<paste the error here>
Fix only this failure, don't touch other files.
```

### Step 7 — Flip the ISC

Once `pytest` passes, open `closedSpace/ISA.md` and change:

```
- [ ] ISC-12: ...
```
to:
```
- [x] ISC-12: ...
```

Add a Verification entry at the bottom of the Changelog section.

---

## 8. Prompt Templates

Copy-paste these into OpenCode as needed.

**Orient a fresh session:**
```
Read CLAUDE.md, closedSpace/CLAUDE.md, and closedSpace/ISA.md.
Summarize: what's built, what's open, and what the engine contract is.
Don't write any code yet.
```

**Plan an ISC:**
```
I want to implement [ISC-NN]: "[paste the criterion text]".
Before writing code: which files change, what's the design, what does the test assert?
```

**Build a function:**
```
Implement [function name] in [file path].
Follow CLAUDE.md: OpenSpec docstring, explicit exception handling, no swallowed errors.
Write the test in closedSpace/tests/[mirrored path].
```

**Debug a failure:**
```
pytest output:
[paste full failure]
The failing test is [test name] in [file].
Root cause only — fix the minimum necessary.
```

**Quality check before committing:**
```
Run: pytest closedSpace/ --cov=closedSpace --cov-fail-under=80
Run: mypy closedSpace/
Run: ruff check closedSpace/
Report pass/fail for each. Fix any failures.
```

---

## 9. Tips & Gotchas

- **Keep sessions short per ISC.** Start a new session (`/new`) for each ISC group.
  Long sessions accumulate stale context and drift.

- **Never use `--auto` flag.** The `--auto` flag skips all permission prompts. Fine
  for throwaway experiments, dangerous on real code — you won't see what it writes.

- **The 32B model is slow on CPU.** If Ollama is CPU-only, `qwen2.5-coder:32b` may
  take 30–90 s per reply. Use it only in the reasoning phase; switch to 7B to build.

- **Engine is the contract.** If OpenCode suggests touching `engine/` internals, push
  back — `closedSpace` must only consume engine via its public interfaces.

- **One function per prompt during build.** Asking for multiple functions at once
  produces harder-to-review diffs. One prompt → one function → approve → test → next.

- **Export a session for reference:**
  ```bash
  opencode session list
  opencode export <SESSION_ID> > sessions/isc12-session.json
  ```

---

## 10. Quick Reference Card

```
Launch:         opencode                          (full TUI)
                opencode -m ollama/qwen2.5-coder:32b   (with model)
                opencode -c                        (continue last session)

Switch model:   /model ollama/qwen2.5-coder:7b    (inside TUI)

List sessions:  opencode session list
Add provider:   opencode providers login

Run tests:      pytest closedSpace/ -x -q
Lint:           ruff check closedSpace/
Types:          mypy closedSpace/
Coverage:       pytest closedSpace/ --cov=closedSpace --cov-fail-under=80

ISC checklist open: ISC-12, 13, 14, 15, 31, 33 (sim), 19, 20 (HW), 42 (manual)
Next action:    ISC-12 (SLAM loss → SAFE_HOVER) — no Gazebo needed
```
