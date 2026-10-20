# Coding Companion

A local Python companion for coding agents. Version 0.4 implements discovery and local impact routing, static/contract checks, native project probes, durable scheduling/watch coordination, repair verification, private memory, optional local ranking and reviewed package updates. It needs no paid service, hosted database or model API.

Distributed under the [MIT license](LICENSE). Repository access can remain private; recipients may use, modify and redistribute copies under the license terms.

The [requirement ledger](design/requirements.json) maps the target inventory to source/test evidence and explicit remaining gates. `python tools/validate_requirements.py` rejects missing requirements, broken references and unsupported completion claims. `unassessed` means individual implementation evidence has not yet been reviewed; it is not a claim that the feature is absent.

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for tested capabilities, explicit detector scope and certification requiring real projects/hosts.

## Run from source

Requires Python 3.12+ and SQLite 3.38+ with JSON/STRICT support. The default core has no third-party runtime dependencies.

```powershell
python companion.py doctor --json
python companion.py discover --project "C:\path\to\project" --json
python companion.py plan --project "C:\path\to\project" --json
python companion.py check --project "C:\path\to\project" --json
python companion.py findings --project "C:\path\to\project" --json
python companion.py inspect FINDING_ID --project "C:\path\to\project" --json
python companion.py verify FINDING_ID --project "C:\path\to\project" --json
python companion.py report --project "C:\path\to\project"
```

Use equivalent paths on macOS/Linux. Default state is outside the customer project under the OS user state directory. `--state-dir PATH` selects a different base; each canonical project receives a separate subdirectory. In a restricted executor, specify an authorized writable base. Windows sandbox path virtualization can require executing these commands with the host's normal approved local path access.

The fast plan validates Python syntax and JSON/TOML formats without executing customer code. `--check sqlite.schema` explicitly validates files named `schema.sql` or `memory_fts.sql` with SQLite in memory; it does not interpret PostgreSQL/MySQL syntax. Unsupported languages and detector families are visible in the coverage plan.

`--scope changed` follows known Python imports/package initializers, relative JavaScript/TypeScript imports (including side effects, re-exports, literal dynamic imports and emitted `.js` names), local `tsconfig.json`/`jsconfig.json` path mappings with bounded local inheritance, unconditional local package exports, and explicit contract-file references. Configuration changes, deletions, computed imports, conditional exports, unresolved external packages, bundler aliases and unsupported relationships fall back to project scanning. JavaScript analysis is lexical; it is not a full language/dependency resolver. Polling may reuse metadata; execution/verification always hash current inputs. A successful scan proves only selected checks.

Exit codes: `0` completed selected checking, `1` selected check failed, `2` incomplete/invalid/blocked checking, `130` interruption. No applicable inputs, zero executed tests, stale results, missing reports, timeouts and truncated evidence never become a pass.

## Watch and checkpoints

```powershell
python companion.py watch --project "C:\path\to\project"
python companion.py findings --project "C:\path\to\project" --since 0 --json
python companion.py stop --project "C:\path\to\project" --json
```

The watcher holds one OS-backed project lock, establishes a baseline and debounces saved changes. Other CLI calls use a bounded durable mailbox. Worker lanes enforce concurrency bounds and aging. Stop requests cancel native jobs; a running static parser finishes its current bounded operation. Keep the findings cursor, and optionally `ack --since CURSOR` to acknowledge delivery. No OS scheduler is installed.

Queries and command output are machine diagnostics. Live Codex/Claude hooks and cloud orchestration are not certified by this runtime. The portable skill uses CLI checkpoints.

## Native project tools

See [native-probes.md](skills/coding-companion/references/native-probes.md) for specifications, explicit trust and JUnit count requirements. Native executables run only after `probe approve SPEC --trust-workspace-execution`. Approval binds command, executable and input hashes; changed inputs require renewed approval. Test probes require JUnit evidence; exit-code probes prove only non-test command success. Shell scripts/shims are unsupported.

Native execution uses host permissions. Windows processes launch suspended, enter a nonbreakaway Job Object with a per-process memory limit, then resume. Job closure terminates ordinary descendants after success/failure/timeout/cancellation. POSIX uses process groups and reports memory limits unenforced. Time/output bounds are enforced; filesystem/network/CPU/GPU isolation is not supplied. Tool binaries, command files, module versions and SQLite journal/WAL inputs are bound to provenance.

For npm projects, `discover` and `probe propose` offer direct installed TypeScript, ESLint, Vite and Vitest commands. Each package receives a separate ID; normal and hoisted installations inside the project are supported. Missing tools/configurations remain visible blocks. No dependency installation or package script execution occurs during discovery.

