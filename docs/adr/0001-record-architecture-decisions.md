# ADR-0001: Record architecture decisions

- **Status:** accepted
- **Date:** 2026-11-12
- **Deciders:** product owner, Claude Code (author)

## Context and problem

`ARCHITECTURE.md` §12 lists open decisions (hosting, identity, AI providers, offline, retention, taxonomy) that must not be resolved silently. Durable choices need a reviewable, dated record that explains why they were made.

## Considered options

1. Lightweight Markdown ADRs in `docs/adr/` (Nygard-style), versioned with the code.
2. Decisions recorded only in `ARCHITECTURE.md`.
3. External wiki.

## Decision

Option 1. Every decision that changes a durable system boundary or commits to an external provider gets an ADR using [`0000-template.md`](0000-template.md). ADRs are numbered sequentially, never rewritten after acceptance except for status changes; a changed decision is a new ADR that supersedes the old one. `ARCHITECTURE.md` summarizes the current state and links to ADRs.

## Consequences

- Decisions are reviewable in the same PR as the code that implements them.
- Small overhead per decision.
- **Reversibility:** trivial.

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | accepted |
| [0002](0002-repository-layout-and-toolchain.md) | Repository layout and toolchain | accepted |
| [0003](0003-authentication-email-magic-link.md) | Authentication: email magic link with server-side sessions | accepted |
| [0004](0004-api-contract-and-client-generation.md) | API contract conventions and TypeScript client generation | accepted |
| [0005](0005-same-origin-deployment-topology.md) | Same-origin deployment topology | accepted |
