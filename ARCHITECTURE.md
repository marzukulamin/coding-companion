# Coding Companion — implementation architecture

Decision date: 12 October 2026, Asia/Dhaka. Architecture version: 1.0.

This is the target implementation design, with concrete schema, protocol, configuration, and validation artifacts. An initial local runtime is now implemented; IMPLEMENTATION_STATUS.md records its tested boundary and remaining gates. COMPANION_REQUIREMENTS.md remains the source requirement inventory; IMPLEMENTATION_PLAN.md traces every requirement to a module and acceptance criterion.

## 1. Decisions

| Concern | Selected design |
|---|---|
| Frontend | None. Agent tools, terminal output, JSON, and Markdown reports are the interfaces. |
| Backend | Local modular Python application, not a hosted web application. |
| Python | Minimum 3.12; recommended development interpreter 3.14; certify each supported interpreter/OS combination. Newly released versions enter the matrix after tests. |
| Core dependencies | Python standard library, including sqlite3. No mandatory paid service or mandatory third-party Python runtime package. |
| Query language | Parameterized SQL, using the SQLite dialect. Named filters in tools; never arbitrary model-supplied SQL. |
| Internal database | One SQLite database per registered project/worktree, on local state storage. |
| Memory search | Optional SQLite FTS5; bounded keyword/tag search when unavailable. No vector service required. |
| Configuration | TOML, parsed with tomllib. JSON check manifests and capabilities. |
| Contracts | Versioned JSON Schema; UTF-8 JSON and NDJSON for machine-readable exchanges. |
| Agent packaging | Portable Agent Skill, with thin host adapters rather than host-specific rules in the core. |
| Continuous operation | Optional session coordinator, durable local file mailbox, and bounded polling or host events. |
| MCP | Optional SDK-backed stdio adapter. No listening network server in the default product. |
| Browser probes | Optional JavaScript/Node Playwright and axe-core adapter. It checks customer interfaces without a companion frontend. |
| Default reasoning | Existing coding agent interprets evidence. Core checks do not call a paid model. |
| Optional learning | Project memory, evaluated rules, self-repair patches, and optional local trained components. |
| Distribution | Private GitHub source and authenticated tagged releases; local validation is sufficient. |
| Default cost policy | No required new service charges; remote paid probes, paid inference, hosted databases, and training workloads disabled unless separately configured. |

Python keeps orchestration close to database, filesystem, test, data, and model tooling. External probes remain language-independent. The language of the companion does not limit the languages or models it can inspect.

