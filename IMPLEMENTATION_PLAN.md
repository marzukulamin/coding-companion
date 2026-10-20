# Implementation plan and requirement traceability

Status: target traceability inventory for the implemented 0.4 runtime. IMPLEMENTATION_STATUS.md records operational capabilities and release gates. The machine-readable design/requirements.json records individual implementation evidence and remaining work; validate it with tools/validate_requirements.py. Original requirement wording below is preserved, including early proposed-interface wording. Implemented CLI behavior is documented in README.md. A requirement becomes complete only with reviewed code and its observable acceptance checks.

## Build phases

| Phase | Modules and deliverables | Completion gate |
|---|---|---|
| P0 | Contracts, config, storage/migrations, doctor, static discovery, CLI plan | Offline setup and schema/contract/error cases |
| P1 | Native check adapters, parsers/counts, snapshots, findings, verification, challenges, memory | Seeded/clean/blocked cases and current-revision verified repair |
| P2 | Mailbox, coordinator, scheduler, budgets, watch, cancellation, recovery | Crash replay, stale results, process cleanup and bounded load |
| P3 | Portable skill, MCP/host adapters, installer/removal, OS matrix | Actual host delivery/fallback and configuration preservation |
| P4 | Expanded detector packs and paired evaluation | Each advertised check has operational fixtures; held-out measured benefit |
| P5 | Candidate improvement, self-repair, activation/rollback, optional local training | Independent evaluation, privacy lineage, recovery and LKG rollback |

No phase authorizes publishing the private repository, installing a scheduler, accessing production, paying for services, or training on an unspecified dataset.

## Requirement coverage

The original requirement wording is preserved below. Architecture section numbers refer to ARCHITECTURE.md. The acceptance column identifies the test family; each implementation task must instantiate its precise behavior, inputs, and assertions.

