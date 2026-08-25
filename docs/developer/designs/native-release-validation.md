# Native release validation and installed product journey

> Status: phases 0–2, the duplicate-start recovery check, the minimum installed
> Viewer readiness marker, evidence binding and the soak trend classifier are
> implemented locally. Native host, full UI, real upgrade and long-window evidence is still required; this page does not claim
> that every gate below exists or has passed. Current gaps are tracked in the
> [service lifecycle conformance register](../conformance/service-lifecycle.md#native-release-acceptance-queue).

## 1. Goal and release claim

ElfieNest has one shared product core and four native release targets:

- `darwin-arm64`;
- `darwin-x64`;
- `win32-x64`;
- `linux-x64`.

A source test, successful package build, or `WORLD_READY` state proves only its
own boundary. A release candidate is accepted only when evidence covers both:

1. **native package and lifecycle integrity** — install, launch, process
   ownership, stop, reinstall, uninstall, and platform integration; and
2. **installed product continuity** — first-run Setup, model configuration,
   adoption, chat, persistence, restart, and real upgrade.

The target first-user path is:

```text
native install
  -> first-run Setup
  -> deterministic model configuration
  -> Owner login
  -> adopt one Elfie
  -> receive one Brain-backed chat reply
  -> restart with the same data home
  -> recover Setup, Elfie, Nest and conversation state
```

No individual test layer may be presented as proof of the whole path.

## 2. Six validation layers

| Layer | Question answered | Required ElfieNest evidence | Current position |
| --- | --- | --- | --- |
| Unit | Is one function or class correct? | Parsing, validation, state transitions, path rules and platform adapters. | Existing coverage; keep focused and deterministic. |
| Integration | Do collaborating modules obey their contracts? | Core, SQLite, Gateway, Godot protocol, Setup, Provider, adoption and chat boundaries. | Existing coverage, including source-level Setup/adoption and Brain/chat slices. |
| Native install smoke | Is the packaged product fundamentally alive? | Install, installed Controller start, `WORLD_READY`, Controller/Core/Godot PIDs, bounded stop, zero recorded residue, reinstall and uninstall. | Implemented locally for four targets; native-runner evidence is still required. |
| Installed product journey | Can a new user complete the supported core path? | Setup, model connection, one adoption, one reply, persisted history and restart recovery through the installed package. | Driver and native-smoke wiring implemented; clean native evidence remains external. |
| Real upgrade | Does user state survive a version transition? | Install previous release, seed supported state, install candidate, recover and continue the journey. | Same-version reinstall exists; previous-version-to-candidate proof is missing. |
| Soak | Does the installed system remain stable over elapsed time? | PID/generation continuity, CPU/RSS/handle or FD trends, component health, error/crash deltas and recovery. | Redacted trend classifier implemented; target-host observation remains external. |

The six layers form a release system only when their evidence is bound to the
same candidate SHA and exact package hashes. They do not remove the need for a
small amount of real desktop acceptance.

Compatibility, resilience, security and evidence identity are cross-cutting
release dimensions, not substitutes for one of the six layers. In particular,
the native gate must also prove the supported-host matrix, installer receipts
and shell integration, lifecycle races and recovery, secret-safe diagnostics,
and one immutable evidence chain from source SHA to published package.

## 3. Deterministic model boundary for CI

### 3.1 Decision

Installed product acceptance must not inject an in-process fake model adapter
into the packaged Core. That would bypass Provider persistence, endpoint
selection, HTTP serialization, capability projection and the release wiring we
need to prove.

Instead, CI starts a repository-owned **scripted protocol model server** on an
ephemeral loopback port. The installed application configures it through the
same versioned Provider and Food surfaces used by a user:

```text
installed ElfieNest
  -> persisted Provider/Food configuration
  -> production model HTTP adapter
  -> 127.0.0.1 scripted model server
  -> schema-valid deterministic response
```

The server is a test double for the remote model boundary, not a second product
model implementation. It is launched and owned only by the test job, asks the
OS to allocate port `0`, binds only to loopback, performs no internet request,
and is never packaged into ElfieNest. If the production Provider contract
requires a credential, the journey stores a fixed synthetic test credential
through the real secret boundary; it is not a real external secret and still
must be redacted from all evidence.

### 3.2 Scripted responses

The server routes by the real protocol request and declared schema, not by a
loose call counter alone. Its minimum scenarios are:

| Request | Deterministic response | Acceptance assertion |
| --- | --- | --- |
| Provider inventory/probe | Protocol-correct model inventory, text probe and structured-capability responses for one qualified model. | The connection, exact endpoint model, Common Food and Emergency Food become executable through persisted projections. |
| `adoption_candidate_reveal_v1` | A valid `original_name`, distinct `suggested_name`, and first-person `personal_story` within production limits. | At least one invited candidate completes the real reveal and admission path. |
| Owner chat | A non-empty first-person Elfie complete response. | The request crosses WebSocket, App, NestSession, Brain and the production model adapter without silently enabling Provider streaming. |
| Unexpected schema, tool or endpoint | Explicit test-server failure. | New model behavior cannot silently receive a generic success response. |

Adoption candidate genetics and acceptance selection remain owned by production
code. The scripted server supplies only the qualified model output required by
the post-acceptance identity reveal and chat. A missing server, rejected
capability, invalid JSON, unexpected request or fallback attempt fails the gate;
the journey is never skipped because a model is absent.

The server records only request kind, schema name, model ID, duration, response
class and pass/fail count. It must not retain prompts, cookies, credentials or
conversation content in uploaded evidence.

The harness owns the server PID and actual bound port, waits for its readiness,
and proves it exits on success and failure. The journey must reach the model
aggregate required by the product contract, including executable Common and
Emergency routes; merely creating a Provider row is not readiness.

### 3.3 What this proves and does not prove

This design proves model configuration, capability selection, request/response
transport, structured parsing, adoption and chat composition without provider
variance. It does not prove the quality, billing state, quota or current
availability of a real cloud provider.

One separately scheduled, non-PR **real-provider canary** may detect day-to-day
reachability with a minimal bounded request. It uses protected secrets, never
runs for forked pull requests, records no secret or prompt, and is reported
independently from deterministic release acceptance. It does not replace the
representative real-provider capability matrix required for each release by
PMA-002. A provider outage must not make package integrity appear broken.

## 4. Installed product journey

Each native target runs the same API-level journey against a fresh temporary
`ELFIE_HOME` and the installed executable, never `scripts/serve.py` or an
in-process `TestClient`. The installed child starts from a neutral directory
outside the checkout with source-oriented environment variables removed. Its
executable, cwd, manifest source revision and resource root must all identify
the installed package. At least one rotating case per OS uses a data-home path
containing whitespace and non-ASCII characters.

1. Install the exact candidate package and verify its OS receipt/registration,
   installed version, manifest, source revision, launchers and package-owned
   shell integration.
2. Start the installed Desktop Controller and require `WORLD_READY` with
   Controller, Core and Godot authority PIDs.
3. Read Setup status and require `need_setup=true`; use the issued Setup cookie
   and CSRF token rather than bypassing first-run authentication.
4. Complete Owner, default no-download model choice and default Nest drafts;
   confirm installation and require Setup completion.
5. Log in as Owner and configure the loopback scripted Provider, synthetic
   credential, exact endpoint model, Common Food and Emergency Food through
   production APIs.
6. Require the model capability projection needed by adoption and chat and the
   expected aggregate model state; assert no bundled default was copied into the
   user configuration root and no source checkout supplied a missing resource.
7. Create one candidate set, invite candidates, select an accepted reveal and
   admit one Elfie.
8. Require the Elfie in the member list and in the running Nest/Runtime
   projection.
9. Open the authenticated production chat WebSocket, send one message, receive
   one non-empty complete Elfie reply, require both messages in persisted
   history, and retain only the non-secret Provider/model/role execution receipt.
10. Record non-secret stable identifiers, stop normally, and prove all recorded
    owned processes have exited.
11. Restart with the same data home; require `need_setup=false`, successful
    login, the same Elfie, the same history and one further successful reply.
12. Uninstall the application; require the OS package receipt/registration,
    package-owned files, shortcuts, desktop entries, launchers and PATH mutation
    to be gone while the selected user data home remains.
13. Stop the scripted model server and prove no test-owned process remains.
    After preservation has been asserted and evidence redacted, the harness may
    remove only its own temporary data root.

The journey uses one Owner, one Elfie and two chat turns. User administration,
the three-Elfie limit, exhaustive Setup alternatives, provider benchmarking and
the complete UI suite remain in focused tests; repeating them here would add
time without improving package-composition evidence.

## 5. Platform coverage

Shared behavior is tested once at full functional depth. Native differences are
tested on every target whose packaging, process, IPC, path or installer behavior
can change the result.

Before native acceptance starts, the release scope names exact supported OS
versions and, for Linux, exact DEB distributions and desktop sessions. Phase 0
freezes the first internal-beta matrix below; it defines validation scope and
does not silently expand a public support promise:

| target | pinned CI image | OS/session | named manual sample |
| --- | --- | --- | --- |
| `darwin-arm64` | `macos-14` | macOS 14 arm64 | macOS 14.8.x arm64 |
| `darwin-x64` | `macos-15-intel` | macOS 15 x64 | macOS 14.8.x x64 (if retained as a support sample) |
| `win32-x64` | `windows-2025` | Windows Server 2025 runner; Windows 11 x64 user sample listed separately | Windows 11 x64 |
| `linux-x64` | `ubuntu-24.04` | Ubuntu 24.04 x64, Xvfb; displayless Dedicated | Ubuntu 24.04 GNOME/X11 or another named session |

Workflow evidence must record the resolved runner image version, architecture,
OS build and desktop/session. A runner label ending in `-latest` is not a
support policy; targets outside the matrix are reported as uncovered, not
supported.

| Validation | macOS arm64 | macOS x64 | Windows x64 | Linux x64 | Reason |
| --- | --- | --- | --- | --- | --- |
| Shared unit/integration/full product suite | — | — | — | Full reference run | Product logic is shared; affected focused tests still run normally. |
| Package contents and native install smoke | Required | Required | Required | Required | Installer format, paths, permissions and authority hosting differ. |
| Receipt, launcher, shortcut/PATH and native uninstall footprint | Required | Required | Required | Required | Silent installation success alone does not prove OS integration or cleanup. |
| Installed API product journey and restart | Required | Required | Required | Required | Data roots, permissions, IPC and packaged resources are target-sensitive. |
| Full Setup -> adoption -> chat UI journey | — | — | — | Required under Xvfb | React behavior is shared; one complete browser path is sufficient. |
| Minimal installed Viewer check | Required | Required | Required | Required | Proves native activation, the management ready marker, no fatal console/crash event, and the platform-rendered Observer surface. |
| Tray, activation, close and single instance | Manual sample | Manual sample | Manual sample | Manual sample | Shell integration is not represented reliably by headless sessions. |
| Interactive installer and OS launcher path | Manual sample | Manual sample | Manual sample | Manual sample | Silent CI does not cover PKG/NSIS/package-manager presentation and Launchpad/Start Menu/application-menu launch. |
| Previous release -> candidate upgrade | Required | Required | Required | Required | Installer replacement and user paths are native. |
| Real-provider canary | — | — | — | One scheduled reference run | Provider behavior is not OS-specific. |
| Long soak | One macOS architecture | — | Required | Required | One architecture per OS covers long lifecycle behavior; both macOS architectures remain smoke-gated. |
| Signing, notarization and downloaded-origin launch | Required when public | Required when public | Required when public | Repository/package signing policy | Requires final signed artifacts and real OS trust surfaces. |

Linux needs two World-authority cases: graphical Electron authority under Xvfb
and Dedicated headless authority without a display. A file-presence check does
not replace a real Dedicated startup and shutdown.

## 6. Native lifecycle resilience matrix

The ordinary installed journey proves the happy path. A separate disposable-
host matrix protects the negative and recovery behavior required by the service
lifecycle contract. It never targets a maintainer's normal installation.

| Scenario | Required result | Minimum native coverage |
| --- | --- | --- |
| App plus concurrent installed CLI start; second App activation | One Controller and generation; target escalation or activation attaches without duplicate Core/Godot. | Every OS |
| Stop during startup; start during shutdown; bounded restart | Serialized result, typed cancellation/`BUSY_STOPPING`, no overlapping generations and zero owned residue. | Windows and one POSIX target, with focused adapters on all targets |
| Godot authority exits unexpectedly | Core remains truthful at `CORE_READY`; authenticated recovery reaches a new valid World generation within budget without a loop. | Every OS authority mode, including Linux Dedicated |
| Core exits unexpectedly | Controller records the failure and performs only bounded recovery; no duplicate Controller/Core and no false `WORLD_READY`. | Every OS |
| Renderer/Viewer process fails | Server and World remain owned; crash evidence is recorded and Viewer can be activated again. | Every desktop OS |
| Scripted model endpoint disappears and returns | Backend remains independent, model health and chat failure are typed, and later recovery succeeds without network-setting changes. | One shared reference plus native short-soak rotation |
| Stale receipt, PID reuse, unrelated occupied port and incompatible live version | Never signal or attach to the unrelated process; return the contracted typed result. | Focused permanent tests plus Windows and POSIX native samples |
| Missing/corrupt installed resource | Installed preflight fails with repair/reinstall guidance and never falls back to the checkout. | Every package layout; one native execution per OS |
| Candidate install/update while the old Controller runs | Detect the exact running Controller, require bounded convergence to `OFFLINE`, and refuse overwrite when it cannot stop. | Every OS installer |
| Failure-path harness cleanup | Package, test server, temporary credentials and test-owned processes are cleaned without touching unrelated processes or user data. | Every native job |

Fault injection is limited to exact test-owned PIDs and disposable data homes.
No scenario changes VPN, proxy, DNS, hosts, routes, firewall, TUN, PAC or another
network service.

## 7. Real upgrade acceptance

Same-version reinstall remains a useful idempotency smoke but is not called an
upgrade test. Real upgrade acceptance uses two immutable artifacts:

```text
install previous supported release
  -> complete Setup with the scripted Provider
  -> adopt one Elfie and persist chat
  -> first attempt candidate update while the old Controller is running
  -> require safe refusal or bounded stop handoff
  -> stop cleanly when required by the installer contract
  -> install exact candidate package
  -> require version change
  -> recover Owner, Provider/Food, Nest, Elfie and history
  -> send one new message
  -> uninstall without deleting user data
```

The previous artifact, candidate artifact, tag/SHA, package hashes and data
fixture version are recorded. A generated source fixture cannot replace a real
previous installer. Until a prior public version is supported, the first
internal baseline package is retained explicitly for this gate.

The gate also proves that Provider credential references remain usable without
exposing their values and that bundled defaults are replaced while user
configuration is preserved. Downgrade compatibility and rollback across a
schema-breaking public release are not implied; they require a separately
approved product contract when such compatibility is promised.

## 8. Soak and recovery acceptance

### 8.1 Short scheduled soak

A scheduled standard-runner check may run a representative installed journey
for 30–60 minutes and sample every five minutes:

- Controller/Core/Godot authority PID and generation;
- state, reached target, failures and component health;
- CPU, RSS, peak RSS, thread and process counts;
- Windows handle count or POSIX open FD count;
- model requests, chat progress and deterministic reply completion;
- error/fatal, abnormal exit and automatic recovery deltas;
- new relevant crash reports; and
- log, crash-dump, database and total data-home size trends.

The workload is fixed and bounded: periodic status, a low-rate deterministic
chat turn, Viewer activate/close where supported, and one controlled restart.
Thresholds compare trends and discontinuities rather than one transient CPU
sample. Phase 0 freezes the initial budgets: a five-minute warm-up; a 30-minute
short soak with five-minute samples; no more than 120 seconds for one recovery;
zero unexplained restarts (one pre-declared controlled restart is allowed);
installed process-tree idle CPU p95 at or below 25% and active-window p95 at or
below 100%; no more than 15% peak-RSS growth after warm-up; no more than 20%
growth in total POSIX FDs/Windows handles; and no more than 25 MiB of
diagnostic-log growth per 24 hours. The 24-hour host soak uses the same budgets
and additionally requires data-root growth to be explained by the fixed fixture.
Any budget breach, unexplained generation change, authority loss, or fatal/error
increment keeps the NAT row open. An observation with no frozen budget is
characterization evidence, not a passing release gate.

### 8.2 Long target-host soak

A 24-hour observation is not one GitHub-hosted job: GitHub-hosted jobs have a
[six-hour execution limit](https://docs.github.com/en/actions/reference/limits).
Long acceptance runs on maintained self-hosted or target test machines, while
GitHub schedules segments and collects redacted summaries. It never changes
VPN, proxy, DNS, firewall, routes or other network services.

Two lanes remain distinct:

- **passive field observation** is strictly read-only and only samples an
  already installed user session; and
- **active test-host soak** uses a disposable data home and scripted Provider,
  may create bounded chat traffic and execute the declared recovery matrix.

Evidence from one lane never silently claims coverage of the other. Each desktop
OS also receives one recorded sleep/wake or session-lock recovery sample on a
test host when that behavior is in the supported scope.

An unexplained PID or generation change, sustained resource trend, authority
loss, Core unhealthiness, growing fatal/error count or installed-app crash keeps
the relevant conformance row open. Expected restarts are marked before the
action and must recover within the agreed budget.

## 9. CI cadence and release gates

| Trigger | Selected validation | Publication |
| --- | --- | --- |
| Ordinary pull request | Focused unit/integration and affected shared lanes. | None. |
| Release-sensitive pull request | Four-target package build, install smoke and installed product journey; one shared UI journey. | None; exact-SHA evidence only. |
| Main post-submit/nightly | Missing full backstop lanes, short soak, Linux Dedicated path and rotating recovery scenarios. | None. |
| Manual candidate, no tag | Full four-target acceptance and retained review artifacts. | None. |
| Pre-tag/final candidate | Full matrix, real upgrade, required soak summaries, manual OS checklist and signing gates in public scope. | Only after all blocking rows close. |
| Tag push | Reuse or rerun evidence bound to the tag SHA and publish only exact verified artifacts plus checksums. | GitHub Release. |

Release-sensitive routing includes installer configuration, release scripts,
Desktop entrypoints, lifecycle/process/IPC code, packaged resources, Setup,
Provider/Food configuration, adoption, chat persistence, Godot runtime exports,
schema/storage contracts and the validation harness itself. Unknown executable
impact fails closed to the complete native lane.

Native jobs use frozen runner-image labels for the accepted matrix rather than
floating `-latest` labels. A final aggregation job downloads the four versioned
JSON summaries, validates their schemas, target uniqueness, candidate SHA,
package SHA-256 and result, and only then permits publication. Job success by
itself is not the release evidence.

## 10. Evidence, security and storage

Every gate emits a small redacted JSON summary containing candidate SHA,
package SHA-256, target, test version, pinned runner image/OS build, phase durations, stable states, PID and
generation changes, resource aggregates, request classes and final result.
Failure artifacts may add bounded log tails, screenshots and crash metadata.
Tokens, cookies, Provider credentials, writer credentials, prompts and user
content are never uploaded.

The evidence schema is versioned and independently validated. Redaction tests
inject known sentinel credentials, authorization headers, cookies and prompt
content and prove none appear in summaries, log tails, screenshots, filenames
or uploaded artifact metadata. Passing and failure paths both run cleanup and
evidence validation.

Cost and retention rules:

- public repositories use only standard GitHub-hosted runners for normal native
  gates; larger runners require explicit cost approval;
- build and test stay in one native job when possible, so PR installers do not
  need artifact transfer;
- successful PRs retain only small JSON summaries for seven days;
- failure diagnostics retain bounded artifacts for seven days;
- full installers are retained as Actions artifacts only for manual candidates,
  normally for three to seven days;
- published installers live in the GitHub Release rather than being duplicated
  as long-retained Actions artifacts;
- caches use scoped keys and the repository cache limit; installers and user
  data are never cached;
- obsolete PR runs are cancelled or coalesced before expensive native jobs.

As of 2026-08-25, GitHub documents standard GitHub-hosted runner minutes as
[free for public repositories](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
Artifact storage and retention still require explicit management, and
[larger runners are always billed](https://docs.github.com/en/billing/reference/actions-runner-pricing).
The policy above therefore optimizes storage and queue time even when standard
runner execution minutes are free.

## 11. Implementation plan and closure order

Each phase produces a reviewable local change and focused evidence. Completing a
phase does not authorize push, Pull Request, merge, tag or release.

### Phase 0 — freeze scope, host matrix and evidence contracts

- Name the exact internal-Beta OS versions, Linux DEB distributions/desktop
  sessions and native runner images.
- Freeze the versioned evidence schema, package/SHA aggregation rule, short/long
  soak budgets and manual acceptance template.
- Cross-map every native row to the existing LFC, CFG and PMA contract rows.

**Gate:** no native claim uses an undefined “Windows,” “Linux,” “macOS,”
“stable,” or “passed” scope.

### Phase 1 — scripted model boundary

- Implement the loopback protocol server and schema-routed scripts.
- Cover inventory/probe, exact capability evidence, Common/Emergency routing,
  adoption reveal, complete-response chat, malformed request and unexpected
  request behavior.
- Exercise the production secret store with a synthetic credential and prove
  the server cannot bind non-loopback, use external network or log secret fields.

**Gate:** production Provider/model adapter tests pass against the server, and
an unexpected schema fails closed.

### Phase 2 — installed product journey driver

- Extract reusable HTTP/WebSocket session support from the existing diagnostic
  flow without treating source `serve.py` as installed evidence.
- Drive Setup, Provider/Food, adoption, chat and restart against an installed
  package and temporary data home.
- Start from a neutral cwd with source environment removed; verify receipt,
  installed resource origin, Setup token/CSRF, history and execution receipts.
- Emit redacted typed evidence, preserve diagnostics on failure and clean every
  test-owned process on both paths.

**Gate:** one disposable local/reference target completes the journey and
restart recovery without direct database seeding.

### Phase 3 — native package and host integration

- Run the journey on `darwin-arm64`, `darwin-x64`, `win32-x64` and `linux-x64`.
- Add release-sensitive PR routing and a no-publish manual candidate entry.
- Verify OS receipts, shortcuts/desktop entries/PATH, standard-user launch,
  uninstall footprint and a real Linux Dedicated no-display lifecycle case.

**Gate:** all four exact package hashes pass native smoke and installed journey;
Linux passes both graphical and Dedicated authority cases.

### Phase 4 — lifecycle recovery matrix

- Implement the duplicate-start, command-race, Core/Godot/Renderer recovery,
  model-outage, stale-identity, port-conflict and installed-preflight cases.
- Exercise update handoff while the old Controller runs.
- Keep fault injection exact-PID, disposable-root and target-native.

**Gate:** applicable LFC-001/002/003/005/006/007/008/009/010 residuals have
replayable native evidence or remain explicitly open.

### Phase 5 — UI acceptance

- Automate one complete Setup -> model configuration -> adoption -> chat UI path
  on Linux Xvfb.
- Add one minimal installed Viewer non-blank/activation check per native target.
- Upload bounded failure screenshots and console diagnostics.

**Gate:** the shared UI journey passes and each target proves its native Viewer
can start; tray/system behavior remains explicitly manual.

### Phase 6 — real upgrade and persistence

- Select the immutable previous supported artifact.
- Seed state only through the installed product journey.
- Upgrade to the candidate and prove continued chat plus preserved data.

**Gate:** all four targets pass previous-version-to-candidate recovery.

### Phase 7 — evidence, CI identity and cost controls

- Bind every summary to candidate SHA and package SHA-256.
- Add retention, cancellation, concurrency and failure-only artifact rules.
- Add independent four-target evidence aggregation, frozen runner images, an
  Actions usage/storage review procedure and budget alert guidance.

**Gate:** evidence is sufficient to diagnose a failure without secrets, while a
normal PR does not retain native installers.

### Phase 8 — soak and resource budgets

- Freeze budgets, then add the 30–60 minute scheduled workload, trend classifier
  and bounded data/log growth checks.
- Run 24-hour target-host observations for macOS, Windows and Linux.
- Keep passive read-only observation separate from active disposable-host soak;
  classify every restart, generation change, error delta and crash.

**Gate:** the agreed observation window closes with no unexplained lifecycle or
resource trend; otherwise the corresponding row remains open.

### Phase 9 — final native and public-distribution closure

- Complete real desktop tray/window/single-instance/manual checks per OS.
- Complete interactive installer/OS-launcher and supported-host samples.
- Run the PMA-002 representative real-provider capability matrix; the minimal
  canary remains only an availability signal.
- Add signing, notarization, quarantine/SmartScreen and checksum gates only for
  an explicitly authorized public release.
- Review all conformance rows and retain unresolved external evidence.

**Gate:** no P0 or release-blocking native row remains open for the intended
distribution scope.

## 12. Definition of complete

The validation system is complete for an internal beta only when:

- the shared functional suite and selected architecture/security gates pass;
- exact supported host/runner scope and resource/recovery budgets are frozen;
- all four package targets pass native install smoke;
- each target proves receipt/shell integration, standard-user launch and clean
  package-footprint removal;
- all four pass the installed Setup/adoption/chat/restart journey;
- one shared UI journey and four minimal native Viewer checks pass;
- the selected real upgrade baseline passes on all four targets;
- macOS, Windows and Linux have classified soak evidence;
- the native lifecycle resilience matrix and the PMA-002 representative
  real-provider matrix have current evidence;
- manual OS integration residuals are recorded;
- exact candidate/package identity and redacted evidence are retained; and
- every applicable conformance row is closed or explicitly deferred by the
  distribution scope.

This is a strong release-confidence boundary, not a claim that every device,
driver, desktop environment, security product or real Provider has been tested.
