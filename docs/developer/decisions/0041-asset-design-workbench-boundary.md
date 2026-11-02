# ADR-0041: Isolate the asset design workbench and its saved assets

**Status:** Accepted
**Date:** 2026-10-22
**Scope:** Developer Tools asset design preview and asset workspace storage

## Context

House, room, terrace and furniture review needs a stable local surface that can
show the saved asset library without becoming a second product runtime. The
workbench also needs a durable boundary between editable source inputs,
published revisions and unregistered working material. A loose directory scan
or a second preview page would make it unclear which files are authoritative
and could make asset review depend on production or Godot state.

## Decision

The Developer Tools `/assets/design` route and its existing viewer are the one
asset preview surface. The workbench does not create a parallel viewer, start a
temporary model website, or own Elfie, Nest or Godot runtime lifecycle.

The portable design workspace is rooted at `devtools/asset_design/assets/`.
`catalog.json` is the loading projection, while each owned object keeps its
public metadata in `object.json` and each published revision keeps its file
registration and details in that revision's `version.json`. Source inputs,
published snapshots and reference images remain in their prescribed object
directories. Files are included in the preview only through explicit catalog
registration; directory scanning cannot silently promote a working file.

Asset workbench rules are maintained in the root and scoped `AGENTS.md` files.
This ADR records the durable boundary; the current scoped rules remain the
executable instructions for contributors.

## Consequences

The page can be reopened from a portable asset workspace without loading
production data or a second runtime. A new or edited GLB must be explicitly
registered before it can affect the page, and old or unregistered working
material remains local until it is reviewed. The catalog, object metadata and
revision metadata have one clear ownership path, which makes omission audits
and workspace relocation reproducible.

## Saved catalog ownership clarification — 2026-11-02

The scoped workbench rule follows the existing storage ownership above:
`catalog.json` contains object indexes and global image associations; each
`object.json` contains public metadata and its revision list; each revision's
`version.json` is the sole registration and detail record for that revision.
`catalog_store` owns the common read/write path. The loading projection must not
duplicate revision records or discover unregistered revisions by scanning.
This clarifies the scoped rule without changing the preview surface or runtime
authority.
