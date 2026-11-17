# ADR-0008: Design Studio first; expert feedback and learning architecture

- **Status:** accepted (product strategy and principles, stated by the product owner on 2026-11-17); the roadmap details marked *proposed* below need approval
- **Date:** 2026-11-17
- **Deciders:** product owner (strategy), Claude Code (author)
- **Related:** `PRODUCT.md` v0.3 (§1–§2, §5, §9, §11), `ARCHITECTURE.md` v0.4 (§5, §7, §8, §11, §12), ADR-0007 (voice notes and transcripts)

## Context and problem

PRODUCT.md v0.2 described an "Expert MVP" followed by "Specialized Fashion AI" and a "Consumer Application", and listed slices in which before/after documentation (Slice 5) came before the dataset foundation (Slice 6). The product owner has clarified the long-term direction:

- The primary product for the foreseeable future is an **internal AI Design Studio**: a professional stylist works with AI, and the system's main value is a complete AI-assisted workflow **plus** systematically captured expert knowledge, used to measurably improve AI suggestions.
- A **commercial Upcycling Assistant** (working names: *Upcycling Assistant*, *Shopping Assistant*) comes only after the Design Studio workflow is validated and the AI shows measurable improvement. It reuses the Studio's backend services and knowledge.

"Learning" was not defined precisely. Without definitions, the team could over-promise ("self-learning AI") or build infrastructure (vector databases, fine-tuning pipelines) before there is data or an evaluation that justifies it.

## Considered options

1. **Keep v0.2 as is**: consumer application as a later phase, learning implied by data collection. Leaves "learning" ambiguous and orders slices without evaluation.
2. **Build towards the commercial app early** (shared UI, shopping features): would split effort before the AI workflow is validated.
3. **Design Studio first, with explicitly separated learning mechanisms and evaluation gates** (chosen).

## Decision

### Strategy

1. **Stage 1 — AI Design Studio** (internal expert platform) is the only development focus. Consumer/shopping features are out of scope until Stage 2 is approved.
2. **Stage 2 — Commercial Upcycling Assistant** starts only after (a) the Studio workflow has been validated with the expert and (b) evaluation shows measurable improvement from expert knowledge over a baseline. It reuses the API, AI capability adapters, knowledge base and evaluation tooling; it gets its own product specification, privacy review and ADRs.

### Three learning mechanisms, never conflated

| Mechanism | What it is | Changes model weights? | When |
|---|---|---|---|
| **A. Within-project adaptation** | The project's history (photos, notes, earlier analyses, suggestions, expert decisions and feedback) is assembled into the context of the next generation | No | Slice 4 |
| **B. Cross-project expert memory** | Relevant knowledge from *other* projects (structured expert rules, similar past cases, preference signals) is retrieved and given to the model, or used to rank suggestions | No | Slice 5, behind an evaluation |
| **C. Model training / fine-tuning** | Supervised training on curated, consented, verified data | Yes | Only after Slice 6 evaluation shows it is justified; separate ADR |

Saving feedback does **not** train a model. The product and documentation must not describe the system as "self-learning" unless mechanism C exists and its effect has been evaluated. Mechanisms A and B are described as "uses expert feedback" or "expert memory".

### Knowledge sources stay separate

Every fact keeps its source and is never silently merged:

1. **AI predictions** (analyses, suggestions) — immutable, with provider, model, prompt version, parameters, input references and timestamps.
2. **Expert observations** — photos, voice recordings (ADR-0007), typed notes, transcripts (machine and expert-corrected as separate records).
3. **Expert corrections** — new records that reference the prediction they correct; the prediction is never overwritten.
4. **Expert preferences and decisions** — approve, reject, modify, alternative idea, regeneration request; the original free-text/voice feedback is always kept; structured labels (e.g. rejection reasons) extracted from it are separate records marked as *expert-selected* or *AI-extracted, unreviewed*.
5. **Verified labels and real outcomes** — explicitly reviewed facts (e.g. "60% linen, 40% viscose" from a label photo) and completed transformations.

Example: AI "cotton" → expert correction "linen-viscose blend" → verified label "60% linen, 40% viscose": three records, each traceable.

### Iterations are first-class

