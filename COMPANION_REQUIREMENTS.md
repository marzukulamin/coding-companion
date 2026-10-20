# Coding Companion — requirements and coverage map

Date: 12 October 2026. Status: target requirement specification; an initial diagnostic runtime is implemented. IMPLEMENTATION_STATUS.md distinguishes operational capabilities from remaining work. The runtime is not globally installed by the implementation task.

## Product intent and user constraints

Build a downloadable companion for coding agents. It should discover project problems before work begins, observe relevant changes during work, run suitable checks, and deliver actionable findings so the coding agent can repair and verify them in the same session where supported.

- Keep the GitHub repository private initially. Downloads require authorized access.
- Package a portable Agent Skill with supporting software; avoid dependence on one model vendor.
- Support websites, web applications, databases, data pipelines, RAG, hosted/local model integration, and training projects through relevant check packs.
- Let the companion improve over time through memory, verified feedback, better rules, and optionally learned components.
- Do not use this private project to train the assistant's or provider's underlying model. This restriction is distinct from the companion's ability to learn or support training workflows.
- Treat this document as the requested requirements inventory. Repository creation, installation, publication, and actual model-training jobs remain separate implementation actions.

Coverage is explicit and testable. The product must disclose unsupported or unchecked areas rather than promise to discover every future defect.

## 1. Architecture and responsibility

- A01: Portable skill: concise instructions for selecting checks, interpreting findings, requesting evidence, and verifying repairs. Load specialized guidance only when applicable.
- A02: Model-independent diagnostic core: execute checks and normalize results without requiring an LLM for basic operation.
- A03: Project adapters: map technologies and existing project commands to suitable checks; do not assume every project uses npm, Python, or one framework.
- A04: Host adapters: integrate with each agent's documented events, tools, permissions, and notification mechanism.
- A05: CLI interface: support discovery, preflight, scan, watch, status, finding inspection, verification, and health checks. These are proposed interfaces, not implemented commands.
- A06: Optional MCP interface: expose structured tools and findings to compatible agent hosts; MCP availability alone does not establish unsolicited same-turn delivery.
- A07: Scheduler: prioritize relevant work, limit resource usage, and coordinate repeated requests.
- A08: Evidence store: retain bounded, redacted diagnostics separately from source code and release packages.
- A09: Memory and improvement subsystem: record scoped verified lessons, evaluate updates, and version changes.
- A10: Mutation ownership: the companion reports and proposes; the coding agent normally edits. Any companion repair mode must avoid concurrent edits and verify every patch.
- A11: Optional model analysis: use for hypothesis generation or difficult interpretation, keep its output labeled, and continue deterministic checks if the model service fails.
- A12: Optional UI: show coverage, active checks, actionable findings, evidence, budgets, and delivery health without making a dashboard necessary for core operation.
- A13: Version 1 has no frontend; CLI, structured tools, and Markdown reports provide agent and human interfaces.
- A14: Require no paid service, hosted backend/database, or independent model API; retain a local/offline operating mode.
- A15: Language-independent probe contracts and explicit host capability tiers provide portability without claiming that a model lacking tools can execute checks.

## 2. Project discovery and required inputs

- P01: Identify repository/worktree boundaries, monorepos, packages, languages, frameworks, runtimes, entry points, and generated files.
- P02: Identify build, test, lint, formatting, migration, startup, and deployment commands from actual project configuration.
- P03: Discover databases, queues, caches, object stores, APIs, model endpoints, and required services.
- P04: Record permitted environments and actions; distinguish local development, isolated tests, staging, and production.
- P05: Read relevant project conventions and user requirements without treating arbitrary source text as trusted policy.
- P06: Capture acceptance criteria, important user journeys, business invariants, and authorization rules where provided.
- P07: Capture traffic assumptions: request mix, concurrency, data sizes, peak load, latency/error targets, and infrastructure resources.
- P08: Capture supported browsers, viewports, devices, languages, time zones, and accessibility expectations.
- P09: Capture model identity, revision, runtime, hardware, context limits, and intended inference or training use where applicable.
- P10: Record unknown requirements explicitly; correct business behavior cannot always be inferred from existing code.
- P11: Create an initial baseline so existing failures are distinguishable from newly introduced failures.
- P12: Publish a coverage map: applicable, implemented, unavailable, excluded, and not yet verified checks.

