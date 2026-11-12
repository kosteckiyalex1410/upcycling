# AI FASHION UPCYCLING ASSISTANT
## Product Specification v0.2

**Status:** Draft  
**Stage:** Expert MVP  
**Documentation language:** English  
**Initial UI languages:** Ukrainian and English  
**Initial expert users:** 1  
**Development approach:** Spec-Driven Development + Vertical Slices

---

## 1. PRODUCT VISION

AI Fashion Upcycling Assistant is an AI-powered platform that helps transform existing garments into more desirable, functional, and aesthetically appealing products.

The platform analyzes garment photographs, identifies construction details, visual fabric characteristics, and visible defects, and recommends potential garment modifications.

The long-term objective is to develop specialized Fashion AI capabilities supported by proprietary expert-annotated datasets.

The initial product is an expert-facing application designed to collect high-quality human feedback while validating AI-generated transformation recommendations.

---

## 2. PRODUCT ROADMAP

### Phase 1 — Expert MVP

A mobile-first application for professional fashion designers.

Core capabilities:

- Garment photography and project creation.
- AI-powered garment analysis.
- Transformation recommendations.
- Interactive AI conversations.
- Recommendation approval and rejection.
- Voice-based expert feedback.
- Expert corrections.
- Custom transformation suggestions.
- Before/after documentation.
- Structured expert data collection.

### Phase 2 — Specialized Fashion AI

Develop and improve specialized capabilities for:

- Garment Understanding.
- Fabric and Texture Understanding.
- Garment Defect Detection.
- Transformation Recommendation and Ranking.

Introduce retrieval, task-specific models, and fine-tuning where supported and justified by evaluation results.

### Phase 3 — Consumer Application

Expand the platform into a consumer-facing mobile application.

Potential capabilities include garment transformation visualization, personalized recommendations, repair guidance, and wardrobe upcycling.

These capabilities require separate product validation.

---

## 3. TARGET USERS

### Initial User

One professional fashion designer.

The initial application must support a single expert without introducing unnecessary multi-user administration.

However, the architecture must allow future expansion to multiple experts.

### Future Users

- Fashion designers.
- Upcycling specialists.
- Tailors.
- Resellers.
- Consumers interested in clothing transformation.

---

## 4. PRIMARY USER JOURNEY

### Scenario: A Designer Visits a Secondhand Store

**Step 1 — Capture Garment**

The designer opens the application on an iPhone and creates a new garment project.

The designer captures multiple photographs:

- Front view.
- Back view.
- Construction details.
- Fabric close-ups.
- Visible defects.
- Labels, when available.

**Step 2 — AI Analysis**

The AI analyzes the available photographs and produces structured garment information.

The analysis may include:

- Garment category.
- Construction elements.
- Visible fabric characteristics.
- Potential defects.
- Uncertain attributes.

The AI may request additional photographs or expert clarification.

**Step 3 — Initial Recommendations**

The AI generates relevant transformation suggestions.

Each recommendation includes:

- Target garment element.
- Proposed modification.
- Expected aesthetic effect.
- Technical feasibility assessment.
- Potential risks.
- Explanation.

**Step 4 — Expert Evaluation**

The designer can:

- Approve a recommendation.
- Reject a recommendation.
- Record a voice comment.
- Correct garment attributes.
- Suggest an alternative transformation.

**Step 5 — Interactive AI Refinement**

After receiving feedback, the AI can reconsider previous recommendations and generate improved alternatives.

The system must preserve the full interaction history.

Expert feedback should influence the current conversation immediately without automatically modifying model weights.

**Step 6 — Save Project**

All photographs, AI outputs, expert decisions, and conversation history are persisted.

**Step 7 — Document Actual Transformation**

The designer can reopen a project and upload photographs of the modified garment.

The application associates the final result with the original garment and its transformation history.

---

## 5. INTERACTIVE AI REQUIREMENTS

### IA-01 — Context Preservation

The AI must maintain access to the current garment context throughout the interaction.

### IA-02 — Iterative Recommendations

The AI must generate updated recommendations based on expert feedback.

### IA-03 — Voice Interaction

The designer must be able to record voice feedback.

Audio is transcribed and provided to the AI as conversational context.

### IA-04 — Structured Feedback

The system must preserve:

- Original recommendation.
- Expert decision.
- Expert explanation.
- AI interpretation.
- Updated recommendation.

### IA-05 — Conversation History

All meaningful interaction turns must be persisted.

### IA-06 — Expert Corrections

Corrections must not overwrite the original AI predictions.

### IA-07 — Human Authority

Expert decisions must remain distinguishable from AI-generated suggestions.

The AI must not silently reinterpret a rejected recommendation as approved.

---

## 6. BEFORE/AFTER DOCUMENTATION

The application must allow designers to attach photographs of completed transformations.

Each transformation record should support:

- Original garment photographs.
- Selected transformation operations.
- Final garment photographs.
- Expert notes.
- Actual implementation status.
- Differences between proposed and completed modifications.

Before/after data may support future recommendation evaluation and specialized model training.

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

The platform must preserve:

- Original images and audio.
- AI predictions.
- Expert corrections.
- Recommendation approvals and rejections.
- Voice transcripts.
- Expert-authored recommendations.
- AI refinement history.
- Before/after photographs.
- Model and prompt versions.
- Annotation provenance.
- Dataset eligibility status.

Expert feedback must be stored separately from model predictions.

Data collection must support future supervised learning, retrieval, ranking, and evaluation.

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

## 11. MVP SUCCESS CRITERIA

The initial validation dataset will contain approximately 50 real garments.

Evaluation areas:

- Garment recognition quality.
- Construction feature recognition.
- Recommendation usefulness.
- Technical feasibility.
- Expert correction frequency.
- Interaction usability.
- Analysis latency.
- AI inference cost.

A preliminary target is at least 80% expert approval among evaluated recommendations.

This target must be reassessed after initial testing and must not replace separate monitoring of technically infeasible suggestions.

---

## 12. DEVELOPMENT PRINCIPLES

- Spec-Driven Development.
- Vertical Slice Delivery.
- Modular Monolith.
- API-First Design.
- Human-in-the-Loop AI.
- Model-Agnostic Architecture.
- Structured Expert Feedback.
- Dataset Versioning.
- Internationalization by Design.
- Automated Testing.
- Incremental Delivery.

---

## 13. FIRST DEVELOPMENT MILESTONES

**M1 — Architecture Foundation**

Repository structure, architecture documentation, development conventions, and API contracts.

**M2 — Garment Capture**

Mobile-first photography and garment project persistence.

**M3 — Garment Understanding**

AI-powered garment recognition and structured analysis.

**M4 — Transformation Recommendations**

Initial AI recommendations with explanations and feasibility considerations.

**M5 — Interactive Expert Feedback**

Approval, rejection, voice comments, and iterative AI refinement.

**M6 — Before/After Documentation**

Capture and persistence of completed transformations.

**M7 — Dataset Foundation**

Structured annotation export, dataset validation, and preparation for future ML training.

---

**Document version:** 0.2  
**Next document:** ARCHITECTURE.md