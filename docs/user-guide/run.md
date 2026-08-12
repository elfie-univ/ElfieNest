# Run your first Nest

## Minimal run

From the repository root:

```bash
.venv/bin/python main.py
```

This entry prepares a minimal Nest, advances three environment ticks, walks an
Elfie through one perception → decision → output flow, and then proactively
shuts down the local service.

## What you will see

The run pipeline includes:

1. The Nest advances environment time;
2. Body and communication events enter the perceptual workspace;
3. The `BrainCoordinator` organizes one cognitive turn;
4. The `OutputRouter` routes the `DecisionPlan` to body, communication or
   internal effectors;
5. Execution receipts flow back into the next round of perception.

## Common entry points

```bash
./elfienest.sh serve --fallback
./elfienest.sh status
./elfienest.sh stop
```

For the full command set and Developer Tools see
[Commands & dev tools](/developer/engineering/tooling).