## 3. Continuous observation and check routing

- E01: Observe available file-change, tool-completion, command-output, build/test, service-start, and session events.
- E02: Handle dependency manifests, lockfiles, configuration, schemas, migrations, API contracts, prompts, and model/index artifacts as potentially broad-impact changes.
- E03: Detect changes made by users or other tools as well as the coding agent when the host exposes them.
- E04: Document visibility limits such as unsaved editor buffers and inaccessible remote resources.
- E05: Debounce rapid saves and incomplete writes; distinguish temporary editing states from stable defects.
- E06: Maintain an impact map connecting changed files to consumers, tests, routes, services, schemas, and downstream data.
- E07: Use fast relevant checks during editing; schedule browser, integration, load, and model checks at suitable checkpoints.
- E08: Cancel superseded jobs and invalidate results whose tested inputs have changed.
- E09: Detect changes during a check; use consistent snapshots where feasible or label mixed-version observations inconclusive.
- E10: Limit CPU, RAM, GPU, subprocesses, network calls, output, time, and optional model spending.
- E11: Prevent duplicate work, starvation of slower checks, recursive watcher loops, and collisions between sessions/worktrees.
- E12: Support restricted networks, offline checks, reconnects, interruptions, and resumable state.
- E13: Clean up descendant processes, temporary files, ports, locks, databases, and subscriptions on cancellation or shutdown.
- E14: Measure event-to-detection time separately from check duration and host delivery delay.

## 4. Host compatibility and delivery

