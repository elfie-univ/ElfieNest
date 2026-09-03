# ADR-0034: Preserve legacy contract version headers during governance cutover

**Status:** Accepted
**Date:** 2026-09-02
**Scope:** governance contract-version extraction and immutable-base change checks

## Context

The governance checker already requires a version bump in both language mirrors
when a contract changes. Older contracts on `main`, however, use the historical
`Status: normative, version N` header (and its Chinese equivalent), while newer
contracts use the canonical bold `Contract version` header. The immutable-base
checker reads the candidate with the old main implementation. When a valid
candidate updates one of those older contracts, the checker cannot extract the
base version and rejects the change before it can compare the versions.

## Decision

`scripts/governance/change_policy.py` accepts both the canonical bilingual
version header and the historical bilingual header. This changes only parsing
compatibility; the checker still requires a changed English/Chinese pair, a
version bump, and the matching ADR. Newly authored contracts continue to use
the canonical bold header.

The architecture governance test suite covers both header forms. No product
module, contract authority, or second source of contract content is introduced.

## Consequences

The immutable-base gate can judge a contract migration while `main` still
contains a legacy header. The repository can normalize remaining legacy headers
incrementally without weakening the governance rule or requiring a temporary
checker bypass.
