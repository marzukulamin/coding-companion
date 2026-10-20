# Runtime implementation status

Version 0.4.1 — 12 October 2026.

Version 0.4.1 targets Codex. An absolute-path launcher supports source checkouts and isolated wheels without a global companion installation. Hook configuration covers session start, prompt checkpoints and supported tool completion names. Oversized context drops whole observations instead of cutting JSON. tools/validate_codex.py initializes the actual Codex 0.160.1 app-server, proves hook discovery, and executes seeded/clean hook fixtures without starting a model turn or bypassing trust. Active-turn delivery still requires user review/trust and a live-session test. The project hook configuration preserves existing TOML settings and uses project-local state; installing it does not establish trust.

Version 0.4 adds a validated ledger for all 172 requirements, bounded local JSONC TypeScript/jsconfig alias inheritance and unconditional workspace exports, declared browser keyboard/focus-state/pointer hit tests, and loopback authorization matrices/concurrent HTTP steps with invariant readbacks. The scenario probe has seeded tenant-leak and lost-update fixtures, a native current-repair fixture, and weakened-contract rejection. MIT licensing is included in wheel metadata, the wheel license directory and the source ZIP. A GitHub CLI download helper supports exact private release/version/hash pins without installing artifacts; its mocked authentication/download regressions do not certify real repository access. Manual CI retains per-platform validation records and logs; it has not been dispatched here.

The ledger distinguishes implemented, partial, deferred and unassessed requirements. Unassessed means exact evidence has not yet been reviewed, not that the runtime lacks all related behavior. Reference validation does not replace behavioral acceptance or certify host delivery.

Fresh 0.4 results are recorded by tools/validate_release.py in dist/validation.json, with source/test input hashes, selected gates, platform and log hashes. The 0.3 results below are historical and do not substitute for this run.

The local implementation now spans the six build phases. It is an operational companion with explicit coverage limits, rather than a claim that every target requirement or detector family is certified.

| Phase | Implemented | Remaining certification or scope |
|---|---|---|
| P0 | CLI/wheel/source packaging, strict resource config, doctor, manifest/framework/service proposals, explicit acceptance inputs, Python package initializer/submodule and relative JS/TS import routing, metadata polling with reconciliation, bounded hashes, migrations and project isolation | Broader language/dependency graph adapters, full JS/TS parsing/alias resolution and full generic event-contract compatibility |
| P1 | Python/JSON/TOML/SQLite parsing, real unittest adapter, JUnit/SARIF probes, reviewable installed TypeScript/ESLint/Vite/Vitest specs, Node CLI package runtime provenance, immutable observations, current verification, Python and JS/TS test/criteria preservation gates, suppression expiry, scoped memory and journal | Tool/version-specific parsers and broader customer regression fixtures; transitive Node dependencies are not exhaustively frozen; heuristics remain predicted risks |
| P2 | Single OS coordinator, durable request/replay ownership, bounded aged worker lanes, coalescing, stop during native execution, snapshot freshness, Windows suspended Job Object launch, descendant cleanup, retention and privacy-cache epochs | Broader load/soak benchmarks and fast interruption of an already-running static parser |
| P3 | Portable skill, preserving installer, 12-tool official MCP SDK adapter, real stdio exchange, documented local Codex hook adapter/config fragment, local ZIP/wheel and manual CI matrix | Actual Codex/Claude active-turn delivery, cloud orchestration and OS/Python-version matrix certification; hooks are not installed automatically |
| P4 | Local security/HTML/data/RAG/AI/model/training/performance packs; real rendered-browser, loopback HTTP and read-only SQLite probes; fixture regressions; matched-trial analysis | Real customer projects, service/model/hardware fixtures, independent agent trials, complete accessibility/security/traffic certification and remaining specialized packs |
| P5 | Verified lesson evaluation/activation/rollback; authorized local hashed ranking training with independent splits; immutable package staging, exact hash/evaluator/fixture gates, external-attestation evaluation, reviewed activation, DB-compatible rollback/recovery and active-wheel launch; deletion propagation | Automatic patch generation and candidate execution in independently verified isolation. External attestation is supplied evidence, not an evaluator run performed by the companion |

Historical version 0.3 validation on Windows, Python 3.13.15 and SQLite 3.50.4:

- 103 runtime/feature/routing tests passed in the prior 0.3 run.
- 64 independent design invariants pass.
- Full Draft 2020-12 validation passes for exported examples/runtime results and control conformance fixtures.
- MCP SDK 2.0.0 negotiated protocol 2025-11-25 in an actual stdio client/server exchange: 12 tools, a seeded defect, inspection and current repair verification.
- Playwright 1.63.0 with existing headless Chrome detected a local console defect and verified its repair across three rendered assertions.
- Actual unittest, SARIF, loopback HTTP and read-only SQLite fixtures run through the native runner. Windows child cleanup after successful parent exit is tested.
- Real TypeScript 7.0.2, ESLint 10.12.0, Vite 8.3.4 and Vitest 5.0.4 run through approved probes in an owned synthetic web fixture. Test/type/lint failures are detected, repairs are verified, weakened assertions remain unresolved, and all four final commands pass. The installed 0.3.0 wheel includes the Node wrapper and emits all four usable proposals.

The manually dispatched CI workflow is supplied for future matrix execution; remote jobs have not been run or paid for by this task.

Privacy withdrawal invalidates derived lessons/candidates/components, removes owned evidence and registered owned backups, clears durable response excerpts and advances a retrieval epoch. External exports are marked withdrawn and reported for separate removal. Filesystem copies, SSD erasure and model unlearning are not promised.

Scope is reported per check. Captured RAG/AI/training/performance contracts evaluate supplied evidence; they do not imply that a live service/model/load generator ran. Browser focus/semantics checks are not full accessibility certification. Native commands need explicit trust and host permissions; Job Objects bound process lifetime/memory, not filesystem/network authority.

Version 0.3 adds reviewable web-tool probes and JS/TS test preservation. Snapshot selection now persists the most recently observed identity even when source returns to previously seen bytes; native approval hashes fresh current inputs. Coverage gaps and resource policy also participate in partial snapshot identity. These changes preserve snapshot creation timestamps and use existing schema-v2 metadata without changing migration checksums.

No repository publication, hosted backend, OS scheduler, production access, global skill/hook installation or real user-dataset training job has been performed. Training tests use generated synthetic fixture data.
