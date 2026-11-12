# AI Fashion Upcycling Assistant — System Architecture

**Version:** 0.2  
**Status:** Slice 0 decisions recorded (see `docs/adr/`)  
**Product baseline:** PRODUCT.md v0.2  
**Documentation language:** English  
**Initial UI locales:** `uk`, `en`  
**Initial audience:** One expert designer using an iPhone

## 1. Architectural goals

Build a small, deployable expert-facing product that can evolve into a native mobile application and a platform for specialized fashion AI models **without rewriting the backend or losing training provenance**.

Priority order:
1. Fast, reliable validation with real garments.
2. Preservation of original expert evidence and decision history.
3. Stable, versioned client/backend boundaries.
4. Replaceable AI capabilities and measurable model quality.
5. Operational simplicity and reasonable inference costs.

**Explicit non-goals for the MVP:** microservices, Kubernetes, automated retraining, real-time model weight updates, a consumer marketplace, generative before/after previews, or a native mobile application.

## 2. System context

```text
 iPhone / Safari / installed PWA
   ├── camera, photo picker, microphone
   ├── localized UI (uk/en)
   ├── API client and platform adapters
   └── local unsent draft (best effort)
                  │ HTTPS / JSON
                  ▼
       FastAPI modular monolith
   ├── identity and access control
   ├── garment projects and media
   ├── analyses and recommendations
   ├── conversation and expert feedback
   ├── transformation outcomes
   ├── dataset review and export
   └── AI orchestration and adapters
          │             │           │
          ▼             ▼           ▼
     PostgreSQL   S3-compatible   AI provider(s)
                    storage      VLM / speech
          │
          ▼
     async job worker (same codebase; separate process)
```

Use **one deployable backend codebase** with API and worker processes. Start with a database-backed job table and worker polling; introduce a dedicated queue only if throughput, latency, or reliability measurements justify it. The API should return promptly for long-running AI work.

## 3. Technology choices

| Layer | Initial choice | Boundary / evolution path |
|---|---|---|
| Client | React 19, TypeScript 5.9, Vite 8, PWA; Node.js 24 LTS, pnpm | Native client can consume same API; Capacitor is an option, not a commitment |
| UI state | TanStack Query for server state; local component state | Keep domain rules server-side |
| Localization | i18next + react-i18next; JSON locale resources | `uk` (default), `en`; stable language-neutral IDs |
| Backend | Python 3.13, FastAPI, Pydantic v2, uv | OpenAPI as the public contract ([ADR-0004](docs/adr/0004-api-contract-and-client-generation.md)) |
| Persistence | PostgreSQL 18, SQLAlchemy 2.1 (async, psycopg 3), Alembic | Versioned migrations; JSONB only for evolving model-specific attributes; `uuidv7()` keys |
| Binary media | Private S3-compatible object storage | Signed upload/download URLs; no public buckets |
| AI inference | External multimodal API via adapters | Later task-specific hosted models |
| Speech | Server-side speech-to-text adapter | Preserve source audio and transcript |
| Jobs | PostgreSQL-backed jobs + worker | Replace with queue/broker if needed |
| Identity | Email magic link + one-time code, server-side session cookie ([ADR-0003](docs/adr/0003-authentication-email-magic-link.md)) | Passkeys can be added as another login method |
| Email | `EmailSender` port, generic SMTP adapter; Mailpit locally | Production provider undecided |
| Deployment | Containerized API + worker + managed DB/object storage; same-origin topology ([ADR-0005](docs/adr/0005-same-origin-deployment-topology.md)) | Provider-agnostic |
| Testing | pytest, Vitest, Playwright | Include actual iPhone Safari smoke testing |

Avoid committing to React Native, KMP, or Capacitor until native requirements are demonstrated. A PWA cannot be guaranteed to convert automatically into a native app: **the portable assets are contracts, domain rules, tests, and potentially shared TypeScript packages**; native UI may require rewriting.

## 4. Code organization

