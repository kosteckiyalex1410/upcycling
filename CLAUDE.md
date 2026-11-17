# Claude Code — Project Operating Instructions

**Project:** Upcycling — AI Design Studio (Stage 1; the commercial Upcycling Assistant is Stage 2, later)  
**Status:** Stage 1 in development (Slices 0–1.1 implemented)  
**Documentation and code comments:** English  
**Initial UI locales:** Ukrainian (`uk`) and English (`en`)

## 1. Mission and source of truth

Build a reliable, iPhone-first **AI Design Studio** in which a professional stylist works with AI: capture garments, analyze, propose feasible transformations, review and iterate, and preserve every observation, AI output, decision and correction with provenance so that expert knowledge can measurably improve future suggestions. The commercial Upcycling Assistant comes later and is out of scope until approved ([ADR-0008](docs/adr/0008-design-studio-first-and-expert-knowledge-architecture.md)).

Read these files before planning work:
1. `PRODUCT.md` — product strategy, scope and user journeys (v0.3).
2. `ARCHITECTURE.md` — system boundaries, API, data invariants, expert-knowledge mechanisms and delivery slices (v0.4).
3. Relevant ADRs in `docs/adr/` and the code/tests for the affected feature.

If a referenced document is missing, **report the gap**; do not fabricate its contents. If requirements conflict, explain the conflict and propose a specific resolution before implementation. This file governs the development workflow; product and architecture documents govern intended behavior and system design.

## 2. Non-negotiable architectural rules

- **Modular monolith:** Python/FastAPI backend with clearly separated API, domain, application, infrastructure, AI adapters, and worker responsibilities. No microservices or Kubernetes for MVP.
- **API-first:** Public client contract under `/api/v1`, described by FastAPI/OpenAPI. Generate the TypeScript API client from the schema; do not maintain divergent handwritten DTOs.
- **Replaceable AI:** Define capability interfaces for garment, fabric, defect, and transformation understanding. External VLM/speech services are adapters, not domain dependencies. Do not couple client code to a provider.
- **Asynchronous inference:** Long-running AI/transcription/refinement tasks run through persisted jobs and a worker; HTTP handlers must not wait on slow inference. Start with PostgreSQL-backed jobs.
- **Immutable evidence:** Preserve original images/audio, completed AI analysis outputs, expert decisions, corrections, and conversation turns as separately attributable records. Do not overwrite original predictions when experts correct them.
- **Recommendation lineage:** Every recommendation links to its analysis run. A refined suggestion gets a new ID and may reference the suggestion it supersedes. Rejection must remain recorded.
- **Human authority:** Never treat unverified AI output as ground truth; never infer approval from conversation context. Expert corrections and interpretations must remain distinguishable.
- **Client portability:** Keep business rules server-side. Isolate camera, microphone, local persistence, and network handling behind client platform adapters. PWA is first; native technology remains undecided.
- **Internationalization:** All user-facing UI strings come from `uk` and `en` locale resources. Stable API codes and domain identifiers remain language-neutral. Preserve original-language expert speech/transcripts.
- **Privacy and security:** Authenticate all project/media endpoints; enforce ownership server-side; private object storage; constrained short-lived signed URLs; server-side secrets; no sensitive media, transcripts, tokens, or signed URLs in logs.
- **Proportional complexity:** Build only what the current vertical slice needs. Avoid speculative abstractions, generic frameworks, premature queues, vector DBs, and training infrastructure.

## 3. Repository conventions

Follow the structure defined in `ARCHITECTURE.md`:

- `apps/expert-pwa/`: React + TypeScript + Vite, iPhone-first UI.
- `packages/api-client/`: generated TypeScript client.
- `backend/app/api/v1/`: HTTP routing and validation only.
- `backend/app/domain/`: domain concepts and invariants.
- `backend/app/application/`: use cases and orchestration.
- `backend/app/infrastructure/`: persistence, object storage, external integrations.
- `backend/app/ai/`: AI capability interfaces, adapters, schemas.
- `backend/app/worker/`: durable background job execution.
- `backend/migrations/`: Alembic migrations.
- `ml/`: datasets, evaluation, experiments, training **when required**.
- `docs/adr/`: recorded architectural decisions.
- `infra/`: local development and deployment configuration.

