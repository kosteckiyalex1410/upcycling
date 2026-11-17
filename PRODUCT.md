# UPCYCLING — AI DESIGN STUDIO
## Product Specification v0.3

**Status:** Draft  
**Stage:** Stage 1 — AI Design Studio (internal expert platform); see [ADR-0008](docs/adr/0008-design-studio-first-and-expert-knowledge-architecture.md)  
**Documentation language:** English  
**Initial UI languages:** Ukrainian and English  
**Initial expert users:** 1  
**Development approach:** Spec-Driven Development + Vertical Slices

---

## 1. PRODUCT VISION

Upcycling helps transform existing garments into more desirable, functional and aesthetically appealing products.

**We are building an expert-driven AI Design Studio that systematically captures professional knowledge and improves AI-assisted garment transformation recommendations. The commercial Upcycling Assistant comes later, after the underlying AI workflow has been validated.**

The Design Studio is not only an idea generator. Its goals are to:

1. Provide a complete, end-to-end AI-assisted upcycling workflow for a professional stylist.
2. Capture professional expertise through natural interaction (photos, voice, short decisions).
3. Collect high-quality, structured expert feedback with full provenance.
4. Build a reusable knowledge base of garment analyses, design decisions and transformation constraints.
5. Continuously evaluate AI recommendations against that knowledge.
6. Develop an AI system that measurably benefits from accumulated expert knowledge.

---

## 2. PRODUCT STRATEGY AND ROADMAP

### Stage 1 — AI Design Studio (current focus)

An internal, iPhone-first expert platform. One professional stylist and upcycling expert works with AI on real garments, typically in secondhand stores. This is the only current development focus and is not the initial commercial product.

### Stage 2 — Commercial Upcycling Assistant (later)

A product for consumers and other users to evaluate garments and discover realistic upcycling opportunities (working names: *Upcycling Assistant*, *Shopping Assistant*; final name undecided). It starts only when the Studio workflow is validated **and** evaluation shows measurable improvement from expert knowledge. It reuses the Studio's backend services, AI capabilities, knowledge base and evaluation tooling, and needs its own specification, privacy review and approval. Consumer and shopping features are not prioritized now.

Specialized fashion AI (task-specific models, retrieval, fine-tuning — formerly "Phase 2") is part of Stage 1 and is introduced only where evaluation justifies it.

### Delivery slices