The supported Python branches are documented by Python itself. Use current patch releases and inspect the linked SQLite library separately. [Python version status](https://devguide.python.org/versions/)

## 2. What zero dollars means

The required software uses the user's existing computer or already available execution environment. It does not provision a server, buy a domain, require an API subscription, or depend on a free cloud tier staying available.

- Required: Python, local storage, and the project's installed tools for its requested checks.
- Optional free software: browser automation, language linters/compilers, vulnerability scanners, model runtimes, and load generators. Installation/downloads need available disk, connectivity, licensing, and user authorization.
- Existing machine, electricity, connectivity, coding-agent subscriptions, and customer application infrastructure remain outside the companion's service-fee budget.
- No independent model calls are needed to scan manifests, run native checks, store evidence, or retrieve memory.
- Customer model/API tests can themselves create charges. Default to fixtures/mocks; unknown or billable remote probes are blocked in the zero-cost profile.
- Arbitrary trusted project scripts can conceal network calls. A cost policy is not a network sandbox: require enforceable isolation for untrusted/unknown scripts, or report the check blocked.
- Local training can require substantial compute even without service fees; it is an optional bounded workload, never a prerequisite.
- CI defaults to local execution. GitHub-hosted Actions are optional and must remain within allowance or have an enforced stop-spending setting.

GitHub Free supports private repositories with limited features. Private-repository Actions have quotas and billable overage; these are not unlimited free infrastructure. [GitHub plans](https://docs.github.com/en/get-started/learning-about-github/githubs-plans), [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Spending controls](https://docs.github.com/en/billing/how-tos/set-up-budgets)

## 3. Why no frontend is needed

The primary customer is an agent performing a task. CLI and MCP calls can return findings, plans, evidence paths, and verification results. Humans can read terminal summaries or exported Markdown. A web dashboard would introduce routing, authentication, hosting, browser security, and deployment work before it improves detection.

Do not build React, Next.js, a public API gateway, or a web login for version 1. Browser testing remains important because the companion inspects websites. A future team dashboard is a separate optional product and must not become necessary for local operation.

## 4. System boundary and data flow

~~~mermaid
flowchart TD
  A[Coding agent or developer] --> B[Portable skill and CLI or MCP adapter]
  H[Host hooks and file events] --> C[Durable local mailbox]
  B --> C
  C --> D[Project coordinator]
  D --> E[Discovery, policy, snapshot, and impact routing]
  E --> F[Bounded check scheduler]
  F --> G[Native tools and optional isolated probes]
  G --> I[Normalize, redact, classify, and check freshness]
  I --> J[(SQLite project state)]
  I --> K[Bounded evidence files]
  J --> L[Compact findings and host delivery]
  L --> A
  A --> M[Agent applies repair]
  M --> C
  J --> N[Challenge journal and scoped lessons]
  N --> O[Evaluate candidate improvements]
  O --> P[Versioned rules, self-repair, or local learned artifacts]
  P --> E
~~~

The coordinator owns durable state and scheduling. Check subprocesses return data, not trusted instructions. The coding agent owns customer-source edits. The companion can repair its own package through a separate versioned process described below.

## 5. Deployment modes and portability

| Mode | Execution and behavior |
|---|---|
| Manual CLI | A developer or tool-enabled agent runs finite checks and reads reports. Required baseline. |
| Local continuous | A session coordinator watches the registered project; a supported host adapter delivers or polls results. |
| Local MCP | Host starts a stdio subprocess; tools use the same core/coordinator. Optional dependencies. |
| Cloud sandbox | Install the core in the sandbox and use available shell/filesystem tools. Persistence depends on host storage. |
| Chat without tools | Consume exported findings or supplied files. Cannot claim to inspect an inaccessible local project continuously. |
| Raw/local model endpoint | A tool harness executes the CLI/MCP interface and feeds results to the model. |
| Future remote service | Separate deployment needing hosting/authentication. Excluded from the mandatory zero-dollar architecture. |

Portability has two contracts: model-neutral instructions/results and host-specific execution/delivery. Agent Skills standardizes the package, not universal background execution. [Agent Skills specification](https://agentskills.io/specification)

Declare compatibility as documented-not-tested, tested, experimental, or unsupported. Never mark a product/version tested based only on documentation. The matrix records host/version, OS, orchestration location, execution location, tools, delivery semantics, adapter/core/schema versions, test date, and fallback.

For Codex local, investigate trusted asynchronous lifecycle hooks for informational same-turn delivery at safe points. Idle completion does not start a turn. Local command-hook support differs under cloud orchestration. Other hosts need their own acceptance tests. [Codex hooks](https://learn.chatgpt.com/docs/hooks)

Custom Codex clients can use supported app-server event/control interfaces only when the integration owns a permitted connection. Installing this skill does not attach to arbitrary desktop sessions. [Codex app-server](https://learn.chatgpt.com/docs/app-server)

## 6. Process and persistence ownership

One coordinator per project/worktree, with an OS-backed exclusive lock. Store coordinator PID, start identity, version, and heartbeat for diagnostics, but never use heartbeat alone as lock authority. Use fcntl on POSIX and msvcrt or a tested Windows lock implementation. Handle stale metadata after a process exits.

The coordinator has the sole writable database connection and owns transactions. Workers, hooks, and other CLI/MCP processes submit validated messages. They never write directly to SQLite.

Finite CLI operations acquire the coordinator lock and perform a bounded operation when no watcher exists. If the coordinator is active, submit a request to its mailbox. Do not create a second coordinator after a request timeout.

Maintain one project per database in version 1; a singleton project record and project-bound child records prevent accidental mixing. Other worktrees get distinct state directories. Team/shared learning is explicit sanitized export, not a shared writable database.

Suggested default state roots:

- Windows: LOCALAPPDATA/CodingCompanion/projects/<project-id>.
- Linux: XDG_STATE_HOME/coding-companion/projects/<project-id>, falling back to the user's local state directory.
- macOS: ~/Library/Application Support/CodingCompanion/projects/<project-id>.
- Cloud: explicit writable local state directory, with declared ephemeral or persistent lifecycle.

State contains database, inbox, responses, sanitized artifacts, coordinator lock, health record, and bounded logs. Keep it outside customer Git by default. Resolve project roots canonically without merging distinct case-sensitive paths or worktrees. Renamed roots require an explicit relocation operation.

## 7. Durable mailbox and crash semantics

Producers write bounded JSON to a same-directory temporary file, flush, and atomically rename to inbox/<UUID>.json. Restrict permissions. An event contains schema version, request/event ID, project/session identity, producer, event type, relevant relative paths or approved check IDs, input revision, deadline, and redacted payload.

Accept only known event schemas. Reject symlinks, path traversal, foreign project IDs, oversized requests, conflicting duplicate IDs, invalid encodings, unknown privileged fields, and arbitrary executable/command strings.

Event payloads are discriminated by event type, with required typed bodies and bounded artifact references. A body reference identifies a finalized sanitized artifact under the registered state root, with content hash, size, and body-contract version; it is not permission to read an arbitrary repository or external path. Validate the referenced bytes before use. Session-start handling creates its session record in the same intake transaction before any event foreign key refers to that session.

Claim each request ID with immutable project/session/producer provenance and canonical input hash before publishing a response. An identical replay returns the existing response; a different request using that ID is rejected. Worker results retain their originating request/run identity and cannot overwrite another request's response. Response contracts distinguish accepted/queued, completed, incomplete, rejected, expired, and cancelled states, and identify the tested revision. A caller timeout does not release ownership or authorize a second execution.

Coordinator flow:

1. Read and validate an inbox file with bounds.
2. Compute its canonical payload hash.
3. Commit an event row with a unique event ID. Same ID/hash is replay; same ID/different hash is quarantined.
4. Plan/enqueue jobs or process a query.
5. Remove the accepted inbox file only after the event transaction commits.
6. Persist and atomically publish a bounded response under the request ID.

Delivery is at least once with idempotency, not an exactly-once promise. A crash between commit and deletion replays safely. Event state remains durable; startup reconciles queued jobs, interrupted runs, and incomplete responses. Worker completion also commits results idempotently.

Responses have deadlines and expiry. CLI timeout means unknown/incomplete, not successful checking. Preserve undelivered findings for checkpoint polling. Limit mailbox files/bytes and coalesce redundant file events; report backpressure/dropped observations and perform reconciliation after overflow.

Version 1 uses the mailbox instead of TCP, reducing platform, authentication, and exposure complexity. Same-user filesystem permissions do not isolate hostile code executing as that user.

Request identity and result correlation are separate: request_id belongs to the initiating intake event and is unique. Worker check-result events must omit request_id; they may carry non-unique origin_request_id referencing that initiating event, with run_id providing execution correlation. Multiple result events cannot overwrite the origin request's response ownership. Responses distinguish complete, incomplete, blocked, rejected, error, cancelled, and expired; complete requires complete verification, while other terminal states carry reasons and partial/none completeness.

## 8. Database, SQL, search, and backup

The executable schema artifact is design/schema.sql. Require a SQLite build supporting the schema's STRICT tables and JSON validation (feature-probed; target SQLite 3.38+). Probe FTS5 separately. Inspect sqlite3.sqlite_version; Python version is not a guarantee of the linked library version.

Defaults: foreign_keys=ON, journal_mode=DELETE, synchronous=FULL, busy_timeout=3000 ms, short explicit transactions, bounded query result sizes, and parameterized values. Set SQL identifiers/orderings from allowlists. No tool exposes arbitrary SQL or dynamic extension loading.

Rollback journaling is adequate for the single-coordinator design. WAL is an opt-in optimization only after measurement and local-disk/version verification. The official WAL guide reports a race fixed in 3.51.3 and listed backports 3.44.6/3.50.7; an older version needs a documented patched build or rollback mode. Keep one writer/checkpointer even on patched builds. [SQLite WAL](https://sqlite.org/wal.html)

Do not place live state on NFS/SMB or a synchronized cloud folder. SQLite suits local state; a centralized many-writer service would need a separate architecture, potentially PostgreSQL. This does not change customer applications' databases. [SQLite use cases](https://sqlite.org/whentouse.html)

Logical tables:

| Table | Purpose |
|---|---|
| schema_migrations | Applied version/checksum and upgrade audit |
| project | Singleton canonical project/worktree identity |
| sessions | Host, policy/capabilities, lifecycle |
| snapshots / snapshot_files | Dirty-worktree manifest and relevant content/configuration fingerprints |
| check_definitions | Versioned manifests and provenance |
| events | Idempotent intake and processing state |
| runs | Check execution, input snapshot, outcome, coverage, counts, timing |
| findings | Stable issue identity, current lifecycle, fingerprint, priority |
| observations | Immutable per-run evidence and classification history |
| artifacts | Sanitized evidence references, hashes, size, retention |
| deliveries | Session cursor, payload digest, delivery/acknowledgment status |
| suppressions | Scoped reason, optional expiry |
| challenges | Difficulties faced by agent or companion, attempts, blockers, and outcomes |
| lessons | Scoped candidates, verified knowledge, rejected/revoked items |
| improvement_candidates | Proposed rule/code/ranking/model changes and evaluation |
| learned_artifacts | Optional versioned learned components and dataset lineage |
| audit_entries | Minimized action, policy, failure, and promotion records |

Large logs/screenshots live in files with metadata in SQLite. Finalize artifacts atomically, hash after redaction, and persist only complete references. Two-phase cleanup handles orphan files and expired references.

FTS5 indexes only approved lesson summaries/tags and is project-bound. The optional design/memory_fts.sql includes synchronization triggers. If unavailable, use bounded parameterized lexical/tag filtering. Cap/escape FTS query syntax and treat parse errors as search errors. Do not automatically fetch native extensions. [FTS5](https://sqlite.org/fts5.html)

Before migrations: acquire coordinator ownership, check free space, use SQLite backup API, validate schema checksum, apply one transactional migration, and run integrity/foreign-key checks. Fail visibly on corruption; preserve damaged state and recover from a verified backup. Never delete and recreate memory silently.

Migration files contain trusted DDL only; they do not own connection pragmas, BEGIN, COMMIT, or the applied-version ledger. Configure pragmas before the transaction. The planned Python driver uses SQLite autocommit mode with no transaction already open, executes a trusted script prefixed with `BEGIN IMMEDIATE;`, validates the new schema/foreign keys, inserts the migration version/checksum/time with parameterized SQL, and executes an explicit `COMMIT` on the same connection. The prefix leaves the transaction open after executescript returns; do not rely on a later independent ledger write or on Connection.commit() when autocommit=True. On any pre-commit error, explicitly roll back if a transaction remains open. Check integrity after commit and audit the result separately. A crash therefore commits both DDL and ledger or neither. Verify an already-applied checksum before treating a retry as complete; a mismatched checksum is an error.

Database constraints and runtime semantic validation jointly enforce identity and lifecycle consistency. A delivery's observation belongs to its stated finding; an observation's snapshot belongs to its run; nested findings use the enclosing result's run/snapshot and approved check context, while preserving native rule IDs/versions separately. Supplied event/run/challenge session references agree with their origin unless an explicitly authorized cross-session delivery is recorded. Artifact references resolve to available sanitized artifacts in this project. A resolved challenge or finding cites suitable complete verification on relevant current inputs, rather than an arbitrary existing run. Active lessons/components require applicable evidence, evaluation, authorization, and exact hashes. Validate these invariants transactionally before state transitions; JSON validity alone is insufficient. Preserve immutable rule/version, severity, confidence, and canonical finding evidence per observation so updating a finding does not rewrite history.

Backup through the database API, not by copying a live database file alone. Test restoration. Purge expired artifacts/lessons in bounded batches. SQLite is not automatically encrypted; use restrictive OS permissions and optionally OS disk encryption. Secure erasure on SSDs/backups cannot be guaranteed by a SQL DELETE.

Retention follows an explicit dependency graph across challenges, attempts, observations, artifacts, lessons, improvement candidates, exported datasets, and learned components. First tombstone an item, stop retrieval/delivery/training use, invalidate dependent lessons/components, and record a minimized deletion authorization; then remove content and indexes in bounded batches after reference reconciliation. Keep a metadata tombstone only where needed to explain unavailable evidence, without retaining deleted excerpts. Foreign-key restrictions and JSON evidence references must both be reconciled; setting a challenge link to null is not complete deletion. Track backup/export expiry and state honestly which copies can be removed. If deleted or withdrawn data influenced a trained artifact, retire that artifact until rebuilt from authorized data. Deleting its source row does not remove influence from model weights, and the product must not promise automatic unlearning.

## 9. Discovery, impact graph, and snapshot identity

Static discovery reads known manifests/configuration and resolves installed tools; it does not import the customer's Python modules or execute package installation. Record confidence for inferred services/check commands. Explicit user configuration wins over heuristics.

Build an incremental graph of packages, imports where parsable, configuration, schemas, routes, tests, data transformations, prompts, indexes, and services. Unsupported relationships are recorded as uncertainty. Native-tool dependency information can improve routing.

A snapshot ID hashes a sorted manifest of relevant relative paths/content hashes plus check-affecting configuration, policy, tool versions, lockfile hashes, and environment signatures. Git HEAD is supplemental, not sufficient. Do not hash or persist secret values; environment signatures use declared safe identifiers.

Exclude state, dependencies, VCS internals, large binaries, caches, build outputs, and generated files unless the check explicitly requires them. Keep explicit size/file-count bounds; report truncated coverage. Do not follow links outside the registered root.

Execution modes:

- Static read: read settled files, compare relevant hashes before/after.
- Approved original-workspace command: record relevant inputs before/after; changing inputs make results superseded/inconclusive.
- Isolated snapshot: copy required approved inputs/resources and run independently when a faithful snapshot is supported.
- External environment: bind evidence to explicit deployed revision/configuration and declared staging/production access.

Copying a repository is not necessarily a faithful executable snapshot: dependencies, links, generated files, databases, and environment behavior need adapters. Do not declare immutable testing without proving the environment correspondence.

Before alert delivery or repair verification, compare relevant inputs to current state. Unrelated changes need not invalidate a narrowly scoped result; dependency/configuration changes do. Keep historical observations even when no longer current.

## 10. Scheduling and resource policies

Initial proposed defaults: debounce 750 ms; polling 2 seconds while active and 10 seconds idle; one expensive subprocess at a time; up to two inexpensive subprocesses; 60-second fast check timeout; 180-second integration timeout; 2 MiB text-output limit; 10 MiB artifact limit; 1 MiB message limit; 256 MiB project-state budget. These are configurable starting limits, not measured guarantees.

For large workspaces, use metadata inventories/host events rather than rehashing all files every poll. Periodic bounded reconciliation catches missed events. Coalesce by project, check, and affected inputs. Priorities combine confirmed blockers, user-requested verification, changed-scope checks, and maintenance; age work to prevent starvation.

Bound input/output queues. Exceeding limits produces an explicit partial/inconclusive result or paused optional work. Never truncate evidence while reporting complete verification. Heavy load/model/training checks require explicit profiles.

CPU/RAM/GPU limits are enforcement-capability-dependent. Report whether a limit is enforced or best effort. A Python timeout is not a sandbox. Avoid assuming resource limits from configuration alone.

Cancellation terminates registered process trees, releases resources, marks interrupted runs, and preserves completed evidence. Use POSIX process groups and a tested resource-limit launcher; on Windows use tested Job Object/process-tree handling. Do not rely on killing only a parent process.

Only a running session or explicitly configured OS/host scheduler provides daily maintenance. Installation does not create a recurring task automatically.

## 11. Check manifest and runner

design/checks.example.json specifies a check manifest: stable ID/version, category, stack/version applicability, relevant inputs/triggers, executable argv template, bounded cwd, output parser, prerequisites, profile, risk/permission scope, network/cost declarations, resource budget, and verification relation.

Events name approved check IDs. They cannot inject commands. Trusted built-in adapters map manifests to executables. Repository-defined commands require approval/trust under the user's host policy. Scope that trust to command/configuration hashes; re-review material changes.

Use argument arrays with shell=False and resolved executable paths. Test Windows command shims deliberately; .cmd/.bat behavior differs from native executables. Never concatenate model text into a shell command. Only fixed placeholder names can be rendered into argv elements. Validate final cwd/paths against allowed roots.

Construct a minimal environment; do not forward every credential. Test accounts/databases and loopback services are explicit resources. Network policy must be enforceable for untrusted execution; otherwise refuse that mode.

Stream subprocess stdout/stderr with bounded buffers. Redact before persistence/notifications, including secrets split across chunks; maintain a bounded rolling redaction window. Preserve exit code and parser status. If output is truncated or malformed, say so.

Parse native JSON, JUnit/XML, SARIF, or bounded compiler diagnostics through versioned adapters. Disable unsafe XML entity handling. Do not treat a missing report, failed parser, unavailable tool, or zero discovered tests as passed.

No automatic installing dependencies, browsers, models, or remote rule packs while watching. A separate reviewed setup operation supplies prerequisites.

## 12. Profiles and detector implementation

Profiles are fast, integration, browser, security, load, maintenance, rag, model, training, and full. Full expands applicable configured checks within permission/budget constraints; it does not imply universal coverage. Results enumerate requested, executed, passed, failed, errored, blocked, skipped, and unknown coverage.

| Pack | Implementation and verification evidence |
|---|---|
| C01 environment | Manifest/runtime/tool/configuration inventory; bounded connectivity checks only when allowed |
| C02 source/build | Native compiler/types/build/lint; Python AST syntax checks without import execution |
| C03 test infrastructure | Runner discovery/collection/counts, fixture/service setup, timeout/open-handle evidence |
| C04 test quality | Requirement-to-test map, boundaries, mock/contract drift, optional targeted property/mutation tests |
| C05 business rules | User-provided invariants and synthetic fixtures; precision/time/state-transition cases |
| C06 UI | Optional Playwright interactions, console/network results, screenshots, geometry/hit testing; intentional overlap cases |
| C07 accessibility | Optional axe-core plus keyboard/focus probes; unresolved manual-review coverage |
| C08 API/integration | Schemas/contracts, sandbox requests, webhook replay, streaming/cancellation |
| C09 identity/isolation | Synthetic role/customer/resource matrix across DB/cache/file/search/job paths |
| C10 security | Native/free scanners and validated patterns; source findings separated from demonstrated exploitability |
| C11 database | DB-specific clients/plans, constraints, transactions, pools, locks, replica lag |
| C12 lifecycle/recovery | Isolated migration/backfill/restore fixtures and deletion propagation |
| C13 data pipeline | Stage counts, freshness/lineage, schema drift, replay/reconciliation fixtures |
| C14 workers/caches | Retry/idempotency, poison jobs, queue growth, scheduler/time zones, cache invalidation/isolation |
| C15 concurrency | Controlled concurrent requests/workers with state assertions and repeatability |
| C16 capacity | Explicit workload/data/resources, p50/p95/p99, throughput/errors/queues, load-generator limits |
| C17 resilience | Staging/local dependency faults, bounded retries, recovery and explicit-failure requirements |
| C18 deployment/operations | Artifact/configuration/health/routing/rollout/rollback and observability checks |
| C19 RAG retrieval | Synthetic corpus, ingestion/index versions, expected passage IDs, permissions and citation mapping |
| C20 AI agents | Structured outputs, grounding, unanswerable/adversarial cases, tool loops/budgets, repeated evaluations |
| C21 model serving | Provenance/license/config compatibility, load/inference fixtures, RAM/VRAM/KV cache, queues and cancellation |
| C22 training | Explicit projects: dataset rights/splits, contamination, numerical stability, resources, distributed/checkpoint/evaluation checks |
| C23 extensions | Domain-specific packs, with an explicit unsupported-state report until implemented |

Each operational check needs a seeded failure, clean fixture, blocked-prerequisite case, parser/error case, and bounded execution proof.

Optional tools: installed project compilers/linters/tests first; Playwright/axe-core for browser/accessibility; Bandit for Python security patterns; Gitleaks for secrets; pip-audit or OSV tooling for dependency advisories; existing local DB/load/model tools. Check each license/version during packaging. pip-audit dependency resolution can execute package behavior, so do not classify arbitrary dependency auditing as harmless static reading. [pip-audit security model](https://github.com/pypa/pip-audit#security-model)

Browser binaries, Node packages, advisory downloads, and GPU/model dependencies are optional explicit prerequisites. Missing tools produce a coverage gap. Customer SQL dialects remain unchanged.

## 13. Findings, alerts, and repair

Contract definitions are in design/contracts.schema.json. Check outcome and finding classification are different fields. Confirmed application defects need evidence against a requirement/invariant. A tool execution error establishes a checking failure, not automatically a product bug.

Implement known runtime contracts with typed/dataclass validators or generated validators sharing conformance fixtures with the exported schemas. Core validation must not require fetching a schema or adding a generic interpreter at runtime. Development/release tooling should additionally use a full Draft 2020-12 meta-validator; the supplied standard-library design validator covers only the vocabulary used in these artifacts.

Each immutable observation records tested snapshot, rule/version, location, severity, confidence, expected/actual behavior, evidence references, reproduction, uncertainty, remedy, and verification. Stable findings group observations by rule plus semantic location/condition; avoid line-number-only fingerprints. Root-cause links remain hypotheses until substantiated.

Alerts include a short current finding, evidence location, and next action. Separate severity from urgency. Suppress unchanged duplicates and group downstream symptoms. Keep scoped/expiring accepted risks and dismissal reasons.

Freshness has a race boundary: files may change after the coordinator's last comparison or after host delivery. Include tested snapshot and observation time in every alert, revalidate before applying a proposed repair and before verification, and supersede results when relevant inputs diverge. Delivery acknowledgment proves receipt, not continuing correctness or successful repair.

Lifecycle: new → acknowledged/investigating → fixing → verified-resolved. Also support dismissed, accepted-risk, reopened, and stale. Verification must rerun suitable checks on current inputs. Deleting a test, muting a scanner, or changing an expectation does not by itself resolve a defect.

Repair preserves the user's intended behavior. Escalate when business requirements, access, hardware, or evidence are missing. Bound repeated failed attempts; journal each materially different attempt and avoid repeated guesses. Broaden checks based on impact/new evidence rather than rerunning everything indiscriminately.

The companion normally proposes; the coding agent edits customer code. Explicit repair modes need one writer, separate patch scope, rollback, and verification. Deploying, production migrations, external messages, or paid operations remain separately authorized actions.

## 14. CLI and MCP contract

Proposed CLI, not commands installed by these design artifacts:

~~~text
companion doctor --json
companion discover --project PATH --json
companion plan --profile fast --scope changed --json
companion check --profile fast --scope changed --json
companion watch --project PATH
companion findings --since CURSOR --json
companion inspect FINDING_ID --json
companion verify FINDING_ID --json
companion feedback FINDING_ID --outcome resolved --json
companion challenges --actor all --json
companion memory search QUERY --json
companion memory inspect|export|delete
companion improve plan|evaluate|activate|rollback
companion report --format markdown
companion stop
companion mcp --stdio
companion host plan|install|uninstall HOST
~~~

Commands require registered project/session identity where relevant. JSON output has a stable schema; progress goes to stderr. Use exit 0 for a completed selected plan with no blocking failures, 1 for confirmed blocking defects, 2 for invalid configuration/incomplete required checking, and 130 for interruption. The structured completeness field is authoritative; a zero exit is not a statement about unchecked areas. Requests are asynchronous when needed, returning IDs that can be polled.

MCP tools: capabilities, discover, plan_checks, start_checks, get_run, list_findings, inspect_finding, verify_finding, record_feedback, list_challenges, search_memory, propose_improvement, and export_report. Separate read-only and executable tools; do not export arbitrary shell/SQL/remote-upload tools.

Use an optional official SDK rather than implementing the protocol ad hoc. Pin a tested stable protocol/SDK pair and negotiate capability/version changes. Stdio stdout contains protocol messages only; logs go to stderr. MCP tool access alone does not ensure mid-turn unsolicited delivery. [MCP transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

Remote HTTP is excluded initially. If later added, define authentication, origin checks, TLS, tenancy, subscriptions, quotas, and data-use boundaries as a separate deployment.

## 15. Host integration lifecycle

On session start: discover capabilities, register session, establish baseline, retrieve relevant verified lessons, and display unavailable coverage.

After meaningful tool/file events: enqueue bounded events and selected checks. An async hook may wait within its host timeout for completed current findings, then return compact structured context. If it ends earlier, findings remain for the next checkpoint. Do not start one full scanner per hook.

Before completion: poll pending findings, perform requested verification, list unresolved/blocked work, and persist challenge outcomes. Do not use an endless stop-hook loop to prevent the user ending a task.

On interruption/session end: cancel that session's jobs, finish bounded durable bookkeeping, clean up resources, and stop a session-owned coordinator after configured idle expiry. Shared sessions are isolated in state, but another session's coordinator use is not interrupted.

Host installation is explicit and reversible: preview changes, back up relevant configuration, insert owned entries, record hashes/versions, respect hook trust, and preserve other plugins/settings. A changed hook definition may need renewed host trust; self-updates cannot bypass it.

## 16. Challenge journal: both agents and the companion

Record a structured challenge when either the coding agent or companion encounters a material difficulty. Actors: coding_agent, companion, user, or external_tool. Types include application defect, environment blocker, test/parser failure, diagnosis uncertainty, unsupported stack, tool incompatibility, stale evidence, delivery failure, resource exhaustion, failed fix, and companion defect.

Capture: challenge ID, project/session/run/finding references, timestamps, stage/task context, goal, symptoms, relevant constraints, expected/actual behavior, attempted actions and their results, hypotheses with confidence, cost/time, blocker, resolution, verification, and reusable candidate lesson.

Store attempts as bounded structured records and link sanitized evidence. Record unsuccessful attempts as failures, not proven remedies. Unknown causes remain unknown. User corrections are attributable feedback. Keep unresolved challenges resumable rather than pretending every session solved them.

The journal is not an indiscriminate transcript recorder. Redact secrets and minimize private excerpts. Provide inspection, correction, search, export, deletion, expiry, and per-project retention. Record recurrence counts and environment/version applicability so future work can prioritize recurring blockers.

When the same verified failure recurs, retrieve the applicable lesson and reproduction. If it no longer matches the environment, revalidate before reuse. Findings and challenges are linked but distinct: a challenge can exist without a product defect, and a defect can involve multiple failed attempts.

## 17. Memory, self-repair, and optional self-training

Default improvement uses scoped verified memory and deterministic feedback statistics. Candidate → reproduced → evaluated → approved → active/versioned; rejection/revocation remains auditable. Memory retrieval stays within project scope and a context budget. Generalization into shared rules requires sanitization and explicit rights.

Record source actor/component/version, environment applicability, evidence hashes, and verification basis for lessons and materially distinct attempts. Corrections append attributable revisions rather than silently turning failed attempts into successes. Unresolved or contradictory reports remain candidate evidence. Retrieved lessons are untrusted diagnostic context even when verified; they cannot grant permissions, change execution policy, or replace the user's goal. Learned ranking may prioritize optional work within policy but cannot suppress required checks, invent a passed result, or weaken verification gates.

Self-repair workflow:

1. Detect a companion defect through health checks, failed parsers, delivery errors, or journal feedback.
2. Produce a minimal reproduction and isolate the package/version involved.
3. The coding agent or explicitly selected local model proposes a patch in an isolated copy.
4. Run targeted regressions, security/secret-canary checks, contract tests, clean fixtures, and held-out evaluations.
5. Create an improvement candidate with evidence and exact diff/artifact hashes.
6. Activate only under configured authorization, after workers drain/restart; preserve last-known-good version.
7. Monitor regressions and roll back on failed acceptance criteria.

Pin an independently trusted evaluator and held-out fixture manifest outside the proposed package. Record evaluator, fixture, base-package, patch, and resulting-package hashes in the evaluation/approval record. A repair may add development tests but cannot edit the evaluator or held-out acceptance assertions used to approve itself. Repeated evaluation uses a recorded budget and reserved fresh holdouts to limit selection overfitting. Check source ownership/licenses and allowed patch paths before evaluation; customer code or private third-party examples cannot silently become distributed companion source.

The planned activation registry stores active, pending, and last-known-good immutable package hashes, expected base hash, schema compatibility, authorization, and phase. Acquire installation ownership and compare the current package with the approved base hash before switching; a version label alone does not prevent concurrent or substituted updates. Stage and verify the complete package, drain relevant workers, persist the pending intent, and atomically switch the active pointer. On startup, reconcile the pointer, registry, and health result after a crash; resume a verified candidate or restore last-known-good, never execute a partially staged package. Host executable/hook trust remains a separate gate and may require renewed review. Updates must declare compatible database schema ranges and a tested recovery plan before activation; a package rollback cannot safely reuse an incompatible newly migrated database. Preserve a verified pre-upgrade backup and reconcile any later observations explicitly instead of silently discarding them.

Do not rewrite the installed live package, trusted host policy, or customer source invisibly. Code/adapter updates and changed executable trust are separate from approving a memory lesson. Automatic promotion may be enabled for scoped non-executable lessons that meet the user's policy; executable updates need their defined review/activation policy.

Optional local training can improve check ranking, retrieval, or specialized detection. Start with low-cost feedback counts or a small local classifier, not mandatory LLM fine-tuning. Use authorized challenge/outcome data with ownership/consent, exclusions, transformations, split isolation, resource caps, evaluation, artifact lineage, rollback, and deletion.

Training/fine-tuning for customer projects remains supported through C22. Neither feature authorizes using this private project to train the assistant/provider's underlying model. Provider policies require their own account/configuration controls; project memory does not update assistant weights.

This user's private-project prohibition is an upper-bound policy, not a local switch that changes a provider's account settings. The example configuration records that intent; project/session overrides cannot relax it. Before any optional external processing, establish the applicable provider's actual data-use controls and permitted payload scope. If that requirement cannot be established, keep the relevant private payload local or report processing blocked. Do not imply that this runtime controls the provider's treatment of an existing coding-agent conversation.

Improvement runs on verified outcomes and optionally a configured local maintenance schedule. Daily improvement is measured by new evidence and evaluations, not by requiring a rule change every day.

## 18. Maintenance, scaling, and operational debugging

Maintain both the companion and the inspected system. Track dependency/advisory freshness, unsupported runtimes, schema/protocol drift, failing regressions, configuration differences, expired assumptions, growing storage/queues, and required updates. Dependency-update proposals run through compatibility checks in isolation.

For production incidents, ingest only explicitly supplied/authorized sanitized evidence: deployed revision, request/correlation IDs, trace/log window, feature flags, roles, relevant inputs/responses, recent releases, and state snapshots. A repository-only diagnosis may lack the customer's actual runtime state. Silent incorrect success paths need business-invariant and outcome checks as well as exceptions.

Scaling advice is evidence-based: declare workload/data/resources, measure bottlenecks and latency/error distributions, propose changes, rerun. More application instances do not fix every database or correctness bottleneck.

Keep runbooks for setup, verification, deployment, migration, rollback, backup/restore, retention, support, and ownership. Documentation drift is a risk until compared with observable behavior. Do not automatically deploy maintenance fixes.

The companion itself scales by incremental routing, bounded queues, local per-project databases, worker caps, and retention. Multiple downloaded users run independent local instances; they do not create traffic on a central service. A future team service would be a separately budgeted design.

## 19. Privacy and threat model

Assets: customer code, credentials, documents, diagnostic evidence, challenge memory, learned components, host settings, and the private package. Threats include hostile repository scripts/documents, prompt injection, poisoned memories/rules, dependency compromise, path/symlink escapes, cross-project leakage, resource abuse, and unauthorized external processing.

Controls: minimized inputs, approved check IDs, bounded schemas, resolved path boundaries, scoped resources, least-privilege environments, secret redaction, protected local directories, separate customer state, no default telemetry/uploads, trusted versioned check packs, and visible permission limitations.

Sandboxing must be real. Python stdlib process management does not prevent all filesystem/network actions. Run untrusted code only under host or optional verified container/OS isolation; otherwise block it. A same-user malicious process can access same-user files unless another boundary exists.

Optional models receive only permitted minimized context. Log/screenshot redaction may be incomplete; sensitive probes can require synthetic data or disable capture. Do not store API keys, tokens, credential-bearing URLs, or complete environments in evidence.

No telemetry or shared training data by default. Project/source privacy, local retention, remote inference, provider training settings, and repository access are separate controls. Exports specify scope and exclude raw/private material by default.

## 20. Health, observability, and recovery

doctor and status expose versions, DB integrity, coordinator ownership, queue depth/age, active/stuck jobs, coverage gaps, disk usage, redaction/parser errors, delivery failures, budgets, and enforcement capabilities.

Use bounded local structured logs and counters; no hosted monitoring service required. Record event, request, session, snapshot, run, finding, challenge, and improvement IDs for correlation. Measure scan durations, alert delivery delay, false positives, retries, and cost without storing unnecessary source.

Recovery cases: coordinator/worker crash, duplicate event, partial write, disk full, DB lock/corruption, clock changes, lost host connection, missing executable, malformed output, changed inputs, and package upgrade failure. Outcomes remain explicit. Use monotonic time for duration/deadline enforcement and UTC timestamps for records; render user-facing time in the configured timezone.

If the companion fails, the user can stop/disable it and continue through manual checks. Required verification still reports incomplete; optional advisory failure must not silently block all coding.

## 21. Configuration and precedence

design/companion.example.toml is a parseable non-executing example. Precedence: installation defaults → explicit user settings → registered project configuration → session overrides, with host/user permission policy remaining an upper bound. Repository settings cannot grant more access, spend, or data sharing.

Validate unknown fields/types, enums, bounds, paths, and incompatible modes. Produce the effective configuration with secret values omitted and provenance for decisions.

Configure profiles/checks, command trust, resources, network/cost, storage, retention, memory scope, notifications, host capabilities, learning, and update activation. Defaults disable remote analysis, telemetry, package downloads, production mutation, and training; verified project memory is enabled with bounded retention. Disabling a feature is a configuration choice, not a blanket architectural prohibition.

Configuration/rule changes invalidate affected snapshots/trust. Store policy hashes and scoped audit records.

## 22. Repository, packaging, and installation

Proposed runtime repository layout:

~~~text
src/coding_companion/
  cli.py, coordinator.py, mailbox.py, discovery.py, snapshot.py
  graph.py, router.py, scheduler.py, runner.py, redaction.py
  contracts.py, normalization.py, findings.py, delivery.py
  storage.py, challenges.py, memory.py, improvement.py, health.py
  adapters/hosts/, adapters/projects/, checks/, migrations/
skills/coding-companion/SKILL.md
skills/coding-companion/references/
probes/browser/
contracts/
tests/unit/, tests/integration/, tests/fixtures/, tests/hosts/
evals/development/, evals/heldout/
docs/, scripts/, pyproject.toml, compatibility.json
~~~

Core wheel can have no runtime dependencies. Build tooling is a separate development requirement. Optional extras isolate MCP/browser/learning dependencies; pin and test them. Provide authenticated source/ZIP installation as well as wheels; do not require publishing private code to a public package index.

The initial skill stays concise: preflight, relevant checks, evidence interpretation, repair/verification, challenge recording, relevant memory, and final unresolved coverage. Detailed packs live in references/tools. No overbroad trigger requiring all checks for every edit.

Install into each host's supported discovery path only after an explicit setup action. Record owned files/config entries; support idempotent upgrades, rollback, and safe removal. Cloud setup must place executables in its actual execution environment. Installation cannot grant credentials or execution rights automatically.

Keep repository private, use tagged releases and checksums, choose explicit distribution/licensing terms before sharing builds, and never commit runtime memory/evidence/secrets. Private access removal does not revoke copies already downloaded.

## 23. Validation and evaluation

Contract/schema tests; database constraints/migrations/backup/restore/FTS; mailbox crash replay/conflicting duplicates; snapshots/rapid saves; scheduler/backpressure; runner quoting/timeouts/cleanup; zero-test and malformed-report cases; redaction/poisoning; cross-project state; memory expiry/deletion; update activation/rollback; host installation/removal; offline modes; OS/version matrix.

Use seeded defects and clean intentionally unusual projects. Prove the detector can remain quiet. Tests use synthetic data and isolated resources. Host tests demonstrate advertised delivery semantics rather than merely checking configuration text.

Paired benchmark: same agent/version/settings, repository/task, hardware/tools, time/cost limits, with versus without companion. Include companion overhead, repeated runs, hidden acceptance assertions, holdout isolation, repair regressions, false alerts, incomplete coverage, and user intervention. Optional comparisons to other products use equivalent controls; no universal superiority claim.

Define release targets on a recorded reference environment: actionable-fast-check p95, watcher idle CPU, peak memory, duplicate/stale alert count, meaningful precision/recall, verified completion, and cleanup behavior. Thresholds become release gates only after benchmark baselines, not unsupported numbers.

## 24. Implementation sequence and completed boundary

1. Contracts, config validation, storage/migrations, discovery, doctor, and manual CLI.
2. Fast native checks, parsers/counts, snapshots/current findings, challenge journal, and scoped memory.
3. Mailbox/coordinator/scheduler, cancellation, budgets, polling, and one tested live host adapter.
4. Portable skill, optional MCP, additional hosts/OSes, installation/removal, and release validation.
5. Browser/API/database/security/deployment/maintenance/load/RAG/model/training packs by declared coverage.
6. Evaluated improvement, self-repair activation/rollback, and optional local learned components.

A pack is operational only after its acceptance fixtures and relevant host tests pass. All planned/unavailable categories remain visible. The architecture covers the full roadmap; implementing a small phase does not justify claiming the entire product finished.

Architecture artifacts supplied now: specification, executable database schema, optional FTS schema, protocol definitions/examples, configuration/check examples, compatibility declarations, research notes, traceability/build plan, and a validation helper. No server, repository, skill installation, recurring task, model training, or running companion is provisioned by this document.

## 25. Research basis and open decisions

RESEARCH_NOTES.md separates public anecdotes, primary research, technical documentation, and design inferences. The design responds to test validity, missing observability, incorrect confidence, maintenance regressions, runtime context, and cost/latency concerns without treating social-media claims as measured performance of the user's selected model.

Open inputs that cannot be inferred: GitHub owner/repository name and distribution license, first real target projects/fixtures, host versions to certify, approved execution/isolation environment, optional tools, and rights/resources for learned datasets. The local implementation is operational; these inputs are needed for broader release certification. IMPLEMENTATION_STATUS.md distinguishes those gates from implemented code.

Every original requirement and all 23 coverage families have an implementation owner and acceptance criterion in IMPLEMENTATION_PLAN.md. Future missed cases become tracked challenges, fixtures, and evaluated updates rather than an unbounded promise to foresee every failure.