```text
upcycling/
├── CLAUDE.md
├── PRODUCT.md
├── ARCHITECTURE.md
├── docs/
│   ├── adr/
│   ├── api/
│   ├── ml/
│   └── development/
├── apps/
│   └── expert-pwa/
│       ├── src/
│       │   ├── features/
│       │   ├── shared/api/
│       │   ├── shared/platform/
│       │   └── locales/{uk,en}/
│       └── tests/
├── packages/
│   └── api-client/             # Generated from OpenAPI (committed openapi.json + schema.d.ts)
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   ├── ai/
│   │   │   ├── garment/
│   │   │   ├── fabric/
│   │   │   ├── defects/
│   │   │   └── transformation/
│   │   └── worker/
│   ├── migrations/
│   └── tests/
├── ml/                         # own pyproject/lockfile; never imports backend/app (ADR-0002)
│   ├── datasets/
│   ├── evaluation/
│   ├── experiments/
│   └── training/
└── infra/
```

Create folders when needed by a vertical slice; do not generate empty abstractions simply to match the tree.

## 5. Domain model and ownership

| Entity | Core fields | Notes |
|---|---|---|
| `users` | id, email, preferred_locale, is_active, created_at, updated_at | Single initial user, future multi-user ready; created via CLI, no sign-up |
| `login_challenges` | id, user_id nullable, email_hash, requester_ip_hash, token_hash, code_hash, failed_attempts, expires_at, consumed_at, created_at | Single-use email login; also the rate-limit ledger (ADR-0003) |
| `auth_sessions` | id, user_id, token_hash, auth_method, created_at, expires_at, revoked_at | Server-side sessions; only token hashes stored |
| `garments` | id, owner_id, title, status, created_at, updated_at | Root project aggregate |
| `media_assets` | id, garment_id, role, storage_key, mime_type, checksum, created_at | Roles: original, detail, defect, label, after, audio |
| `analysis_runs` | id, garment_id, status, schema_version, model_id, prompt_version, raw_output_key, structured_output, created_at | Immutable completed outputs |
| `recommendations` | id, analysis_run_id, operation_code, target, rationale, risk, feasibility, created_at | Stable per-suggestion IDs |
| `conversations` | id, garment_id, created_at | Conversation scoped to a garment |
| `conversation_turns` | id, conversation_id, role, text, source_media_id, model_id, created_at | Append-only; user and assistant turns |
| `expert_feedback` | id, garment_id, recommendation_id nullable, decision, comment, source_turn_id nullable, created_at | Approval/rejection/uncertain; corrections separate |
| `attribute_corrections` | id, garment_id, analysis_run_id, attribute_path, original_value, corrected_value, expert_id, created_at | Do not overwrite predictions |
| `transformation_plans` | id, garment_id, status, created_at | Chosen operations, may differ from AI suggestions |
| `plan_operations` | id, plan_id, operation_code, notes, source_recommendation_id nullable | Expert-authored or AI-suggested |
| `transformation_outcomes` | id, plan_id, completion_status, notes, completed_at | Links after photos via media assets |
| `jobs` | id, kind, aggregate_id, status, attempts, idempotency_key, error_code, created_at | Async analysis/transcription/refinement |
| `dataset_exports` | id, version, criteria, manifest_key, created_at | Immutable dataset manifest |

Use UUIDs, UTC timestamps, foreign keys, and explicit indexes for owner, garment, status and creation time. Store media bytes in object storage, not PostgreSQL. Raw provider responses can be retained as private JSON objects; store their references and hashes. Define retention/deletion rules before recruiting external users.

### Domain invariants

- AI output and expert correction are separate records.
- Every recommendation points to the analysis run that produced it.
- Every AI response records model, prompt, input media identifiers, and output schema version.
- Rejected recommendations remain rejected; a refined suggestion receives a **new ID** and optional `supersedes_recommendation_id`.
- Audio transcripts do not replace original audio; AI-extracted interpretation does not replace original expert words.
- `before` and `after` media are linked to the same garment and, when applicable, to an actual transformation outcome.
- Never promote raw AI labels directly into ground-truth training data.

## 6. API design — `/api/v1`

