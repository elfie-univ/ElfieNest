# ADR-0008: Public documentation information architecture

- **Status:** accepted
- **Date:** 2026-08-12
- **Scope:** public documentation structure and lifecycle

## Context

The public site serves three different reader needs: understanding the world and
story, operating ElfieNest, and contributing to the system. Developer content
also has several different lifecycles: current architecture, cross-version
designs, normative contracts, temporary conformance gaps, durable decisions and
engineering guidance.

Without a protected information architecture, user instructions can drift into
Developer pages, engineering pages can accumulate at the Developer root, and
temporary governance records can be mistaken for permanent history. Navigation
alone describes presentation but does not protect ownership or bilingual parity.

## Decision

The public root is organized as Home, Story, User Guide and Developer Docs.
`getting-started/` is replaced by `user-guide/` because the section owns the
complete user manual rather than only first-run onboarding.

Developer content is organized directly into `architecture/`, optional
`designs/`, `contracts/`, `conformance/`, `decisions/` and `engineering/`.
No additional evolution, governance, current-version or archive wrapper is
introduced. The sidebar presents Current Architecture first, then Design &
Governance, then Engineering.

English and Simplified Chinese remain path mirrors. Empty placeholder sections
are not retained. Detailed Conformance records contain only current gaps and are
removed after full conformance; the index records the current conformant state
while permanent machine checks remain active.

The structure is versioned in a dedicated bilingual contract, summarized for
coding Agents in `docs/AGENTS.md`, registered in the Contract Registry and
checked by a focused architecture test plus the VitePress build.

## Consequences

Readers have one obvious place for usage instructions and one Developer model
for understanding the current system, its evolution and the engineering workflow.
Historical execution noise does not accumulate in the public site, while durable
Designs and ADRs remain traceable.

A later structural change requires a governance-only ADR and contract update.
Ordinary page edits inside an existing category remain lightweight and do not
need an ADR.

Rejected alternatives are keeping `getting-started/` as a permanent user-manual
name, leaving Developer pages flat, introducing deeper evolution/archive directory
trees, relying only on sidebar configuration, and archiving every completed
Conformance execution record.