- H01: Detect host, version, operating system, local/cloud orchestration and execution, available tools, sandbox policy, and supported events.
- H02: Publish tested compatibility levels: automatic same-turn delivery, checkpoint polling, manual invocation, or unsupported.
- H03: For supported local Codex workflows, trusted asynchronous command hooks can return findings at the next safe point in an active turn. This does not interrupt an in-flight model request or already-executed action. [Official hooks documentation](https://learn.chatgpt.com/docs/hooks)
- H04: Do not assume local command hooks work in cloud orchestration. Advertise cloud behavior only after testing the specific supported integration. [Official hooks documentation](https://learn.chatgpt.com/docs/hooks)
- H05: Where a product owns a supported Codex app-server connection, investigate structured tool-output delivery for active work. Do not claim access to arbitrary existing desktop sessions. [Official app-server documentation](https://learn.chatgpt.com/docs/app-server)
- H06: Keep detector output machine-originated; do not present it as a human instruction or promote raw untrusted logs into trusted instruction context.
- H07: Use explicit CLI/MCP checkpoints when a host lacks reliable live delivery, and make that fallback visible.
- H08: Detect delivery failure, stale session IDs, duplicates, reconnects, and host/version incompatibility.
- H09: A model endpoint without tools needs a harness that executes checks and returns findings. Model portability is different from host compatibility.
- H10: Support notifications to the agent separately from notifications to the human; keep human alerts configurable and limited to meaningful events.
- H11: Installing a skill does not automatically install runtimes, grant service access, or authorize hooks.

## 5. Finding and check contracts

- F01: Check outcomes: passed, failed, execution-error, skipped, blocked, not-applicable, inconclusive, cancelled, and superseded.
- F02: Finding classifications: confirmed application defect, confirmed check/environment failure, predicted risk, and inconclusive observation.
- F03: Separate severity, confidence, urgency, and whether the issue blocks the current task.
- F04: Include stable finding/rule IDs, detector version, repository/worktree/session, timestamp, input hashes, environment fingerprint, and source locations at the tested revision.
- F05: Include expected behavior and its basis: requirement, contract, invariant, or documented rule.
- F06: Include actual behavior, exact reproduction command/inputs, exit status, and bounded redacted evidence references.
- F07: Include likely cause as a hypothesis unless verified, impact, a concrete next action, and material alternative fixes.
- F08: Include a verification plan and the circumstances under which the finding would no longer apply.
- F09: Preserve test discovery/execution/skip counts, workload definitions, browser states, and other limits needed to interpret results.
- F10: Link screenshots, traces, network records, query plans, metrics, or fixtures rather than flooding model context.
- F11: Track lifecycle: new, acknowledged, investigating, fixing, verified-resolved, dismissed, accepted-risk, reopened, and stale.
- F12: Root-cause grouping: distinguish one unavailable database causing many test failures from many independent defects.
- F13: Deduplicate unchanged findings; suppressions require scope, reason, and optional expiry.
- F14: Never mark a check passed because its tool is missing, it timed out, it discovered zero tests, or it was never run.
- F15: Claim resolution only after relevant verification on current inputs. A patch or an agent's assertion is not verification.

## 6. Detector coverage catalog

Each implemented check declares supported versions, inputs, triggers, execution risk, dependencies, cost limits, evidence, and known blind spots. The catalog is a roadmap; listing a check does not mean it has been implemented.

### C01 — Environment, dependencies, and setup

Check runtime/compiler/package compatibility, lockfile consistency, native prerequisites, missing executables/imports, module formats, working directories, quoting, path case sensitivity, Unicode/spaces, environment configuration shape, permissions, port conflicts, service availability, proxies/DNS, and package-source access. Identify missing or rejected credentials without exposing their values. Separate installation failures from application defects.

### C02 — Source, static checks, and production builds

Run relevant parser/compiler/type/static-analysis checks. Inspect unresolved imports, incompatible APIs, unsafe conversions, dead paths where relevant, generated-code validity, cleanup errors, and differences between development and production builds. Prefer native diagnostic evidence over invented code-review warnings.

### C03 — Test infrastructure and discovery

Check runner configuration, collection, discovery counts, filters/skips, fixtures, browser binaries, database migrations, CI configuration, hanging handles/processes, order dependence, shared state, parallel collisions, and cleanup. Distinguish application, test, and environment failures. Investigate repeatability without hiding flaky tests through retries.

### C04 — Test quality and requirement coverage

Map important requirements to meaningful assertions and realistic cases. Cover unit, integration, contract, end-to-end, regression, negative/boundary, property-based, visual, accessibility, load, resilience, migration, restore, and AI evaluations as applicable. Inspect mock drift, swallowed failures, empty assertions, unreachable scenarios, and tests that merely copy implementation logic. Missing coverage is a risk, not proof of a defect. Targeted mutation tests are optional when justified.

### C05 — Business logic and input boundaries

Probe null/empty inputs, duplicates, invalid state transitions, limits, pagination, off-by-one errors, precision/currency, overflow, large identifiers, Unicode/encoding, locales, time zones, expiration, cancellation, repeated actions, partial completion, and resource cleanup. Expected results need a real business rule or invariant.

### C06 — Rendered UI and interaction

Check console errors, failing resources/API calls, routes, navigation, hydration, stale async state, responsiveness, long content, translations, fonts, zoom, clipping, scroll containers, sticky/fixed elements, stacking, dialogs/menus, and viewport overflow. Verify whether overlap hides content or intercepts input; intentional overlays must not be false alarms. Exercise loading, empty, error, denied, offline, success, and recovery states. Evidence includes route, viewport, browser, interaction sequence, screenshot, DOM geometry/hit test, and relevant network records.

### C07 — Accessibility

Check labels/names, semantics, measurable contrast, keyboard navigation, visible focus, focus restoration, modal behavior, announcements, touch targets, reduced motion, and alternative content. Identify aspects that require human review; automated scans cannot establish every accessibility requirement.

### C08 — APIs, integrations, and real-time protocols

Check schema validation, serialization/content types, error behavior, pagination, filtering, version compatibility, input/request limits, timeouts, bounded retries, cancellation, and contract drift. For webhooks check signatures, replay/duplicate delivery, ordering assumptions, and idempotency. For streaming/SSE/WebSockets check partial responses, disconnects, reconnection, cancellation, and resource release. Use controlled substitutes plus selected real sandbox checks.

### C09 — Identity, authorization, and tenant isolation

Exercise registration, login/logout, recovery, expiration/revocation, role changes, session/cookie behavior, CSRF/CORS, and object-level permissions. Use a role/action/resource matrix and multiple synthetic customers. Cover database queries, caches, files, search/RAG, background jobs, logs, and administrative routes. Administrator-only tests cannot establish isolation.

### C10 — Security and supply chain

Check injection, unsafe HTML, command execution, path traversal, deserialization, uploads, server-side requests, redirects, excessive privileges, secrets, sensitive logs, dependency advisories/provenance, installation execution, and artifact integrity. Label heuristics accurately and scope active security checks to authorized test environments. Do not equate a clean scan with proof of security.

### C11 — Databases

Check schema/relations/constraints, null handling, uniqueness, orphaned records, transactions/isolation, inconsistent derived data, N+1 queries, indexes/query plans, representative timings, pagination costs, hot rows, deadlocks, contention, pools, replica lag, and read-after-write behavior. Tie correctness claims to state invariants and performance claims to realistic data.

### C12 — Migrations, retention, and recovery

Check migration ordering, existing-data compatibility, backfills, long locks, rolling-release compatibility, destructive steps, reversibility limits, data export/deletion/retention, and deletion propagation into derived stores. Actually restore backups and verify post-restore integrity; backup existence alone is insufficient.

### C13 — Data pipelines

Check source availability, parser loss, malformed records, schema drift, duplicates, dropped rows, joins, ordering, timestamps, lineage, freshness, partial batches, offset/checkpoint handling, replay, retry duplication, reconciliation, and per-stage counts. Test claimed processing guarantees through observed outcomes.

### C14 — Queues, workers, schedules, and caching

Check poison messages, failed-job handling, bounded retries, dead-letter queues, starvation, queue growth/backpressure, job progress, cancellation/restart, scheduler time zones, duplicate schedules, cache keys/invalidation/expiration, sensitive cache sharing, stampedes, and consistency between stores.

### C15 — Concurrency

Probe simultaneous updates, lost writes, double submissions, inventory/payment duplication, uniqueness races, locks, shared mutable state, competing workers, stale results, retry side effects, and concurrent deployment. Use controlled concurrent reproductions; passing one small run does not prove race freedom.

### C16 — Traffic and capacity

Measure latency distributions, throughput, errors, queue depth, pools, CPU/RAM/GPU, storage, and network under an explicit request mix, payload/data size, concurrency, duration, cold/warm conditions, and cache behavior. Include load, spike, stress, and selected endurance tests. Verify the load generator is not the bottleneck. Inspect rate limits, overload protection, expensive endpoints, resource budgets, and scaling behavior. Do not claim high-traffic readiness from source inspection alone.

### C17 — Resilience and failure behavior

Test slow/unavailable dependencies, dropped connections, interrupted writes/jobs, failed workers, timeouts, bounded retries, retry storms, duplicate effects, queue growth, shutdown/draining, restart, fallback, and recovery. Check fallback against requirements: an explicit failure may be correct when substituting data would be harmful.

### C18 — Deployment, networking, and operations

Check build artifacts, images/manifests, runtime versions, production configuration, secret injection, resource limits, health/readiness, routing/base paths, proxy headers, HTTPS/DNS/certificates, staged/rolling releases, migration coordination, cache invalidation, rollback, logs/metrics/traces, correlation IDs, useful alerts, and source/artifact correspondence. Production testing requires its own explicit scope.

### C19 — RAG ingestion and retrieval

Check parsing/OCR loss, duplication, chunking, metadata, permissions, document versions, index freshness, deletion propagation, embedding dimension/runtime compatibility, keyword/semantic filters, reranking, relevance, context truncation/token budgets, and citation mapping. Inspect retrieved evidence separately from generation. Use synthetic private/public documents to test cross-customer leakage.

### C20 — AI applications and agents

Evaluate answer correctness, grounding, citations, unanswerable/conflicting cases, structured outputs, streaming, model/configuration changes, prompt injection, sensitive context leakage, tool permissions, tool-result handling, repeated loops, spending limits, and recovery. Use representative and adversarial cases, repeated evaluations where needed, and human review for uncertain judgments. An LLM judge supplies evidence, not an unquestionable truth label.

### C21 — Open-source/local model integration and serving

Check exact identity/revision, model card/license availability, provenance, artifact integrity, tokenizer/chat template, adapter/quantization compatibility, precision, architecture, runtime/drivers/hardware, remote-code loading, context limits, generation parameters, RAM/VRAM/KV-cache capacity, batching, concurrency, offloading, startup, streaming/cancellation, and out-of-memory recovery. Verify endpoint authentication, protocol/schema compatibility, queues, timeouts, quotas, isolation, and cost. Measured capacity and documented compatibility are different evidence classes.

### C22 — Training and fine-tuning projects

When explicitly relevant, check dataset rights/lineage, preprocessing, labeling, duplicates, train/validation/test separation, leakage/contamination, reproducibility/seeds, numerical instability/NaNs, loss behavior, gradient/optimization configuration, mixed precision, hardware/distributed synchronization, checkpoint/resume, evaluation validity, artifact versioning, training/inference compatibility, budgets, and deployment readiness. Keep expensive execution separately scoped. These checks do not authorize reuse of this private companion project as underlying-model training data.

### C23 — Specialized extensions

Add separate packs when a project requires mobile/offline behavior, desktop packaging, embedded hardware, real-time media, scientific numerical correctness, or other domain-specific verification. Unknown stacks should expose reduced coverage, not silently reuse unsuitable checks.

## 7. Repair and verification loop

- R01: Reproduce and classify the issue before selecting a remedy when feasible.
- R02: Use a causal chain to fix upstream causes rather than repeatedly patch downstream symptoms.
- R03: Offer the smallest suitable repair and explain material tradeoffs; preserve the user's feature intent.
- R04: Avoid silently weakening tests, suppressing errors, replacing real integrations with fake behavior, or adding unrelated infrastructure to obtain green results.
- R05: Hand evidence and relevant context to the coding agent; route to appropriate tools or specialized skills when actually available.
- R06: After changes, rerun focused verification; broaden testing when dependency impact or new evidence warrants it.
- R07: Validate that the original failure is fixed and important adjacent behavior still works.
- R08: Bound unsuccessful retries and escalate with a precise missing-input or blocked-check report.
- R09: Preserve failed approaches with their evidence when useful, so the agent does not loop through the same guesses.
- R10: Keep unresolved issues and accepted risks visible at completion, separately from verified fixes.

## 8. Memory, feedback, and improvement

- M01: Separate transient session state, project memory, workspace/team memory, and optional generic reusable knowledge.
- M02: Store useful facts such as verified commands, environment constraints, reproduced failures, accepted fixes, rejected alerts, and user preferences—not indiscriminate transcripts.
- M03: Scope memory by repository/customer; do not silently transfer private content between projects or users.
- M04: Record provenance, timestamp, tool/version, environment, evidence, and applicability for each lesson.
- M05: Distinguish observed facts, hypotheses, user preferences, and reviewed rules.
- M06: Detect conflicting/outdated memory; expire or revalidate assumptions after environment/dependency changes.
- M07: Retrieve only task-relevant memory within a context budget.
- M08: Let users inspect, correct, export, delete, disable, or configure retention for memory.
- M09: Protect memory against poisoned logs, hostile documents, malicious repository text, and unverified agent suggestions.
- M10: Propose improvements from verified outcomes, reproduce them, add suitable regression cases, evaluate on held-out cases, then promote versioned changes.
- M11: Keep installed policy/skill packages separate from mutable runtime state; avoid invisible rewriting of trusted instructions.
- M12: Allow optional learned detectors, ranking, retrieval, or trained components when explicitly selected; define the purpose, training method, datasets, execution location, budget, and rights first.
- M13: Track dataset/model lineage, privacy exclusions, transforms, retention, versioning, evaluation, deployment, rollback, and disable controls for trained components.
- M14: Permission to store memory does not imply permission to upload it, build a shared dataset, train a model, or distribute artifacts.
- M15: Memory and skill improvements do not update the underlying assistant's weights. Provider-side training/data use requires separate provider/account controls. [Official authentication and data-policy boundary](https://learn.chatgpt.com/docs/auth)
- M16: Improvement can occur during use or through scheduled maintenance; daily execution requires a configured scheduler and should report meaningful changes rather than unchanged status.
- M17: Maintain a challenge journal for both the coding agent and companion, including task context, symptoms, attempts, failed approaches, blockers, and evidence.
- M18: Distinguish unsuccessful attempts, hypotheses, and unresolved challenges from verified remedies.
- M19: Retrieve recurring applicable challenges/lessons with version, environment, provenance, retention, inspection, and deletion controls.
- M20: Diagnose companion failures and propose self-repair patches in an isolated package copy.
- M21: Evaluate self-repairs before activation, retain the last-known-good version, drain/restart affected workers, and support rollback.
- M22: Support optional bounded local training/ranking from authorized challenge outcomes, with dataset lineage and held-out evaluation.
- M23: Keep memory approval, executable rule changes, package updates, training, and sharing under separate explicit policies.
- M24: Convert demonstrated missed defects and recurring blockers into regression fixtures and measured improvements.

## 9. Privacy, execution safety, and ownership

- S01: Operate locally where feasible; telemetry and remote analysis are explicit features with documented data flows.
- S02: Minimize inputs and redact secrets before logs, screenshots, findings, memory, artifacts, model calls, or uploads.
- S03: Respect host sandbox, user authorization, workspace limits, and service policies; no automatic permission bypass.
- S04: Treat install scripts and tests as executable code that may mutate files, databases, or networks; isolate them appropriately.
- S05: Restrict paths, executable commands/arguments, network destinations, and production access; avoid shell interpolation of untrusted content.
- S06: Store credentials using suitable credential mechanisms; never commit them to the repository or diagnostic examples.
- S07: Validate external results against schemas and preserve data/instruction separation, especially in hook context.
- S08: Separate each customer's evidence, memory, subscriptions, and learned artifacts with access controls.
- S09: Offer retention, deletion/export, encryption where appropriate, and minimized audit records.
- S10: Respect ownership/license restrictions of model artifacts, dependencies, datasets, screenshots, and shared lessons.
- S11: Document provider data-use configuration; do not claim a skill overrides a provider's policies or that private GitHub visibility prevents all external processing.
- S12: Synthetic fixtures should cover secrets/cross-tenant leakage without needing real customer data.

## 10. Private repository and distribution

- D01: Private GitHub ownership and authorized collaborator/download access; do not make the repository public automatically.
- D02: Distributable Agent Skill entry point with focused name/description, scripts, and relevant references. [Official skill packaging documentation](https://learn.chatgpt.com/docs/build-skills)
- D03: Separate portable core, host adapters, project/check packs, schemas, fixtures/evaluations, and maintained documentation.
- D04: Include a quick start, runtime prerequisites, supported-version matrix, privacy/data-flow description, configuration examples, and limitations.
- D05: Choose an explicit license/distribution policy; private visibility alone does not grant reuse rights.
- D06: Support authenticated clone/release download and version pinning; keep credentials out of installed files.
- D07: Verify packaged artifacts, checksums/provenance, dependency versions, and executable check-pack trust.
- D08: Make setup idempotent, validate capabilities, preview configuration changes, preserve unrelated settings, and respect required hook trust.
- D09: Support safe upgrades, rollback, and uninstall without deleting user code or unrelated host configuration.
- D10: Keep runtime evidence/memory outside committed package files; document what uninstall retains or deletes.
- D11: Test Windows/macOS/Linux, spaces/Unicode, symlinks, containers, remote workspaces, monorepos, restricted networks, and lack of administrator privileges where advertised.
- D12: Cloud installation must put required software in the actual execution environment; downloading Markdown alone does not supply runtime capability.
- D13: Keep CI optional and local-first; document private-repository quotas and enforce spending limits before enabling hosted automation.

Suggested future repository areas: skills/coding-companion, core, adapters/hosts, adapters/projects, checks, contracts, evals, docs. Runtime state belongs in a configured data location, not the release tree. This layout is a proposal, not a created skill.

## 11. Testing the companion itself

- Q01: Unit/contract tests for event parsing, check manifests, result normalization, evidence references, lifecycle transitions, and configuration.
- Q02: Seeded-defect fixtures for supported compiler/test/browser/database/API/RAG/model scenarios.
- Q03: Clean and intentionally unusual fixtures to measure false positives, including legitimate overlays and valid explicit failure behavior.
- Q04: Host adapter tests for actual advertised same-session delivery and visible fallback behavior.
- Q05: Rapid changes/out-of-order completion tests to prevent stale alerts and false repair claims.
- Q06: Cancellation/restart/crash tests for process cleanup and consistent state.
- Q07: Missing tools/credentials/network tests to prove blocked checks never become successes.
- Q08: Multi-session/worktree/worker tests for shared ports, datasets, locks, and finding isolation.
- Q09: Secret-canary and hostile-output tests for redaction, prompt-injection resistance, and memory contamination.
- Q10: Memory inspection/deletion/expiry/export tests; separate development and benchmark memories.
- Q11: Installation/upgrade/uninstall tests that preserve unrelated host settings.
- Q12: Resource/latency/cost tests so monitoring overhead does not overwhelm coding work.
- Q13: Held-out evaluations for changes to checks, prompts, memory retrieval, or trained components.

## 12. Success metrics and fair comparison

- B01: Compare the same agent with and without the companion using identical repository snapshots, prompts, model/settings, tools, hardware, limits, and budgets.
- B02: Count the companion's compute, wall time, tokens, API spending, and user intervention in total cost.
- B03: Measure confirmed-defect precision/recall by category/severity, false alerts, correct localization, and missed important defects.
- B04: Measure verified completion, introduced regressions, time to detect, delivery delay, and time to verified repair.
- B05: Measure duplicate/stale alerts, unnecessary edits, interruptions, blocked/inconclusive coverage, and check execution errors.
- B06: Include realistic failures and clean cases; do not use only defects that were designed for the detector.
- B07: Keep improvement data separate from held-out evaluations; prevent memory or answer leakage between runs.
- B08: Repeat nondeterministic runs and use independent behavioral assertions; report uncertainty and compatibility limits.
- B09: Optional competitor comparisons must control model/version/settings and total budgets; subscription tier names alone do not identify a model.
- B10: Claim measured gains on tested tasks rather than universal superiority over another assistant.

## 13. Build order and release criteria

1. Establish portable contracts, project discovery, capability reporting, baseline checks, and a deterministic CLI.
2. Support one web stack end to end: environment, build/types, test discovery/results, browser smoke checks, structured evidence, and focused verification.
3. Add one tested live host adapter, revision-aware scheduling, cancellation, deduplication, local findings, and installation/removal.
4. Add scoped memory and evaluated improvements; benchmark the same agent with and without the companion.
5. Expand API/database, UI/accessibility, security, load/resilience, deployment/data-pipeline, RAG, and model-integration packs according to evidence and demand.
6. Add further hosts/clouds and optional learned components only with explicit compatibility and privacy contracts.

Release acceptance requires evidence that supported defects are found, clean cases stay quiet, advertised live delivery works, stale findings are rejected, missing checks stay visibly blocked, repairs are verified, secrets remain protected, jobs clean up, configuration survives uninstall, memory is controllable, and paired held-out benchmarks demonstrate benefit.

## Example behavior during a coding session

At elapsed 21:42 a completed browser check might report: “Confirmed interaction defect on current component hash: at viewport 390×844, the sticky footer intercepts clicks on the form submit button. Screenshot and hit-test evidence attached. Reproduce with this route and interaction. Inspect the footer/container positioning; then rerun the same check.” The location, timing, and numbers here are illustrative, not observations from a real application.

A capacity check might instead report: “Predicted capacity risk: requests can open more database connections than the configured pool permits under the stated peak workload. No load failure has been reproduced. Run the isolated workload to measure queueing and errors.”

The coding agent selects and applies a fix. The companion reruns the relevant check on current inputs, records the outcome, and only then marks the finding verified-resolved. Any reusable lesson retains its evidence and scope before promotion.
