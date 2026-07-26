# Module boundaries

## Root module responsibilities

| Module | Responsible for | Not responsible for |
| --- | --- | --- |
| `elfie/` | Individual profile, brain, body, nervous system, communication and skills | Accounts, Nest, desktop lifecycle |
| `nest/` | In-nest state, environment time, interaction propagation, Godot semantic protocol | Creating or holding `ElfieIndividual`, house geometry |
| `app/` | Product use-cases, interfaces, infrastructure, cross-module orchestration | Replacing the internal state of domain modules |
| `ai_runtime/` | Providers, models, policy, tools, safety and inference | Account and Nest business rules |
| `desktop/` | Electron windows, platform resources and process supervision | Elfie cognition, adoption and chat rules |
| `godot_project/` | Houses, coordinates, motion, collision, characters and rendering | Python-side business state |
| `devtools/` | Isolated development and debugging entry points | End-user product navigation |

## The single composition point

Real Elfies and the Nest are composed only in
`app/orchestration/NestSession`. This keeps `Nest` pure in-nest semantics,
lets `Elfie` be tested as an independent individual, and lets the application
layer assemble them into a product session.

## Dependency direction

```text
app/bootstrap → app/orchestration → elfie / nest / ai_runtime
app/interfaces → app/features → app/infrastructure
desktop → Python Core / Godot Web Runtime
```

Lower-level modules do not reverse-depend on `app.interfaces`; any cross-boundary
change must update the architecture tests and the corresponding READMEs in
lockstep.