Authentication is required for all project and media endpoints. All non-2xx responses use the error envelope `{"error": {"code", "message", "request_id", "details"}}` with stable, language-neutral codes ([ADR-0004](docs/adr/0004-api-contract-and-client-generation.md)). State-changing requests must carry an allowed `Origin`. Response schemas are versioned and documented with OpenAPI; generate the TypeScript client from the backend schema.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health`, `/health/ready` | Liveness; readiness (database reachable, migrations at head). Unauthenticated |
| `POST` | `/auth/login-requests` | Request magic link + one-time code (always `202`; rate limited) |
| `POST` | `/auth/login-requests/verify-token` | Exchange magic-link token for a session cookie |
| `POST` | `/auth/login-requests/{id}/verify-code` | Exchange one-time code for a session cookie (installed PWA) |
| `POST` | `/auth/logout`, `/auth/sessions/revoke-all` | Revoke current session / all sessions |
| `GET`/`PATCH` | `/me` | Current user profile and `preferred_locale` |
| `POST` | `/garments` | Create garment project |
| `GET` | `/garments` | List current user's projects |
| `GET` | `/garments/{id}` | Fetch project summary |
| `POST` | `/garments/{id}/media/uploads` | Request a short-lived signed upload |
| `POST` | `/garments/{id}/media/complete` | Validate uploaded object and register media |
| `POST` | `/garments/{id}/analyses` | Queue analysis, return job ID |
| `GET` | `/jobs/{id}` | Poll async status and result reference |
| `GET` | `/garments/{id}/analyses` | List immutable analysis runs |
| `GET` | `/garments/{id}/recommendations` | Read suggestions and evaluation state |
| `POST` | `/recommendations/{id}/feedback` | Submit expert decision |
| `POST` | `/garments/{id}/corrections` | Record expert attribute correction |
| `POST` | `/garments/{id}/conversation/turns` | Send text or registered audio reference; queue refinement |
| `GET` | `/garments/{id}/conversation/turns` | Retrieve conversation history |
| `POST` | `/garments/{id}/plans` | Save expert-selected transformation plan |
| `POST` | `/plans/{id}/outcomes` | Record actual outcome and attach after photos |
| `POST` | `/dataset-exports` | Admin-only, curated export request; not required for first slice |

**Example analysis job response:**

```json
{
  "job_id": "0192bcd4-0fd5-78a4-9157-cf9c62d2f017",
  "status": "queued",
  "garment_id": "0192bcd3-6ed2-75d2-9028-b2f12b9980e3"
}
```

**Example model-independent analysis output:**

```json
{
  "schema_version": "1.0",
  "garment_category": "denim_jacket",
  "attributes": [
    {
      "code": "chest_pocket_count",
      "value": 2,
      "evidence_media_ids": [],
      "confidence": null,
      "verification_status": "ai_inferred"
    }
  ],
  "fabric": {
    "visual_description": "Denim-like twill texture",
    "composition": null,
    "composition_status": "unknown"
  },
  "defects": [],
  "uncertainties": ["Pocket removal may leave visible stitch marks"]
}
```

`confidence` is nullable because model self-reported confidence is not necessarily calibrated. Never present it as a validated probability without calibration.

### API and media safety

- Verify garment ownership on every resource access; do not rely on obscurity of UUIDs.
- Signed upload URLs must constrain object key, content type, size, and expiry; verify the actual object before registration.
- Validate MIME by content where feasible; strip or restrict sensitive image metadata on derivative exports while preserving originals according to consent policy.
- Use idempotency keys for create/upload-complete/job submission to avoid duplicates on mobile retries.
- Use pagination and consistent machine-readable error codes.
- Never expose AI provider credentials to the client.

## 7. AI orchestration

### Capability interfaces

Define internal typed interfaces, independent of provider SDKs:

```python
from typing import Protocol

class GarmentUnderstanding(Protocol):
    async def analyze(self, request: "GarmentAnalysisRequest") -> "GarmentAnalysisResult": ...

class FabricUnderstanding(Protocol):
    async def analyze(self, request: "FabricAnalysisRequest") -> "FabricAnalysisResult": ...

class DefectUnderstanding(Protocol):
    async def analyze(self, request: "DefectAnalysisRequest") -> "DefectAnalysisResult": ...

class TransformationRecommender(Protocol):
    async def recommend(self, request: "RecommendationRequest") -> "RecommendationResult": ...

class SpeechTranscriber(Protocol):
    async def transcribe(self, request: "TranscriptionRequest") -> "TranscriptionResult": ...