```powershell
python companion.py probe propose --project "C:\path\to\web-project" --json
python companion.py probe propose native.web.tests --project "C:\path\to\web-project" --output "C:\review\web-tests.json" --json
python companion.py probe approve "C:\review\web-tests.json" --project "C:\path\to\web-project" --trust-workspace-execution --json
python companion.py check --project "C:\path\to\web-project" --check native.web.tests --json
```

Export a spec outside the project or before approval; adding a review file after approval changes the bound inputs. Node runs the installed CLI through a packaged directory wrapper with no shell. Vite build output and TypeScript incremental metadata go to scratch storage. Vitest must produce nonzero JUnit cases. Approved Node CLI packages have bounded runtime-artifact hashes in addition to entry-point hashes; transitive dependency code and external environment inputs are not exhaustively frozen. CLI success proves the selected tool's scope, and custom scripts/configurations can require separately reviewed commands. See the official [TypeScript options](https://www.typescriptlang.org/docs/handbook/compiler-options.html), [ESLint CLI](https://eslint.org/docs/latest/use/command-line-interface), [Vite CLI](https://vite.dev/guide/cli) and [Vitest reporters](https://vitest.dev/guide/reporters).

## Memory and improvement

`verify FINDING_ID --lesson "LESSON"` records a private project lesson after current successful verification. `memory search QUERY`, `memory inspect ID`, `memory export`, and `memory delete ID` provide bounded operations. Search retrieves at most five nonexpired verified lessons. Deletion scrubs live lesson content; previously exported backups require separate removal. Raw source and chat transcripts are not stored as lessons.

`challenges --record "SYMPTOMS" --goal "GOAL" --actor coding_agent` records a bounded, redacted diagnostic journal. `feedback FINDING_ID --outcome resolved` reruns verification; it cannot merely assert resolution. Other lifecycle feedback needs a reason.

`improve plan` lists supported gates. Lesson proposals can be evaluated, explicitly activated and rolled back. `learning train --dataset FILE --authorize-local-training` supports local ranking with declared rights/consent, disjoint splits and a recorded evaluation budget. Activation requires `--approve`; ranking cannot suppress required checks or train a provider's underlying model.

`suppress FINDING_ID --reason REASON --expires-at UTC_TIME`, `unsuppress ID`, `maintenance`, and `withdraw finding|challenge|lesson ID` support scoped cleanup. Withdrawal invalidates derived models/candidates, scrubs live content/replay caches, removes hash-owned local evidence/backups and reports external exports. `memory export --output PATH` registers an export; existing external copies require separate removal.

`update evaluate --proposal FILE --evidence FILE --accept-external-evaluation` binds independently supplied evidence to exact package/base/evaluator/fixture hashes without executing candidate code. `update activate --candidate ID --approve` stages an immutable wheel and DB-compatible pointer/backup. `update rollback`, `update recover`, and `update launch --run-args doctor --json` provide reviewed rollback/recovery/launch. Installed source is never silently rewritten. Automatic patch generation and evaluation without verified isolation remain unsupported.

`benchmark --results FILE` validates matched measured trials, including companion overhead, and reports observed acceptance/time/token deltas. It does not claim universal superiority. Runtime settings do not control a provider's treatment of an existing agent conversation.

## Packaging and host integration

```powershell
python tools/build_release.py
python -m pip install --no-deps dist/coding_companion-0.4.1-py3-none-any.whl
companion doctor --json
companion host plan codex
companion host install codex --destination "C:\path\to\skills\coding-companion"
```

The source ZIP and wheel exclude runtime state, evidence, model data, credentials and `.codex` settings. Installation of the portable skill requires an explicit new destination. Removal checks ownership hashes and preserves modified/user-owned files. Neither operation changes host settings or installs hooks/schedulers.

For an existing private GitHub release, `python tools/download_release.py --repository OWNER/REPO --version 0.4.0 --sha256 REVIEWED_SHA256 --output NEW_WHEEL_PATH` uses separately authenticated GitHub CLI, checks that the repository is private, downloads only the pinned wheel, and verifies its supplied hash/package identity. Obtain the hash from an independently reviewed release record. It stores no new credentials, replaces no existing file, and installs nothing. Actual private release access remains unverified until an authorized repository/release is supplied.

The MCP stdio adapter is tested with official SDK 2.0.0 and protocol 2025-11-25. Install `.[mcp]` separately. Twelve structured tools expose discovery/plans/checks/runs/findings/verification/feedback/challenges/memory/reports; arbitrary shell/SQL/approval tools are excluded. Core CLI operation needs no SDK.