| Slice | Scope | Status |
|---|---|---|
| 0 | Foundation | Done |
| 1 | Garment capture & persistence | Implemented (PR #2) |
| 1.1 | Mobile capture UX & voice notes | Implemented (PR #2); real-iPhone verification pending |
| 2 | AI garment analysis | Next |
| 3 | AI transformation suggestions + generated visualizations | Planned |
| 4 | Expert review & iterative regeneration | Planned |
| 5 | Cross-project expert memory | Planned |
| 6 | Evaluation & dataset | Planned |
| 7 | Real transformation outcomes (before/after) | Planned |
| 8 | Commercial Upcycling Assistant (Stage 2) | Requires separate approval |

Technical scope per slice: `ARCHITECTURE.md` §11. The list is a plan, not permission to implement ahead of the current slice.

### Current implementation status

| Capability | Status |
|---|---|
| Sign-in (email link / 6-digit code), `uk`/`en` | Implemented |
| Projects, photo capture per selected category, one gallery, recategorize later | Implemented |
| Voice notes (original audio stored; playback; deletion) | Implemented; iPhone recording not yet verified on a device |
| Typed project notes | Implemented |
| Transcription of voice notes | Planned (Slice 4; Slice 2 may transcribe for analysis context) |
| AI garment analysis, suggestions with generated visualizations, iterative regeneration | Planned (Slices 2–4) |
| Cross-project expert memory | Planned (Slice 5); approach to be chosen by evaluation |
| Evaluation framework, dataset exports | Planned (Slice 6) |
| Model fine-tuning | Not planned until justified by evaluation |
| Before/after outcomes | Planned (Slice 7) |
| Commercial assistant | Stage 2, not started |

---

## 3. TARGET USERS

### Initial User

One professional stylist and upcycling expert (Stage 1).

The initial application must support a single expert without introducing unnecessary multi-user administration.

However, the architecture must allow future expansion to multiple experts.

### Future Users

- Stage 1: additional fashion designers, upcycling specialists and tailors as experts.
- Stage 2: consumers, resellers and other users of the commercial assistant.

---

## 4. PRIMARY USER JOURNEY

### Scenario: A stylist works on a garment in a secondhand store

The workflow is iterative: a project may have several analyses, several suggestion batches, many expert decisions and revisions. One analysis or one generation is never assumed to be enough.

**Step 1 — Create a project and capture the garment** *(implemented)*

The stylist creates a design project on an iPhone and works on one compact screen: **select category → take photo → change category → take photo**. Category chips (front, back, detail, fabric, defect, label, or no category) stay selected until changed; every photo taken or chosen gets the selected category. All photos appear in one gallery with their category; a category can be changed later on the photo screen.

**Step 2 — Record observations** *(implemented: audio and text are stored; transcription planned)*

The stylist optionally records voice notes ("A men's wool blazer from the 1990s; the lining is damaged…") or types short notes.

**Step 3 — AI analysis** *(planned, Slice 2)*

The AI analyzes the photos (and available notes) and produces structured garment information: garment type, construction elements, visible fabric characteristics, potential defects, and explicitly uncertain attributes. It may ask for more photos or clarification.

**Step 4 — AI suggestions with visualizations** *(planned, Slice 3)*

The AI generates several possible transformations. **Every proposal has text and a generated image of the expected result** ([ADR-0009](docs/adr/0009-proposal-visualizations-and-versioned-design-iterations.md)): title, concise description, key construction changes, known material/feasibility limits, and an image generated from the actual garment photos that keeps the garment's fabric, colour, texture, buttons, pockets and other details unless the transformation changes them. Example: an oversized men's blazer → "Cropped women's blazer": shorten, keep the lapels and shoulder structure, reconstruct the hem — with an image of *this* blazer cropped.

The image is clearly labelled as an AI visualization. A plausible image does not prove the transformation is feasible: the visual concept, the feasibility assessment, the expert's validation and the actual result are separate. On a phone the image comes first; the stylist can compare the original and the proposal side by side or full screen.

**Step 5 — Expert review** *(planned, Slice 4)*

For each suggestion the stylist can approve, reject, modify, add feedback (voice or text), propose an alternative idea, or request regeneration. Feedback can be about the design ("not enough fabric", "the fabric cannot hold this shape") or about the picture ("the image added pockets that do not exist"); the system keeps these apart. Optional one-tap rejection reasons: insufficient fabric, unsuitable material, construction limitations, excessive complexity, poor aesthetic result, other. No complex forms.

**Step 6 — Iterative refinement** *(planned, Slice 4)*

The AI generates revised suggestions that take the feedback and the project history into account (e.g. "Keep the sleeves. I want a more avant-garde transformation."). Each revision has an updated description **and** an updated image. Revised suggestions are new versions; earlier suggestions, images and decisions remain unchanged, so the History view can show how the design evolved.

**Step 7 — Expert knowledge for future projects** *(planned, Slice 5)*

Relevant knowledge from earlier projects (e.g. the stylist repeatedly rejects corsets when the fabric lacks structure) becomes available when analyzing new garments.

**Step 8 — Actual transformation** *(planned, Slice 7)*

The stylist documents the realized transformation with before/after photos.

---

## 5. INTERACTIVE AI REQUIREMENTS

### IA-01 — Context Preservation

The AI must maintain access to the current project context throughout the interaction.

### IA-02 — Iterative Recommendations

The AI must generate updated recommendations based on expert feedback, over as many iterations as needed.

### IA-03 — Voice Interaction

The stylist must be able to record voice notes and voice feedback. The original audio is always kept; machine transcripts and expert-corrected transcripts are separate records. Transcripts are provided to the AI as context.

### IA-04 — Structured Feedback

The system must preserve the original suggestion, the expert decision, the expert's original words, any structured labels (marked as expert-selected or AI-extracted), the AI's interpretation, and the revised suggestion.

### IA-05 — Conversation History

All meaningful interaction turns must be persisted.

### IA-06 — Expert Corrections

Corrections must not overwrite the original AI predictions.

### IA-07 — Human Authority

Expert decisions must remain distinguishable from AI-generated suggestions. The AI must not silently reinterpret a rejected recommendation as approved, and voice interpretation must not silently change a decision.

### IA-08 — How the AI uses expert knowledge

Three different mechanisms, which the product must never conflate ([ADR-0008](docs/adr/0008-design-studio-first-and-expert-knowledge-architecture.md)):

- **Within-project adaptation:** feedback and history of the same project are included in the next generation's context. No model training.
- **Cross-project expert memory:** relevant knowledge from other projects is retrieved (structured rules, similar cases, preferences) and used as context or for ranking. No model training.
- **Model training / fine-tuning:** only with sufficient validated, consented data and an evaluation that justifies it.

Saving feedback does not train the AI. The product must not be described as "self-learning" unless a training mechanism exists and its effect has been measured.

---

## 6. BEFORE/AFTER DOCUMENTATION (REAL TRANSFORMATION OUTCOMES)

*Planned for Slice 7; not to be introduced earlier.*

The stylist will be able to document completed transformations:

- Original garment and its photographs.
- Selected design idea (AI suggestion, revised suggestion or expert's own idea).
- Final transformation and after photographs.
- Materials used, construction challenges and time required.
- Expert evaluation of the result.
- Differences between the AI proposal (text and visualization) and the actual result.

Do not assume that a recommendation was executed. Verified outcomes are the most valuable data for future evaluation and, if justified, model training.

---

## 7. INTERNATIONALIZATION

The initial application must support:

- Ukrainian (`uk`).
- English (`en`).

### Requirements

- All user-facing text must be externalized into localization resources.
- UI components must not contain hardcoded user-facing strings.
- Users must be able to switch languages.
- Language preferences must persist between sessions.
- Backend domain identifiers must remain language-independent.
- AI-generated explanations should follow the selected UI language.
- Original expert comments and transcripts must be preserved in their source language.

Future languages must be addable without modifying core business logic.

---

## 8. AI ARCHITECTURE PRINCIPLES

The system must support independently replaceable AI capabilities:

1. Garment Understanding.
2. Fabric and Texture Understanding.
3. Defect Understanding.
4. Transformation Intelligence.

Initially, these capabilities may share a general-purpose multimodal model.

The architecture must support replacing individual capabilities with specialized models.

AI provider selection must not affect public client API contracts.

---

## 9. EXPERT DATA COLLECTION

The platform must preserve, with source and provenance:

- Original images and original audio recordings.
- Machine-generated transcripts and expert-corrected transcripts (separately).
- AI analyses and AI-generated suggestions, with model and prompt versions, generation parameters, input references and timestamps.
- AI-generated proposal images (labelled as AI visualizations), with the source photos, models, prompts and parameters used.
- Expert decisions, comments, alternatives, preferences and regeneration requests.
- Expert corrections and verified labels.
- Suggestion revisions and refinement history.
- Actual transformation outcomes and before/after photographs.
- Dataset eligibility and consent status.

Five kinds of knowledge are kept apart and never silently merged: **AI predictions, expert observations, expert corrections, expert preferences/decisions, and verified real-world facts/outcomes**. Example: AI "Material: cotton" → expert correction "linen-viscose blend" → verified label "60% linen, 40% viscose" are three traceable records.

Data collection must support future retrieval, ranking, evaluation and supervised learning.

---

## 10. CLIENT APPLICATION STRATEGY

### Initial Client

React + TypeScript Progressive Web Application.

Optimized for iPhone and Safari.

### Future Clients

The platform must support migration or expansion to a full mobile application.

The final mobile technology is intentionally undecided.

Potential approaches include:

- Capacitor.
- React Native.
- Kotlin Multiplatform.
- Native iOS and Android.

Backend APIs and business logic must remain independent of client technology.

---

## 11. SUCCESS CRITERIA AND EVALUATION

The Design Studio is successful when expert knowledge **measurably** improves AI-assisted recommendations. An initial evaluation set of roughly 50 real garments, split by project to avoid leakage, will compare:

- Baseline AI without expert memory.
- AI with project-specific feedback.
- AI with cross-project expert memory.

Metrics (to be defined precisely in Slice 6; a minimal version earlier):

- Garment analysis accuracy against verified labels.
- Suggestion acceptance rate.
- Technical feasibility.
- Visual fidelity of generated images to the original garment.
- Design novelty and diversity.
- Expert editing effort.
- Time to first useful suggestion.
- Relevance of retrieved expert knowledge.
- Quality improvement across iterations.
- Interaction usability, analysis latency and inference cost.

Acceptance rate alone is insufficient: the system must not be optimized towards safe, repetitive or obvious ideas. The earlier target of ≥80% expert approval is kept only as one signal and must be reassessed after initial testing.

---

## 12. DEVELOPMENT PRINCIPLES

- Spec-Driven Development.
- Vertical Slice Delivery.
- Modular Monolith.
- API-First Design.
- Design Studio first, commercial application later.
- Expert-in-the-loop by design; expert feedback must be easy to give.
- Human-in-the-Loop AI.
- Model-Agnostic Architecture.
- Structured Expert Feedback with full provenance; originals and predictions never overwritten.
- Measurable improvements over architectural complexity; no premature fine-tuning.
- Privacy and ownership of expert data.
- Dataset Versioning.
- Internationalization by Design.
- Automated Testing.
- Incremental Delivery.

---

## 13. DEVELOPMENT ROADMAP

See §2 (delivery slices and status) and `ARCHITECTURE.md` §11 (technical scope per slice). The former milestones M1–M7 map to Slices 0–6 of v0.2; in v0.3 before/after documentation moves to Slice 7, and cross-project memory (Slice 5) and evaluation (Slice 6) come first.

---

**Document version:** 0.3 (2026-11-17: Design Studio strategy, ADR-0008)  
**Next document:** ARCHITECTURE.md