A garment project can have many analyses, many suggestion batches (generations), many expert reviews and revisions. A revised suggestion is a new record that may reference the one it supersedes; rejected suggestions stay rejected. Relational tables with explicit provenance columns; no event-sourcing framework.

### Expert effort first

Feedback must be natural (voice or a short text, one-tap decisions). Structured fields such as rejection reasons are optional quick choices (insufficient fabric, unsuitable material, construction limitations, excessive complexity, poor aesthetic result, other) or are extracted by AI afterwards and marked as unreviewed. No mandatory forms.

### Evaluation gates

Improvements must be measured against a stable, versioned evaluation set split by garment/project (no leakage between memory/training data and evaluation). Compare at least: baseline (no expert memory), with project feedback (A), with cross-project memory (B). Metrics include analysis accuracy against verified labels, suggestion acceptance, technical feasibility, novelty/diversity, expert editing effort, time to first useful suggestion, retrieval relevance, and quality across iterations. **Acceptance rate alone is not a success metric**: optimizing it rewards safe, repetitive ideas.

### Roadmap (supersedes the slice list in ARCHITECTURE.md v0.3 §11)

| Slice | Scope | Status |
|---|---|---|
| 0 | Foundation | done (merged) |
| 1 | Garment capture & persistence | implemented (PR #2) |
| 1.1 | Mobile capture UX & voice notes | implemented (PR #2), iPhone verification pending |
| 2 | AI garment analysis | next, not started |
| 3 | AI transformation suggestions + generated visualizations ([ADR-0009](0009-proposal-visualizations-and-versioned-design-iterations.md)) | planned |
| 4 | Expert review & iterative regeneration (mechanism A, transcription) | planned |
| 5 | Cross-project expert memory (mechanism B) | planned — *proposed: starts with a minimal evaluation harness, see below* |
| 6 | Evaluation & dataset | planned |
| 7 | Real transformation outcomes (before/after) | planned (was Slice 5) |
| 8 | Commercial Upcycling Assistant | Stage 2, needs separate approval |

*Proposed (needs approval):* because Slice 5 precedes the full evaluation slice, Slice 5 should begin with a **minimal evaluation harness** (a small frozen set of past projects, the baseline vs. memory comparison, and expert blind review of suggestions), and the first memory implementation should be the simplest measurable one: structured expert rules and similar-case retrieval over relational data. A vector index (e.g. pgvector inside PostgreSQL) only if the evaluation shows that simpler retrieval is insufficient; no separate vector database without an ADR.

## Consequences

- PRODUCT.md, ARCHITECTURE.md and CLAUDE.md are updated to the Stage 1/Stage 2 strategy, the learning mechanisms and the new slice order. Slice 0–1.1 decisions and code are unchanged.
- The planned data model (ARCHITECTURE.md §5) gains explicit records for generation runs/suggestion batches, suggestion revisions, expert reviews, extracted feedback labels, verified labels and transcripts. They are **planned**, not implemented; each slice designs its tables with migrations and tests.
- Before/after outcomes move from Slice 5 to Slice 7; they remain the most valuable verified data, but the iterative design loop and its evaluation come first.
- The v0.2 target "≥80% expert approval" is no longer a sufficient success criterion; it stays as one signal among the metrics above.
- Risks: the evaluation set is small with one expert (high variance, expert-specific taste); memory may encode one person's preferences (acceptable for the Studio, must be reconsidered for Stage 2); extracting structured labels with AI can introduce errors (kept as unreviewed).
- **Reversibility:** the strategy is a product decision and can change; the data principles (immutable predictions, separate sources, provenance) are cheap to keep and expensive to retrofit, so they are treated as durable.

## Open questions

1. Is a design project always exactly one garment, or can a project combine several garments (common in upcycling)? Today the garment is the project root aggregate.
2. Who may confirm a "verified label" (only the expert, or also evidence such as a label photo with expert confirmation)?
3. Approval of the Slice 5 approach above (minimal evaluation harness first, relational retrieval before vectors).
4. Training consent and retention for expert media and feedback (open decision 5) before any mechanism C or any Stage 2 reuse of Studio data.
5. Final Stage 2 product name and target users.