Do not create empty folders or boilerplate for future slices. Prefer readable code, explicit dependencies, typed interfaces, and straightforward naming. Use Python type hints and Pydantic v2 for API contracts. Keep PostgreSQL schema migrations version-controlled.

## 4. Task execution protocol

### Step A — Inspect and plan

Before editing:
1. Read relevant specifications and existing implementation.
2. Restate the requested outcome and its acceptance criteria.
3. Identify files/modules likely to change, API/schema changes, migrations, and risks.
4. Propose the smallest end-to-end vertical slice that delivers the outcome.
5. Identify decisions that are unresolved or would lock in a provider/technology.

For architectural changes, new external providers, auth, storage, retention, training permissions, or mobile-platform commitments: **stop after the plan and request approval**. For routine changes within an approved slice, implement directly unless instructed to plan only.

### Step B — Implement

- Work in a focused branch/PR per slice when Git workflow is available.
- Prefer small, reviewable changes; do not refactor unrelated modules.
- Keep business rules in backend domain/application layers.
- Add or update automated tests with each behavioral change.
- Use deterministic mocks/fakes for provider-dependent tests; never require paid AI calls for routine CI.
- For database changes, include an Alembic migration and migration tests.
- For API changes, update OpenAPI and regenerate the client; verify compatibility.
- For new UI text, update both `uk` and `en` resources.
- Document any deliberate deviation from the approved plan.

### Step C — Verify and report

Run applicable checks, using commands actually defined by the repository. Never claim a check passed if it was not run.

At minimum, when applicable:
- Backend unit and integration tests.
- Database migration up/down or supported migration smoke test.
- Frontend lint, typecheck, tests, and production build.
- OpenAPI/client generation and compatibility check.
- Auth, ownership, upload-validation, and error-path tests for new endpoints.
- Manual iPhone Safari verification for camera/microphone/PWA/network behavior when device access is available; otherwise flag it explicitly as **not verified**.

Final implementation report must include:
1. What changed.
2. Tests/checks executed and outcomes.
3. Unverified behavior and remaining risks.
4. Migration/configuration implications.
5. Next recommended slice.

## 5. Data and ML safeguards

- Store raw provider responses and provenance (provider/model ID, prompt version, input media IDs, output schema version, timestamps) with each AI run.
- Preserve raw audio separately from transcripts and AI-extracted summaries.
- Preserve `before` and `after` images with their actual transformation plan/outcome relationships; do not assume a recommendation was executed.
- Separate AI-inferred labels, expert corrections, expert-confirmed labels, and uncertain/unreviewed annotations.
- Fabric composition, stretch, weight, and hidden construction may be unknown from images; represent uncertainty instead of inventing facts.
- Do not present uncalibrated model confidence as statistical certainty.
- Do not automatically fine-tune or change deployed model weights from incoming feedback. Saving feedback is not training.
- Keep the three expert-knowledge mechanisms distinct: within-project context adaptation, cross-project expert memory (retrieval/rules/ranking), and explicit training. Never describe the system as "self-learning" unless training exists and has been evaluated.
- Keep five knowledge sources separate: AI predictions, expert observations, expert corrections, expert preferences/decisions, verified facts/outcomes. Structured labels extracted by AI from expert words are separate, marked as unreviewed, and never replace the original words.
- Every AI generation records model, prompt version, parameters, input references and the expert knowledge it used.
- Generated proposal images are AI visualizations: always labelled as such, stored immutably and privately with provenance, never treated as evidence of feasibility or as photos of a real outcome (ADR-0009).
- Measure improvements against a frozen evaluation set (baseline vs. project feedback vs. cross-project memory); acceptance rate alone is not a success metric.
- Dataset exports must have immutable manifests, versioning, selection criteria, provenance, and leakage-aware evaluation splits.
- Do not introduce model training, a vector database, or a model registry until a concrete slice and evaluation justify it.

## 6. API, uploads, and jobs