`host plan codex` emits a reviewable local async hook fragment. `hook` validates a registered project and never reads transcript paths or executes supplied tool-input commands. Active-turn Codex delivery remains unverified; the adapter/config is tested locally. Skill installation does not install/trust hooks. [Official hooks documentation](https://learn.chatgpt.com/docs/hooks)

Codex hook commands use an absolute companion launcher, so a source checkout or isolated wheel works without a global package install. Generated hooks cover session start, prompt checkpoints and supported tool completion names. Codex must review and trust the exact hook definition through `/hooks` before execution. `python tools/validate_codex.py --executable NATIVE_CODEX_PATH` tests actual app-server discovery and seeded/clean companion execution without inference or a trust bypass. Add `--codex-executable NATIVE_CODEX_PATH` to the release validator to retain this gate with the other results.

## Detector profiles and live probes

Profiles: fast, security, browser, data, rag, model, training, load, maintenance and full. Fast selects Python/JSON/TOML syntax. Other profiles select explicitly scoped inputs:

| Check | Input/scope |
|---|---|
| `security.patterns` | Python risky-call patterns, classified as predicted risks |
| `web.semantics` | Local HTML alt/duplicate-ID heuristics |
| `data.contracts` | `companion.data.json`: CSV/JSONL rows, required fields, uniqueness/relations |
| `rag.contracts` | `companion.rag.json`: captured retrieval/index tenant/deletion/freshness/recall |
| `ai.contracts` | `companion.evals.json`: captured outputs and explicit expectations |
| `model.contracts` | `companion.model.json`: identity, context budgets and artifact hashes |
| `training.contracts` | `companion.training.json`: declared rights, split isolation and finite losses |
| `performance.contracts` | `companion.metrics.json`: supplied workload samples and thresholds |

The package includes unittest, rendered-browser, loopback HTTP and read-only SQLite helpers for approved native probes. Browser execution needs Playwright 1.63.0 (`browser` extra) and an installed browser. It checks declared routes/viewports and bounded console/resource/overflow/visibility/focus assertions; this is not full accessibility certification. HTTP requests require explicit expectations and `--allow-mutation` for active methods. SQLite probes clone a bounded read-only source to memory and check integrity, foreign keys and restricted scalar expectations without changing customer rows.

Browser actions also support declared focus and bounded keyboard presses. `selector_focused` checks the current focus without changing it; `selector_receives_pointer` checks whether the element or its descendants receive a hit at its visible center. Intentional overlays that allow pointer events through remain valid. These checks do not prove whole-element visibility or complete keyboard accessibility.

The `coding_companion.scenario_probe` helper runs loopback access matrices and sequential/concurrent HTTP steps. Each actor/resource pair requires an explicit expected result; parallel batches contain 2–16 requests and finish before a subsequent invariant request. At most 100 requests run. Active methods require `--allow-mutation`, and the native runner still requires exact approval. See [scenario contracts](skills/coding-companion/references/scenario-probes.md).

Verification preserves original captured expectations, command identity, required failing cases, recognized Python test definitions, and the contents of JavaScript/TypeScript `*.test.*`, `*.spec.*`, `tests/` and `__tests__/` files. Changing a threshold/filter/assertion does not silently establish repair; review revised acceptance criteria separately.

## Development verification

```powershell
python -m unittest discover -s tests -v
python tools/validate_architecture.py --summary
python tools/build_release.py
python tools/validate_requirements.py
python tools/validate_release.py
```

Tests include real native fixture processes and watcher/client coordination. The architecture validator checks design contracts and SQL invariants separately. Tests currently establish Windows/Python 3.13 compatibility, not an untested cross-platform matrix or superiority over other tools.

Optional real integration validators:

```powershell
python tools/validate_optional.py --dependencies .companion/optional-deps
python tools/validate_browser.py --dependencies .companion/browser-deps --executable "C:\Program Files\Google\Chrome\Application\chrome.exe"
python tools/validate_web.py --project .companion/web-fixture
```

Those directories are isolated development installations, not runtime defaults. The supplied CI matrix is manually dispatched; local packaging starts no remote jobs.

`validate_release.py` runs gates, records exact input hashes and log hashes, and builds only after the selected checks pass. Its JSON records the current host and explicit certification limits. Pass `--optional-dependencies`, `--browser-dependencies` with `--browser-executable`, and `--web-project` to include existing optional fixtures. The manual CI matrix retains per-platform records and logs.

The web validator requires an explicitly named private `companion-web-certification-fixture` package with installed TypeScript, ESLint, Vite and Vitest. Install those development dependencies separately with lifecycle scripts disabled, then preserve its lockfile. The validator seeds test/type/lint failures, verifies repairs, rejects a weakened test and ends with all four real commands passing. It refuses to overwrite pre-existing fixture sources without its ownership marker.
