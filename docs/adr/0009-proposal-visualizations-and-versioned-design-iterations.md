# ADR-0009: Generated visualizations for every proposal; versioned design iterations

- **Status:** accepted (product requirement stated by the product owner on 2026-11-17); provider choice remains open
- **Date:** 2026-11-17
- **Deciders:** product owner (requirement), Claude Code (author)
- **Related:** ADR-0008 (Design Studio strategy, learning mechanisms), ADR-0006 (private storage), ADR-0007 (capture and voice), `ARCHITECTURE.md` §1, §5, §7, §9, §11–§12; `PRODUCT.md` §4, §6

## Context and problem

`ARCHITECTURE.md` v0.4 listed "generative before/after previews" as a Stage 1 non-goal. The product owner has made a generated image a **mandatory part of every transformation proposal** (Slice 3 onwards): a stylist judges a design idea visually, by comparing the actual garment with the proposed result. Text alone is not enough.

A generated image is persuasive, and therefore risky: it can look plausible while being impossible to sew, and it can invent details (pockets, buttons) the garment does not have. We need to decide how images are generated, stored and versioned, how they are distinguished from evidence, and how feedback on them is captured.

## Considered options

1. Text-only proposals, optional images later (v0.4 non-goal). Rejected by the product owner.
2. Generic text-to-image illustrations. Rejected: they do not show *this* garment and would mislead.
3. **Image-conditioned generation from the garment's own photos for every proposal, stored immutably with provenance and always labelled as an AI visualization** (chosen).

## Decision

### Requirement

- Every AI transformation proposal consists of **text** (title, concise description, key construction changes, known material/feasibility limits) **and a generated image** of the expected result. A proposal without an image is incomplete; if image generation fails, the proposal is shown with an explicit "visualization failed — retry" state, never with a stock picture.
- Images are **image-conditioned** on the project's source photos. They should preserve identifiable properties the transformation does not intentionally change (fabric appearance, colour, texture, buttons, pockets, decorative elements, construction details) and avoid inventing details.
- Each revision (Slice 4) produces an updated description **and** an updated image.

### Four things the UI and data model never conflate

1. **AI visual concept** (generated image) — always labelled as an AI visualization, never shown as or stored as a photograph.
2. **Technical feasibility assessment** (AI and/or expert) — separate field; a convincing image is not evidence of feasibility.
3. **Expert validation** (decision and comments).
4. **Actual completed transformation** (Slice 7 after-photos) — the only real evidence of the result.

### Versioned design iterations (planned data model)

- A proposal is immutable. A revision is a new proposal with `parent_proposal_id` (the one it revises), a new text and a new image. Earlier proposals, images and decisions are never overwritten.
- Each proposal records: project/garment, source media ids, analysis run id, generation (batch) id, version/parent, text, image reference(s), model and prompt versions for **both** text and image generation, generation parameters (including seeds where available), expert decision, expert feedback and timestamps.
- Generated images are stored as **immutable objects in private object storage** (planned key layout `generated/{garment}/{proposal}/{image}`), served only through authenticated, owner-checked API endpoints like photos (ADR-0006); the raw provider response is kept privately with a checksum. Display copies follow the same metadata rules as photos.

### Image-specific expert feedback (Slice 4)

Feedback may concern the design or the picture. The original words (voice or text) are always kept; structured labels are added next to them (expert-selected or AI-extracted and unreviewed) with at least these dimensions: **aesthetic preference**, **technical feasibility**, **visual generation accuracy** (e.g. "the image added pockets that do not exist"), and **construction/material constraints**. "The visual is good but the construction is impractical" must be representable.

### Capabilities and providers

- A provider-independent `TransformationVisualizer` capability (image-conditioned generation) joins the existing capability contracts; it is defined when Slice 3 implements it, not before.
- The image generation provider is **open** (added to open decision 3). Sending garment photos to an external generation provider is a data transfer covered by open decision 5 (consent/retention) and must be reviewed when the provider is chosen.

### UI (planned)

Project-level views: **Materials** (implemented: photos, notes), **AI Ideas** (analysis, proposal cards), **History** (analyses, proposals, feedback, revisions). Proposal cards put the generated image first, then title, short description, key changes, limitations, and actions (approve, reject, voice/text feedback, request revision). A full-screen before/after comparison is planned for the slice that ships proposals; no placeholder controls before then.

## Consequences

- `ARCHITECTURE.md` no longer lists generative previews as a non-goal; Slice 3 scope grows (image generation, storage, latency and cost), and Slice 4 revisions regenerate images.
- Generation is slow and costly: it runs as persisted jobs in the worker, with timeouts, bounded retries and per-proposal status (text ready, image pending/failed).
- Evaluation gains **visual fidelity to the original garment** and **visual accuracy** metrics; acceptance of attractive images must not be mistaken for feasibility.
- Generated images are never exported as ground truth or as "after" photos; datasets mark them as model outputs.
- **Reversibility:** the requirement is a product decision; the storage/provenance design is cheap now and expensive to retrofit; the provider is replaceable behind the capability contract.
