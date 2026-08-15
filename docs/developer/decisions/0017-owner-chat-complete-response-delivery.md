# ADR-0017: Owner chat uses complete-response delivery

- **Status:** Accepted
- **Date:** 2026-08-15
- **Scope:** Model/Food/tool behavior contract and owner chat delivery

## Context

The chat path was experimentally changed to provider streaming so that the Web
client could render partial text before the model returned. Controlled local
tests and five paired calls against the configured remote Volcengine model did
not show a material latency improvement. The observed differences were within
network and provider variation, while a streaming request adds a separate HTTP
transport, SSE parsing and transient UI delivery path.

The experiment also created a second realtime message shape beside the existing
persisted conversation message. That extra path does not improve model
generation, structured-output work or the number of model calls.

## Decision

Owner chat uses complete-response delivery:

- one ordinary model request produces one complete response;
- the completed Elfie reply is persisted once;
- the authorized Web client receives one normal message event;
- transient message_delta events and stream-specific identifiers are not part
  of the current chat protocol.

Structured JSON and tool-call generations continue to wait for their complete
result. Latency observations may still record first-token and total timings as
model evidence, but observations do not change the product delivery contract.

Provider streaming is not a default performance optimization. A future
streaming proposal requires a new contract revision and a controlled benchmark
that demonstrates a material user-visible benefit without weakening structured
output, persistence, authorization or UI privacy boundaries.

## Consequences

The experimental streaming implementation and its transient chat protocol are
removed. The Web client renders the persisted complete reply and does not need
stream buffers or reconciliation between partial and final messages.

Actual speed work remains focused on model request cost: context and prompt
size, serial model calls, model selection and reusable provider connections.
The rollback does not change the existing complete-response chat behavior or
the structured model contract.
