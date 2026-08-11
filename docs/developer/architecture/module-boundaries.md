# Module boundaries

> This page describes the currently operating boundaries. Normative target
> rules live in the [System](../contracts/system) and
> [Application](../contracts/application) contracts; known deviations are
> tracked in the [conformance registers](../conformance/).

## Root module responsibilities

| Module | Responsible for | Not responsible for |
| --- | --- | --- |
| `elfie/` | Individual profile, brain, body, nervous system, communication and skills | Accounts, Nest, Runtime lifecycle |
| `nest/` | In-nest semantic state, environment time and interaction propagation | Creating or holding `ElfieIndividual`, house geometry or authority hosting |
| `infrastructure/godot/gateway/` | Authenticated Python-side Godot transport, protocol frames, sessions and bundle inspection | Nest world semantics, product authorization or process lifecycle |
| `app/orchestration/lifecycle/` | Runtime lifecycle, full health, owner leases and authority start/stop | Product UI, account rules and raw scene facts |
| `infrastructure/godot/lifecycle/` and `artifacts/` | Authority-host selection, artifact metadata, validation and exported Runtime launch | Nest business state, scene editing or product routing |
| `app/interfaces/desktop/` | Electron observer windows, platform integration and public lifecycle client | Supervisor, Gateway internals, authority credentials and product rules |
| `app/` | Product use-cases, interfaces, infrastructure and cross-module orchestration | Replacing the internal state of domain modules |
| `ai_runtime/` | Providers, models, policy, tools, safety and inference | Account and Nest business rules |
| `godot_project/` | Houses, coordinates, motion, collision, characters and rendering source | Python-side business state or Runtime lifecycle |
| `devtools/` | Isolated development and debugging entry points | End-user product navigation |

## Composition, authority and observation

Real Elfies and the Nest are composed only in
`app/orchestration/NestSession`. `app/orchestration/lifecycle` is the sole
authority for starting, stopping or restarting the Core, Gateway and selected
Godot authority. The Gateway carries high-level semantic commands to Godot and
returns physical facts that occurred; Python does not recreate navigation,
collision, coordinates or rendering.

An Observer is a product-facing, authenticated semantic projection. It may read
only its authorized room or owned Elfie scope and send only the closed
high-level intents documented in [Runtime & data](./runtime). It
is not a second authority or a pass-through for Godot protocol frames.

## Dependency direction

```text
app/bootstrap → app/orchestration → elfie / nest / ai_runtime
app/orchestration → infrastructure/godot/gateway → exported Godot authority
app/orchestration/lifecycle → infrastructure/godot/lifecycle → exported Godot authority
app/interfaces/desktop → public lifecycle CLI and authenticated Observer surface
app/interfaces → app/features
app/infrastructure → Feature / Orchestration Ports
app/bootstrap → interfaces + features + orchestration + infrastructure
```

Lower-level modules do not reverse-depend on `app.interfaces`. Interfaces,
Features and Infrastructure may use only the public Observer/Gateway read
surfaces; they cannot construct an authority host or send raw Runtime frames.
Features never import concrete Infrastructure; runtime calls reach adapters
only through injected consumer-owned Ports. The normative details are in the
[Application architecture contract](../contracts/application).
Any cross-boundary change must update the architecture tests and corresponding
English and Simplified-Chinese documentation in lockstep.