| ID | Requirement | Implementation owner | Architecture sections | Phase | Acceptance family |
|---|---|---|---|---|---|
| A01 | Portable skill: concise instructions for selecting checks, interpreting findings, requesting evidence, and verifying repairs. Load specialized guidance only when applicable. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A02 | Model-independent diagnostic core: execute checks and normalize results without requiring an LLM for basic operation. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A03 | Project adapters: map technologies and existing project commands to suitable checks; do not assume every project uses npm, Python, or one framework. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A04 | Host adapters: integrate with each agent's documented events, tools, permissions, and notification mechanism. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A05 | CLI interface: support discovery, preflight, scan, watch, status, finding inspection, verification, and health checks. These are proposed interfaces, not implemented commands. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A06 | Optional MCP interface: expose structured tools and findings to compatible agent hosts; MCP availability alone does not establish unsolicited same-turn delivery. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A07 | Scheduler: prioritize relevant work, limit resource usage, and coordinate repeated requests. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A08 | Evidence store: retain bounded, redacted diagnostics separately from source code and release packages. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A09 | Memory and improvement subsystem: record scoped verified lessons, evaluate updates, and version changes. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A10 | Mutation ownership: the companion reports and proposes; the coding agent normally edits. Any companion repair mode must avoid concurrent edits and verify every patch. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A11 | Optional model analysis: use for hypothesis generation or difficult interpretation, keep its output labeled, and continue deterministic checks if the model service fails. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A12 | Optional UI: show coverage, active checks, actionable findings, evidence, budgets, and delivery health without making a dashboard necessary for core operation. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A13 | Version 1 has no frontend; CLI, structured tools, and Markdown reports provide agent and human interfaces. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A14 | Require no paid service, hosted backend/database, or independent model API; retain a local/offline operating mode. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| A15 | Language-independent probe contracts and explicit host capability tiers provide portability without claiming that a model lacking tools can execute checks. | Core/packaging/host contracts | 1–5, 14, 22 | P0/P3 | Boundary and compatibility fixtures |
| P01 | Identify repository/worktree boundaries, monorepos, packages, languages, frameworks, runtimes, entry points, and generated files. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P02 | Identify build, test, lint, formatting, migration, startup, and deployment commands from actual project configuration. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P03 | Discover databases, queues, caches, object stores, APIs, model endpoints, and required services. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P04 | Record permitted environments and actions; distinguish local development, isolated tests, staging, and production. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P05 | Read relevant project conventions and user requirements without treating arbitrary source text as trusted policy. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P06 | Capture acceptance criteria, important user journeys, business invariants, and authorization rules where provided. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P07 | Capture traffic assumptions: request mix, concurrency, data sizes, peak load, latency/error targets, and infrastructure resources. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P08 | Capture supported browsers, viewports, devices, languages, time zones, and accessibility expectations. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P09 | Capture model identity, revision, runtime, hardware, context limits, and intended inference or training use where applicable. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P10 | Record unknown requirements explicitly; correct business behavior cannot always be inferred from existing code. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P11 | Create an initial baseline so existing failures are distinguishable from newly introduced failures. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| P12 | Publish a coverage map: applicable, implemented, unavailable, excluded, and not yet verified checks. | Discovery/config/impact graph | 9, 12, 21 | P0 | Representative manifest and unknown-stack fixtures |
| E01 | Observe available file-change, tool-completion, command-output, build/test, service-start, and session events. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E02 | Handle dependency manifests, lockfiles, configuration, schemas, migrations, API contracts, prompts, and model/index artifacts as potentially broad-impact changes. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E03 | Detect changes made by users or other tools as well as the coding agent when the host exposes them. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E04 | Document visibility limits such as unsaved editor buffers and inaccessible remote resources. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E05 | Debounce rapid saves and incomplete writes; distinguish temporary editing states from stable defects. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E06 | Maintain an impact map connecting changed files to consumers, tests, routes, services, schemas, and downstream data. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E07 | Use fast relevant checks during editing; schedule browser, integration, load, and model checks at suitable checkpoints. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E08 | Cancel superseded jobs and invalidate results whose tested inputs have changed. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E09 | Detect changes during a check; use consistent snapshots where feasible or label mixed-version observations inconclusive. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E10 | Limit CPU, RAM, GPU, subprocesses, network calls, output, time, and optional model spending. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E11 | Prevent duplicate work, starvation of slower checks, recursive watcher loops, and collisions between sessions/worktrees. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E12 | Support restricted networks, offline checks, reconnects, interruptions, and resumable state. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E13 | Clean up descendant processes, temporary files, ports, locks, databases, and subscriptions on cancellation or shutdown. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| E14 | Measure event-to-detection time separately from check duration and host delivery delay. | Coordinator/mailbox/scheduler/snapshots | 6–10, 15 | P2 | Replay, rapid-save, cancellation and resource tests |
| H01 | Detect host, version, operating system, local/cloud orchestration and execution, available tools, sandbox policy, and supported events. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H02 | Publish tested compatibility levels: automatic same-turn delivery, checkpoint polling, manual invocation, or unsupported. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H03 | For supported local Codex workflows, trusted asynchronous command hooks can return findings at the next safe point in an active turn. This does not interrupt an in-flight model request or already-executed action. [Official hooks documentation](https://learn.chatgpt.com/docs/hooks) | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H04 | Do not assume local command hooks work in cloud orchestration. Advertise cloud behavior only after testing the specific supported integration. [Official hooks documentation](https://learn.chatgpt.com/docs/hooks) | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H05 | Where a product owns a supported Codex app-server connection, investigate structured tool-output delivery for active work. Do not claim access to arbitrary existing desktop sessions. [Official app-server documentation](https://learn.chatgpt.com/docs/app-server) | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H06 | Keep detector output machine-originated; do not present it as a human instruction or promote raw untrusted logs into trusted instruction context. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H07 | Use explicit CLI/MCP checkpoints when a host lacks reliable live delivery, and make that fallback visible. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H08 | Detect delivery failure, stale session IDs, duplicates, reconnects, and host/version incompatibility. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H09 | A model endpoint without tools needs a harness that executes checks and returns findings. Model portability is different from host compatibility. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H10 | Support notifications to the agent separately from notifications to the human; keep human alerts configurable and limited to meaningful events. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| H11 | Installing a skill does not automatically install runtimes, grant service access, or authorize hooks. | Host adapters/capabilities/delivery | 5, 14–15 | P3 | Real host/version delivery and fallback tests |
| F01 | Check outcomes: passed, failed, execution-error, skipped, blocked, not-applicable, inconclusive, cancelled, and superseded. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F02 | Finding classifications: confirmed application defect, confirmed check/environment failure, predicted risk, and inconclusive observation. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F03 | Separate severity, confidence, urgency, and whether the issue blocks the current task. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F04 | Include stable finding/rule IDs, detector version, repository/worktree/session, timestamp, input hashes, environment fingerprint, and source locations at the tested revision. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F05 | Include expected behavior and its basis: requirement, contract, invariant, or documented rule. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F06 | Include actual behavior, exact reproduction command/inputs, exit status, and bounded redacted evidence references. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F07 | Include likely cause as a hypothesis unless verified, impact, a concrete next action, and material alternative fixes. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F08 | Include a verification plan and the circumstances under which the finding would no longer apply. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F09 | Preserve test discovery/execution/skip counts, workload definitions, browser states, and other limits needed to interpret results. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F10 | Link screenshots, traces, network records, query plans, metrics, or fixtures rather than flooding model context. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F11 | Track lifecycle: new, acknowledged, investigating, fixing, verified-resolved, dismissed, accepted-risk, reopened, and stale. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F12 | Root-cause grouping: distinguish one unavailable database causing many test failures from many independent defects. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F13 | Deduplicate unchanged findings; suppressions require scope, reason, and optional expiry. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F14 | Never mark a check passed because its tool is missing, it timed out, it discovered zero tests, or it was never run. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| F15 | Claim resolution only after relevant verification on current inputs. A patch or an agent's assertion is not verification. | Contracts/normalization/storage/findings | 8, 11, 13–14 | P0/P1 | Typed outcomes, freshness and evidence fixtures |
| R01 | Reproduce and classify the issue before selecting a remedy when feasible. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R02 | Use a causal chain to fix upstream causes rather than repeatedly patch downstream symptoms. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R03 | Offer the smallest suitable repair and explain material tradeoffs; preserve the user's feature intent. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R04 | Avoid silently weakening tests, suppressing errors, replacing real integrations with fake behavior, or adding unrelated infrastructure to obtain green results. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R05 | Hand evidence and relevant context to the coding agent; route to appropriate tools or specialized skills when actually available. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R06 | After changes, rerun focused verification; broaden testing when dependency impact or new evidence warrants it. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R07 | Validate that the original failure is fixed and important adjacent behavior still works. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R08 | Bound unsuccessful retries and escalate with a precise missing-input or blocked-check report. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R09 | Preserve failed approaches with their evidence when useful, so the agent does not loop through the same guesses. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| R10 | Keep unresolved issues and accepted risks visible at completion, separately from verified fixes. | Repair/verification/challenge workflow | 13, 16 | P1 | Reproduce, fix, verify, regression and retry cases |
| M01 | Separate transient session state, project memory, workspace/team memory, and optional generic reusable knowledge. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M02 | Store useful facts such as verified commands, environment constraints, reproduced failures, accepted fixes, rejected alerts, and user preferences—not indiscriminate transcripts. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M03 | Scope memory by repository/customer; do not silently transfer private content between projects or users. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M04 | Record provenance, timestamp, tool/version, environment, evidence, and applicability for each lesson. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M05 | Distinguish observed facts, hypotheses, user preferences, and reviewed rules. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M06 | Detect conflicting/outdated memory; expire or revalidate assumptions after environment/dependency changes. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M07 | Retrieve only task-relevant memory within a context budget. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M08 | Let users inspect, correct, export, delete, disable, or configure retention for memory. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M09 | Protect memory against poisoned logs, hostile documents, malicious repository text, and unverified agent suggestions. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M10 | Propose improvements from verified outcomes, reproduce them, add suitable regression cases, evaluate on held-out cases, then promote versioned changes. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M11 | Keep installed policy/skill packages separate from mutable runtime state; avoid invisible rewriting of trusted instructions. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M12 | Allow optional learned detectors, ranking, retrieval, or trained components when explicitly selected; define the purpose, training method, datasets, execution location, budget, and rights first. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M13 | Track dataset/model lineage, privacy exclusions, transforms, retention, versioning, evaluation, deployment, rollback, and disable controls for trained components. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M14 | Permission to store memory does not imply permission to upload it, build a shared dataset, train a model, or distribute artifacts. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M15 | Memory and skill improvements do not update the underlying assistant's weights. Provider-side training/data use requires separate provider/account controls. [Official authentication and data-policy boundary](https://learn.chatgpt.com/docs/auth) | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M16 | Improvement can occur during use or through scheduled maintenance; daily execution requires a configured scheduler and should report meaningful changes rather than unchanged status. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M17 | Maintain a challenge journal for both the coding agent and companion, including task context, symptoms, attempts, failed approaches, blockers, and evidence. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M18 | Distinguish unsuccessful attempts, hypotheses, and unresolved challenges from verified remedies. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M19 | Retrieve recurring applicable challenges/lessons with version, environment, provenance, retention, inspection, and deletion controls. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M20 | Diagnose companion failures and propose self-repair patches in an isolated package copy. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M21 | Evaluate self-repairs before activation, retain the last-known-good version, drain/restart affected workers, and support rollback. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M22 | Support optional bounded local training/ranking from authorized challenge outcomes, with dataset lineage and held-out evaluation. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M23 | Keep memory approval, executable rule changes, package updates, training, and sharing under separate explicit policies. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| M24 | Convert demonstrated missed defects and recurring blockers into regression fixtures and measured improvements. | Challenges/memory/improvement | 16–17, 19 | P1/P5 | Journal, provenance, deletion, poisoning and rollback cases |
| S01 | Operate locally where feasible; telemetry and remote analysis are explicit features with documented data flows. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S02 | Minimize inputs and redact secrets before logs, screenshots, findings, memory, artifacts, model calls, or uploads. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S03 | Respect host sandbox, user authorization, workspace limits, and service policies; no automatic permission bypass. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S04 | Treat install scripts and tests as executable code that may mutate files, databases, or networks; isolate them appropriately. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S05 | Restrict paths, executable commands/arguments, network destinations, and production access; avoid shell interpolation of untrusted content. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S06 | Store credentials using suitable credential mechanisms; never commit them to the repository or diagnostic examples. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S07 | Validate external results against schemas and preserve data/instruction separation, especially in hook context. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S08 | Separate each customer's evidence, memory, subscriptions, and learned artifacts with access controls. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S09 | Offer retention, deletion/export, encryption where appropriate, and minimized audit records. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S10 | Respect ownership/license restrictions of model artifacts, dependencies, datasets, screenshots, and shared lessons. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S11 | Document provider data-use configuration; do not claim a skill overrides a provider's policies or that private GitHub visibility prevents all external processing. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| S12 | Synthetic fixtures should cover secrets/cross-tenant leakage without needing real customer data. | Policy/runner/redaction/isolation | 11, 19, 21 | P0–P5 | Secrets, path, permission and side-effect cases |
| D01 | Private GitHub ownership and authorized collaborator/download access; do not make the repository public automatically. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D02 | Distributable Agent Skill entry point with focused name/description, scripts, and relevant references. [Official skill packaging documentation](https://learn.chatgpt.com/docs/build-skills) | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D03 | Separate portable core, host adapters, project/check packs, schemas, fixtures/evaluations, and maintained documentation. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D04 | Include a quick start, runtime prerequisites, supported-version matrix, privacy/data-flow description, configuration examples, and limitations. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D05 | Choose an explicit license/distribution policy; private visibility alone does not grant reuse rights. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D06 | Support authenticated clone/release download and version pinning; keep credentials out of installed files. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D07 | Verify packaged artifacts, checksums/provenance, dependency versions, and executable check-pack trust. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D08 | Make setup idempotent, validate capabilities, preview configuration changes, preserve unrelated settings, and respect required hook trust. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D09 | Support safe upgrades, rollback, and uninstall without deleting user code or unrelated host configuration. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D10 | Keep runtime evidence/memory outside committed package files; document what uninstall retains or deletes. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D11 | Test Windows/macOS/Linux, spaces/Unicode, symlinks, containers, remote workspaces, monorepos, restricted networks, and lack of administrator privileges where advertised. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D12 | Cloud installation must put required software in the actual execution environment; downloading Markdown alone does not supply runtime capability. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| D13 | Keep CI optional and local-first; document private-repository quotas and enforce spending limits before enabling hosted automation. | Distribution/installer/compatibility/cost | 2, 5, 15, 22 | P3 | Private package, upgrade/uninstall and spending-policy cases |
| Q01 | Unit/contract tests for event parsing, check manifests, result normalization, evidence references, lifecycle transitions, and configuration. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q02 | Seeded-defect fixtures for supported compiler/test/browser/database/API/RAG/model scenarios. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q03 | Clean and intentionally unusual fixtures to measure false positives, including legitimate overlays and valid explicit failure behavior. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q04 | Host adapter tests for actual advertised same-session delivery and visible fallback behavior. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q05 | Rapid changes/out-of-order completion tests to prevent stale alerts and false repair claims. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q06 | Cancellation/restart/crash tests for process cleanup and consistent state. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q07 | Missing tools/credentials/network tests to prove blocked checks never become successes. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q08 | Multi-session/worktree/worker tests for shared ports, datasets, locks, and finding isolation. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q09 | Secret-canary and hostile-output tests for redaction, prompt-injection resistance, and memory contamination. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q10 | Memory inspection/deletion/expiry/export tests; separate development and benchmark memories. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q11 | Installation/upgrade/uninstall tests that preserve unrelated host settings. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q12 | Resource/latency/cost tests so monitoring overhead does not overwhelm coding work. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| Q13 | Held-out evaluations for changes to checks, prompts, memory retrieval, or trained components. | Test fixtures and companion reliability | 20, 23 | Every phase | Independent observable behavior and failure cases |
| B01 | Compare the same agent with and without the companion using identical repository snapshots, prompts, model/settings, tools, hardware, limits, and budgets. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B02 | Count the companion's compute, wall time, tokens, API spending, and user intervention in total cost. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B03 | Measure confirmed-defect precision/recall by category/severity, false alerts, correct localization, and missed important defects. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B04 | Measure verified completion, introduced regressions, time to detect, delivery delay, and time to verified repair. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B05 | Measure duplicate/stale alerts, unnecessary edits, interruptions, blocked/inconclusive coverage, and check execution errors. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B06 | Include realistic failures and clean cases; do not use only defects that were designed for the detector. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B07 | Keep improvement data separate from held-out evaluations; prevent memory or answer leakage between runs. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B08 | Repeat nondeterministic runs and use independent behavioral assertions; report uncertainty and compatibility limits. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B09 | Optional competitor comparisons must control model/version/settings and total budgets; subscription tier names alone do not identify a model. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |
| B10 | Claim measured gains on tested tasks rather than universal superiority over another assistant. | Held-out paired evaluation | 23 | P4 | Equal-budget measured quality/overhead/regression benchmark |

## Detector pack coverage

Every pack is specified in architecture section 12 and detailed in COMPANION_REQUIREMENTS.md. Packs are planned until their prerequisites, concrete adapters, seeded failures, clean fixtures, blocked/parser cases, permissions and cost limits are implemented.

| Pack | Owner | Phase | Required proof |
|---|---|---|---|
| C01 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C02 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C03 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C04 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C05 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C06 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C07 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C08 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C09 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C10 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C11 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C12 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C13 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C14 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C15 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C16 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C17 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C18 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C19 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C20 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C21 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C22 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |
| C23 | checks/adapters/projects | P1/P4 | Failure + clean + missing tool + invalid evidence + current verification |

## Implementation invariants to preserve

- The coordinator alone owns writes and migrations; ledger and DDL commit atomically.
- Every observation matches its run/snapshot; every delivery matches its observation/finding.
- Events create/register required sessions atomically; event/request ID collisions cannot overwrite responses.
- Result freshness and required test counts are runtime proofs, not only schema enums.
- Resolved challenges require suitable verified current evidence.
- Candidate patches cannot edit their independently pinned evaluator or held-out acceptance set.
- Activation uses exact package/artifact hashes and DB-compatible rollback.
- Deletion/consent withdrawal propagates to lessons, datasets, exports and learned components.
- User data-use prohibitions and host permissions cannot be relaxed by repository/session overrides.
- Typed protocol validators and exported schemas must share conformance fixtures.

## Current validation boundary

tools/validate_architecture.py checks design syntax, known contract semantics, SQL integrity/constraints, optional FTS synchronization, migration atomicity, backup restoration, privacy/relation invariants, configuration defaults, and coverage of every requirement ID.

It is an architecture validation utility. It does not establish working watchers, supported live host integration, successful real-project checks, actual process isolation, maintenance automation, detector accuracy, or product superiority. Those need the runtime and acceptance phases above.
