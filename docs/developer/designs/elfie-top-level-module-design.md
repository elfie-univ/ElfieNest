# Elfie top-level module design

> Status: accepted design<br>
> Confirmed: 2026-08-11<br>
> Nature: cross-version target-directory and module-ownership design; it does not
> claim that source migration is complete and is not the active contract<br>
> Not covered yet: inter-module protocols, event schemas, call ordering or a
> migration implementation plan

## 1. Purpose

This document designs the top-level directories, first-class modules, data
ownership and forbidden boundaries of one complete Elfie. It answers:

1. which top-level modules exist;
2. what each module owns;
3. which concepts must no longer be top-level modules;
4. how Genesis, Factory and the Elfie Facade differ;
5. which prerequisites apply to later source migration.

Communication events, input/output contracts, concurrency and error protocols
will be finalized after the related designs converge. Temporary interfaces must
not be mistaken for that later contract.

## 2. Target top-level layout

```text
elfie/
├── profile/              # immutable identity, virtual appearance and provenance
├── brain/                # persistent psychology, cognition, activity and autonomy
├── nervous_system/       # embodied perception, signals, reflexes and action adaptation
├── body/                 # virtual/physical bodies, sole authority and switching state
├── communication/        # digital contacts, channels, conversations, messages and receipts
├── genesis/              # one-time life-initialization rules and artifacts
├── elfie.py              # thin Facade for one complete Elfie
└── factory.py            # technical assembly and restoration of an existing Elfie
```

This is a responsibility map, not a file-by-file layout for each directory.

## 3. Five first-class runtime modules

### 3.1 Profile

Profile stores the intrinsic record that does not change after creation. It is a
first-class data module, not a continuously running loop.

```text
ElfieProfile
├── Identity
│   ├── elfie_id
│   ├── name
│   ├── species
│   ├── birth_at
│   ├── origin
│   └── other confirmed immutable identity facts
├── VirtualAppearance
│   ├── appearance_genome
│   ├── morphology
│   ├── proportions
│   ├── face / fur / coat
│   └── semantic appearance specifications consumable by Godot
└── Provenance
    ├── schema_version
    ├── generator_version
    ├── generation_seed
    └── stable creation-source information
```

Profile does not store current age; personality traits or interests; memories,
life events or relationships; self-understanding; emotion, energy or drives;
capability permissions; the active body; physical-toy facts; or current channels
and conversations.

Immutability alone is not sufficient for Profile ownership. A childhood event
still belongs to Memory, and a stable family relationship still belongs to
Relationship. Profile owns only intrinsic identity, virtual appearance and
creation provenance.

### 3.2 Brain

Brain owns the psychological state and cognition through which an Elfie changes,
learns and grows, including:

- Personality, Self Model and stable norms;
- Memory, Knowledge and Relationship;
- Emotion;
- Energy, Homeostasis and Circadian Rhythm;
- Motivation and Drive;
- Perception, Attention and the three event lanes;
- Cortex, Planner, Skills, Tools and scoped Workers;
- Executive and cross-turn Activities;
- Offline Cognition / Night Work;
- Capability Envelope, budgets and autonomous decisions;
- structured decisions, Activity triggers and execution-receipt feedback.

Genesis co-materializes Profile and the Brain-owned Selfhood state from one
validated creation bundle. Profile remains the immutable external dossier, but
ordinary Brain runtime does not read it as a context source. Selfhood's frozen
`identity_core` supplies Brain identity, while `adaptive_self` describes the
slow way the Elfie understands and expresses itself. The focused
[Selfhood design](./elfie-selfhood-and-fixed-model-header.md) supersedes earlier
runtime Profile-anchor interpretations.

### 3.3 Nervous System

Nervous System belongs only to the embodied lane. It owns sensor input from the
authoritative body, normalization and source preservation, deterministic
low-latency safety reflexes, physical feasibility constraints, adaptation of
high-level actions and true body execution receipts.

It does not handle digital chat, own personality or memory, or make open-ended
social decisions.

### 3.4 Body

Body owns two available body types and the sole embodiment authority:

- the Godot virtual body;
- the physical toy body;
- `selected_body`;
- `VIRTUAL_ACTIVE`;
- `SWITCHING_TO_PHYSICAL`;
- `PHYSICAL_ACTIVE`;
- `SWITCHING_TO_VIRTUAL`;
- switch transactions, generations, rollback and recovery;
- capabilities, connection state and action-execution state.

Virtual and physical bodies are mutually exclusive, with one action authority at
all times. `Headless` cannot be a third product body or normal life state; if it
exists, it is only a test or development substitute.

Body does not own the virtual appearance stored in Profile. It passes
VirtualAppearance to Godot; the physical toy's appearance is a device fact and
is not written into Profile.

### 3.5 Communication

Communication belongs only to the digital communication lane. It owns contact
and person-to-channel mapping, channel registration and reachability,
conversations, inbox/outbox state, message envelopes and attachments, replies
and proactive conversations, plus sending, failure, retry, deduplication,
timeout and receipts.