- Use the `/api/v1` endpoints and domain entities specified in `ARCHITECTURE.md` unless an approved ADR changes them.
- Authenticate and check resource ownership on every relevant read/write, including signed-media operations.
- Uploads: issue short-lived constrained signed URLs, verify uploaded objects before registration, validate size/type, and handle interrupted/retried uploads.
- Use idempotency keys for duplicate-prone creation, upload completion, and job submission.
- For async tasks, persist job status, attempt count, and machine-readable error codes. Define bounded retries and timeouts.
- Avoid logging raw images, audio, full transcripts, tokens, signed URLs, or other sensitive payloads.

## 7. UX and localization

- Optimize first for a single professional designer using iPhone Safari and an installed PWA.
- Primary journey: capture garment → analyze → review suggestions → approve/reject/comment by voice → AI refinement → save → later attach actual after photos.
- Provide visible states for upload, queued/processing jobs, errors, retries, and missing permissions.
- Do not promise reliable offline image retention on iOS PWA; treat local unsent drafts as best-effort until offline requirements are explicitly resolved.
- Use localized UI copy in Ukrainian and English; keep internal operation codes and persisted taxonomy values stable.
- Preserve expert control: voice interpretation must not silently change approval/rejection state.

## 8. Architecture decision records

Create an ADR under `docs/adr/` for decisions that change a durable system boundary or commit to an external provider. Include:
- Context and problem.
- Considered options and trade-offs.
- Decision and rationale.
- Consequences, risks, and reversibility.
- Date and status (`proposed`, `accepted`, or `superseded`).

**Open decisions — do not silently lock in:** hosting/object storage provider; production email provider; initial VLM/speech/image-generation providers; hard offline requirement; data retention and training consent; defect geometry and fabric taxonomy; project vs. garment cardinality; cross-project memory approach; Stage 2 scope and data reuse. See `ARCHITECTURE.md` §12. Authentication is decided in ADR-0003; the photo upload/storage protocol (provider-independent) in ADR-0006; voice notes in ADR-0007; the Design Studio strategy and expert-knowledge architecture in ADR-0008; proposal visualizations and versioned iterations in ADR-0009.

## 9. Delivery order and definition of done

Follow the vertical-slice order (details and status: `ARCHITECTURE.md` §11, [ADR-0008](docs/adr/0008-design-studio-first-and-expert-knowledge-architecture.md)); implement only the current slice:

0. Foundation.
1. Garment capture and persistence. 1.1 Mobile capture UX and voice notes.
2. AI garment analysis.
3. AI transformation suggestions + generated visualizations (every proposal has text and an image; ADR-0009).
4. Expert review and iterative regeneration (within-project adaptation, transcription).
5. Cross-project expert memory (simplest measurable approach first, with a baseline comparison).
6. Evaluation and dataset preparation.
7. Real transformation outcomes (before/after).
8. Commercial Upcycling Assistant (Stage 2; separate approval).

A slice is **done** only when its user-visible path works end-to-end, failure paths are covered, relevant tests pass, security/ownership checks are applied, docs/contracts are updated, and remaining manual verification is explicitly recorded. Do not claim production readiness merely because a demo works locally.

Local setup, commands and quality gates: see `docs/development.md`.

## 10. First Claude Code assignment: Slice 0 (historical)

**First action: planning only.** Inspect the repository and read `PRODUCT.md`, `ARCHITECTURE.md`, and this file. Produce a concise implementation plan for Slice 0 including:

- Proposed folder/files layout (only what Slice 0 requires).
- Development environment and minimal local startup path.
- Dependency/tool choices with reasons and versions to be verified.
- Initial authentication options and a recommendation **without committing** to one.
- PostgreSQL migration/bootstrap strategy.
- OpenAPI-to-TypeScript client generation workflow.
- `uk`/`en` localization scaffolding.
- CI quality gates and testing approach.
- Required ADRs and unresolved decisions.
- Acceptance tests and implementation order.

**Do not create files, install packages, provision services, or commit code until the Slice 0 plan and provider-dependent decisions are approved.**
