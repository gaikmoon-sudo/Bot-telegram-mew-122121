# Telegram Academy V5 — Release Notes

## Included

- V4 foundation preserved: Telegram bot, persistent learning progress, quizzes, streaks/badges/certificate flow, reminders, admin tools, Mini App IDE and isolated code Sandbox.
- AI Tutor layer added as an optional feature.
- Persistent AI conversation history with a bounded retention window.
- Compact educational memory derived from recent student questions.
- Lesson-aware retrieval over the academy's own content.
- AI Code Reviewer for C++ and Python text submissions.
- Daily usage quotas for tutor, code review, and future smart quizzes.
- AI response feedback buttons.
- `/ai` command and AI buttons in the main menu, dashboard, and lesson view.
- Server-side API key design; no key is embedded in the Mini App.
- AI is disabled by default (`AI_ENABLED=false`).

## Deliberately not enabled yet

- Smart Quiz generation is represented in the UI but is intentionally not wired into live student assessment yet. It should first gain structured JSON/schema validation, duplicate detection, answer verification, and persistence before being allowed to create Telegram Quiz Polls.
- No API key is included in this release.

## Validation performed

- Python `compileall` passed.
- AST parsing of all Python files passed.
- SQLite AI schema/migration smoke tests passed.
- AI storage/quota smoke tests passed. The full AI request path was not live-tested because the build environment does not contain the Telegram bot runtime dependencies/credentials.
- Searched the release for hard-coded OpenAI keys, `drop_pending_updates=True`, and legacy `coming_soon` references.

A live Telegram/OpenAI request and Docker runtime could not be executed in the build environment because credentials/network access and Docker are not available there. Those are deployment tests, not hidden assumptions in the source.


## V5.1 safety and performance hardening

- Added best-effort Redis AI response caching with SHA-256 cache keys that
  include provider/model/mode/system prompt/messages. Redis failures never
  break AI requests.
- Added a shared Redis connection module that remains optional when Redis is
  not configured.
- Added Sentry initialization through a dedicated configuration object with
  PII disabled by default and configurable trace/profile sampling.
- Hardened the dedicated Sandbox service with CPU, address-space, file-size and
  process-count limits, bounded concurrency, minimal child environment,
  read-only filesystem, dropped Linux capabilities, `no-new-privileges`, and
  Docker-level memory/CPU/PID limits.
- Added a private bot-to-sandbox shared token so the execution endpoint cannot
  be invoked by arbitrary clients on the internal network.
- The sandbox never mounts the Docker socket and never launches Docker from
  inside the sandbox; this avoids turning the execution service into a host
  control boundary.