It does not control the body or own personality, memory or social judgment.
Brain decides whom to contact, why and what to express; Communication establishes
the real connection and delivers the message.

## 4. Genesis is creation, not a sixth runtime organ

`genesis/` owns domain rules for life initialization. It runs only during
adoption and no longer owns the data after creation.

```text
GenesisBundle
├── ProfileDraft
├── PersonalitySeed
├── MemorySeeds
├── RelationshipSeeds
├── SelfModelSeed
├── BiographyEnrichmentPlan
└── InitializationManifest
```

After consistency validation, ownership is committed as follows:

| Generated artifact | Final owner |
| --- | --- |
| Intrinsic identity, virtual appearance and provenance | Profile |
| Initial personality | Brain / Personality |
| At most five key pre-adoption events | Brain / Memory |
| Initial relationships | Brain / Relationship |
| Initial self-understanding | Brain / Self Model |
| Boundaries for later biographical enrichment | A temporary scoped Activity in Brain / Offline Cognition |
| Creation version, completion state and validation result | Initialization Manifest |

The generation model cannot freely invent the Capability Envelope, permissions,
real device capabilities, available channels, model/tool budgets, safety
boundaries or the true local Owner binding. Product configuration, real devices
and App use cases bind those deterministically.

### 4.1 Genesis and Night Work

Before the first awakening, Genesis must create the minimum complete person:
Profile, initial personality, a relationship skeleton, Self Model and no more
than five key historical events.

Genesis may create a temporary `BiographyEnrichmentPlan`. Early Night Work may
add sensory, emotional and associative detail only within its event roots,
people, facts, budget and expiry. Every addition first becomes a
`MemoryCandidate` and is committed only after Memory System review.

Night Work cannot modify Profile, add unlimited major history, invent new key
relationships or become a permanent background storyteller. The special
enrichment Activity ends when completed or expired.

## 5. Factory, Facade and Bootstrap

### 5.1 Factory

Factory assembles or restores an Elfie from existing data and injected external
dependencies. It does not generate a life story, own life state or reimplement
Brain, Body or Communication algorithms.

### 5.2 Elfie Facade

`elfie.py` is the thin Facade of one complete Elfie, not an independent system.
It ensures that internal modules share an `elfie_id`, exposes start/stop/recovery,
provides controlled entrances for body events, communication events and body
switching, delegates to the correct module, and prevents callers from assembling
an incomplete or identity-inconsistent Elfie.

The Facade does not schedule Activities, organize memory, decide response
content or implement the body-switching state machine.

### 5.3 Bootstrap / App Orchestration

Bootstrap injects dependencies and starts processes. App orchestration combines
Elfie, Nest, Godot/devices, model and tool infrastructure, communication
interfaces and persistence into the running product. These remain outside Elfie
and cannot become its personality or embodiment authority.

## 6. Concepts that are not top-level modules

| Concept | Target ownership |
| --- | --- |
| Entity Identity | Profile / Identity |
| Virtual Appearance | Profile / VirtualAppearance |
| Personality, Self, Memory, Emotion, Energy | Brain |
| Skills, Planner, Tool Loop, Worker | Brain / Cortex; execution infrastructure is injected |
| Activity, Activity triggers and Night Work | Brain |
| Embodiment Authority | Body |
| Lifecycle System | Not created; retain the thin Elfie Facade |
| Profile Page | Product-layer aggregate view, not a new data owner |
| Godot World, Nest, model/tool infrastructure, Persistence | Outside Elfie |

## 7. Explicitly out of scope for this design stage

1. migrating current source directories;
2. moving current implementations such as `skills/`, `initialization.py` or
   `cognitive_runtime.py`;
3. changing Profile schemas or persisted data;
4. defining communication payloads, event types or protocol versions;
5. adding compatibility layers for temporary adaptation;
6. presenting target design as already implemented architecture;
7. starting product migration under this design alone.

## 8. Gates for later migration

After the related communication design is accepted:

1. synchronize the facts of current code;
2. combine those facts with this ownership design to finalize communication and
   interaction contracts;
3. audit callers, data owners and persistence entrances against the target;
4. create staged migration slices for directories, callers and development-data
   rebuilds;
5. define acceptance evidence for every stage before changing source.

Communication contracts may add interfaces but cannot silently reverse these
first-class ownership decisions. A real conflict requires an explicit design
revision before implementation changes responsibilities.

## 9. Fixed conclusions

1. Runtime first-class modules are Profile, Brain, Nervous System, Body and
   Communication.
2. Profile owns immutable identity, virtual appearance and provenance.
3. Brain owns growing psychology, selfhood, personality, memory, relationships
   and cognition.
4. Body owns the mutually exclusive virtual/physical Embodiment Authority.
5. Genesis is a one-time cross-module creation flow, not a permanent life organ.
6. Factory assembles and the Elfie Facade is a thin external boundary; neither
   schedules domain behavior.
7. Skills, Activities, Night Work and autonomy governance belong to Brain.
8. This stage fixes directory and ownership design without prematurely fixing
   communication protocols or authorizing source migration.