```

These are **logical capability contracts**, not a requirement for five models or five network calls. Initially, a single VLM adapter may implement garment/fabric/defect understanding, and the same provider may generate recommendations. A separate transcription provider may be used for voice.

### Initial inference flow

1. Worker loads validated image references and project context.
2. Orchestrator invokes VLM with a versioned prompt and strict output schema.
3. Validate response using Pydantic; on invalid output, retry within a bounded budget or fail explicitly.
4. Generate 3–5 suggestions where warranted, using an operation catalog with feasibility/risk constraints.
5. Persist immutable run, provenance, suggestions and uncertainty notes.
6. Return localized explanation text (or generate it for the selected locale) while keeping operation codes language-neutral.

**Safety and epistemic limits:** visual appearance does not prove fabric composition, stretch, internal seam construction, stain chemistry, or feasibility of pocket removal. Use `unknown`, ask for close-up photos or expert confirmation, and label feasibility as an assessment, not a guarantee.

### Interactive refinement

```text
Expert decision / voice note
    → persist raw decision/audio
    → transcribe (if audio)
    → preserve transcript and source language
    → assemble bounded garment conversation context
    → generate revised suggestions
    → persist new analysis/recommendation generation
    → display delta without rewriting prior decisions
```

Use server-side conversation context. Summaries may be introduced for long threads but must not discard the canonical turn history. Expert corrections are authoritative **for the current garment context**, not automatically for all garments.

### Model routing

Model selection belongs in backend configuration, e.g. `garment_understanding: provider_vlm_v1`, `defect_detection: provider_vlm_v1`, `transformation: provider_vlm_v1`. Later replace a capability with a specialized service through the same contract. Keep model artifacts, deployment versions, dataset versions and evaluation results traceable.

## 8. ML data and evaluation architecture

### Annotation layers

1. **Observations:** original photos, audio, expert-authored free text.
2. **Predictions:** model outputs with provenance and schema versions.
3. **Expert judgments:** approvals, rejections, corrections, alternatives, feasibility comments.
4. **Verified labels:** explicitly reviewed/accepted annotations eligible for training.
5. **Outcomes:** actual completed transformations, after photos and deviations from plan.

A thumbs-up is not a full ground-truth label for fabric composition or defect location. Voice transcript interpretations require validation before being treated as precise labels.

### Dataset export

An immutable export manifest should include example IDs, media checksums, annotation versions, expert/source attribution, consent/usage flags, split assignment, and schema version. Keep training/validation/test splits **by garment/project**, not by photo, to avoid leakage. Where possible, hold out later garments or independent experts for realistic generalization evaluation.

### Model roadmap

| Capability | Initial approach | Future experiments | Evaluation |
|---|---|---|---|
| Garment structure | General VLM | Fine-tuned vision/VLM | Attribute precision/recall, critical omissions |
| Fabric/texture | VLM visual descriptors + expert verification | Fabric classification/embedding models | Per-class F1, calibration, unknown handling |
| Defects | VLM + detail photos | Detection/segmentation/anomaly models | Precision/recall, mAP/IoU when localized |
| Transformations | VLM + operation catalog + expert dialogue | Retrieval, ranking, supervised fine-tuning | Expert acceptance, feasibility, diversity, safety |

The first 50 garments are a **product-validation and initial benchmark set**, not a sufficient guarantee for training robust specialized models. Use curated datasets and independent holdouts before promoting a new model.

## 9. Client architecture and mobile evolution

### PWA now

- Camera/photo capture through browser APIs or file input with camera hint; test on real iPhones.
- Microphone recording only after explicit user interaction and permission.
- Best-effort draft persistence; never promise durable offline media on iOS Safari due to storage eviction and background limitations.
- Network-aware upload retry, visible progress, and clear failure states.
- Translation keys for all user-facing strings; selected locale persisted.
- Accessible, touch-first controls and minimal typing.

### Platform abstraction

```text
features/garments/     → use cases and UI
shared/api/            → generated typed API client
shared/platform/       → CameraPort, AudioRecorderPort, LocalDraftPort
```

Avoid browser globals in domain/application logic. This makes Capacitor adapters feasible and keeps a React Native or SwiftUI replacement focused on UI/platform integrations. A later native app is a **separate client decision**, not an automatic code conversion promise.

## 10. Security, privacy and operations

- Single-user MVP still requires authentication and ownership checks. Authentication: email magic link (token in URL fragment) plus a one-time code for the installed iOS PWA, whose cookie jar is separate from Safari; `HttpOnly`/`Secure`/`SameSite=Lax` session cookie; DB-backed rate limiting; session revocation ([ADR-0003](docs/adr/0003-authentication-email-magic-link.md)).
- Private object storage, encryption in transit, least-privilege credentials, secret management and DB backups.
- Explicit consent/terms for using expert media and annotations in training, including rights to images and voice recordings; clarify deletion and export policy before external testing.
- Do not log full images, raw voice transcripts, access tokens or signed URLs in application logs.
- Record structured operational telemetry: request/job IDs, latency, retries, error class, provider/model version, token usage and estimated cost.
- Bound image size, upload size, AI request budget, retries and concurrency.
- Provide a deletion workflow covering DB records, object storage and derived datasets where applicable; document immutable dataset constraints and retention.
- Use separate development and production environments; keep production data out of local development fixtures.

## 11. Delivery and quality gates

**Working method:** one vertical slice per branch/PR, with plan → implementation → automated verification → human review.

### Slice 0 — Foundation
- Repository, development environment, CI, formatting, linting, migrations and health endpoint.
- Basic auth and i18n scaffolding.
- OpenAPI generation and typed client generation.
- Architectural decision records and `CLAUDE.md`.

### Slice 1 — Capture and persist
- Create garment, take/select images, signed upload, finalize media, list/reopen garment.
- Test retries, oversized images, permission denial and invalid ownership.

### Slice 2 — AI analysis
- Async job, VLM adapter, schema validation, immutable analysis record and UI rendering.
- Test provider timeout, invalid output, unknown fabric and missing photos.

### Slice 3 — Recommendations
- Operation catalog, risk/feasibility metadata, suggestion cards and history.

### Slice 4 — Expert interaction
- Approve/reject, audio upload, transcription, conversation turns, iterative refinement and provenance.
- Test that rejected suggestions stay rejected and new suggestions have new IDs.

### Slice 5 — Before/after
- Expert plan, completed transformation, after-photo upload, outcome notes and comparison view.

### Slice 6 — Dataset foundation
- Review states, immutable export manifest, leakage-safe split assignment and benchmark report.

### Required checks for every slice
- Unit and integration tests; DB migration test.
- Typecheck/lint/build; API schema/client compatibility.
- Security checks for new endpoints and storage access.
- Manual iPhone Safari test for camera, microphone, installation and network recovery when relevant.
- Documentation and ADR updates for changed decisions.

## 12. Open decisions (not blockers for documenting the design)

1. Hosting provider and S3-compatible storage provider. *Constrained by [ADR-0005](docs/adr/0005-same-origin-deployment-topology.md): must support same-origin routing of PWA and `/api`.*
2. ~~Initial identity mechanism~~ — **resolved** by [ADR-0003](docs/adr/0003-authentication-email-magic-link.md). Still open: production email (SMTP) provider.
3. Initial VLM and speech providers, chosen after quality/cost tests.
4. Whether reliable offline photo capture is a hard requirement; if yes, revisit native-first strategy.
5. Data retention period, training permissions and deletion semantics.
6. Exact annotation schema for defect geometry and fabric taxonomy after first expert trials.

Do not let Claude Code silently resolve these with arbitrary permanent dependencies. Record chosen options in `docs/adr/` before implementation.

## 13. Architecture acceptance criteria

The design is acceptable when:
- A second mobile client can use the same backend API without moving domain logic out of the server.
- A VLM can be replaced by a specialized model through a capability adapter without breaking client contracts.
- Original AI outputs, expert corrections, dialogue turns and real before/after outcomes remain separately traceable.
- Dataset exports are reproducible and can exclude unverified labels.
- A single developer using Claude Code can run, test, deploy and debug the MVP without operating a distributed microservice platform.

---

**Next artifact:** `CLAUDE.md` — coding rules, planning workflow, architecture guardrails and definition of done.
