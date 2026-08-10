# ADR-0001: Lightweight Ports and Adapters for App

- **Status:** accepted
- **Date:** 2026-08-10
- **Scope:** `app/`

## Context

Repeated feature work left Interfaces constructing repositories, Features
depending on persistence details and composition spread across entry points.
The project needs stable ownership and testable boundaries without introducing
microservice or dependency-injection ceremony.

## Decision

App adopts a lightweight Ports-and-Adapters structure:

- Feature remains the concrete product-use-case implementation; it is not an
  interface-only layer.
- The consumer Feature or Orchestration domain owns the smallest Port needed
  for an external fact or side effect.
- Infrastructure implements Ports and owns technical records and adapters.
- Bootstrap is the only place that constructs and injects concrete adapters.
- Interface DTOs, Feature models, Port models and persistence records have
  separate owners and do not cross boundaries implicitly.
- Small domains may use cohesive `models.py` and `ports.py`; large domains may
  split cohesive packages. There is no repository-wide giant model file and no
  requirement for one file per model.
- Infrastructure is organized by technical capability and need not mirror every
  Feature directory.

## Consequences

Existing code is migrated one business domain at a time under an exact
conformance baseline. The structure adds explicit mapping at boundaries, but it
removes hidden framework/storage coupling and makes use-cases independently
testable. Device transport remains Infrastructure; workflows combining a real
Elfie, Nest and external body remain Orchestration.

Alternatives rejected for now are the current direct dependency structure, a
Port for every helper, a global generic repository, a DI framework, full CQRS,
Event Sourcing and microservices.
