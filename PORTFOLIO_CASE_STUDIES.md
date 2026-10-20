# Coding Companion: portfolio case studies

These are engineering case studies from one project, rather than separate client engagements. They describe implemented mechanisms and documented local validation. They do not claim measured customer adoption, productivity gains, or production incident outcomes. Prepared from the local source and implementation records on 20 October 2026; validation was not rerun for this writing task.

## Project overview

Coding Companion is a local Python tool that helps coding agents check their work, investigate findings, and verify repairs against current project files. Its core runs without a paid service, hosted database, or model API. The implementation combines a CLI, SQLite state, project discovery, background coordination, approved native tool execution, private memory, and optional agent integration.

## 1. Making repair verification resistant to false success

### Problem

A successful command can create misleading confidence: it may execute no tests, read an outdated report, or pass only because someone weakened an assertion. Coding workflows need evidence that the original problem was repaired under the original acceptance criteria.

### Solution

Coding Companion records findings with input identities and verifies them against current files. Native test probes require usable JUnit evidence and nonzero test cases. Verification preserves original expectations, required failing cases, and recognized Python and JavaScript/TypeScript test content. Missing reports, stale results, timeouts, truncated evidence, and zero-test runs remain incomplete or failed.

### Demonstrated outcome

The implementation records describe real web-tool fixtures in which test, type, and lint failures were detected, repairs were verified, and weakened assertions remained unresolved. This establishes a local verification workflow that distinguishes a supported repair from a misleading green command. It does not establish a reduction in production defects.

### Portfolio takeaway

Built an evidence-based repair verification system that checks current inputs and preserves acceptance criteria before declaring a defect resolved.

Evidence: `README.md` sections on verification and native tools; `IMPLEMENTATION_STATUS.md`; `tests/test_runtime.py`; `tests/test_web.py`; `tools/validate_web.py`.

## 2. Coordinating background checks during rapid code changes

### Problem

A watcher and multiple CLI clients can race over the same project. Rapid saves can schedule redundant work, old results can describe obsolete files, and abandoned child processes can keep running after a check ends.

### Solution

The runtime uses one OS-backed coordinator lock per project, a durable mailbox, bounded worker lanes with aging, and change debouncing/coalescing. Snapshot identities connect observations to the files they describe. Native verification hashes current inputs. Stop requests cancel native jobs. On Windows, processes launch suspended, enter a Job Object, and then resume so ordinary descendants can be cleaned up when the job ends.

### Demonstrated outcome

The implementation records report watcher/client coordination tests and Windows descendant cleanup fixtures. The runtime also handles source returning to previously observed bytes while keeping the latest observed snapshot identity. Broader load and soak benchmarks remain open.

### Portfolio takeaway

Designed durable coordination and process lifecycle controls to keep background validation aligned with changing project files.

Evidence: `README.md` watch/checkpoint section; `IMPLEMENTATION_STATUS.md` P2 and snapshot notes; `tests/test_runtime.py`.

## 3. Connecting validation to a real JavaScript and TypeScript toolchain

### Problem

Generic syntax checks cannot establish whether a web project type-checks, passes lint rules, builds, or passes its tests. Running arbitrary package scripts also makes the executed command and its side effects harder to review.

### Solution

Project discovery proposes direct installed TypeScript, ESLint, Vite, and Vitest commands for review. Approvals bind the command, executable, and input hashes. Node tools run through a packaged wrapper without a shell; build output and incremental metadata use scratch storage. Changed-file routing follows supported local imports, aliases, and package exports, with broader scanning when relationships cannot be resolved safely.

### Demonstrated outcome

Documented local validation exercised all four real tools in an owned synthetic fixture, detected seeded failures, verified repairs, and finished with all four commands passing. The resolver is lexical and bounded; it does not claim full JavaScript dependency resolution or exhaustive freezing of transitive dependencies.

### Portfolio takeaway

Integrated real web development tools into a reviewable validation pipeline with provenance checks and conservative dependency routing.

Evidence: `README.md` native project tools section; `IMPLEMENTATION_STATUS.md` P0/P1 and historical web validation; `tests/test_web.py`; `tools/validate_web.py`.

## 4. Testing authorization and concurrent API behavior

### Problem

An API can return valid-looking responses while exposing another tenant's data or losing updates under concurrent requests. Individual endpoint checks need explicit actor/resource expectations and post-request invariants to catch those failures.

### Solution

The scenario probe runs declared authorization matrices and sequential or concurrent loopback HTTP steps. Every actor/resource pair specifies its expected result. Parallel batches complete before subsequent invariant checks. Request counts are bounded, active methods require explicit permission, and native execution requires exact approval. Repair verification retains the original scenario expectations.

### Demonstrated outcome

Version 0.4 records seeded tenant-leak and lost-update fixtures, current repair verification, and rejection of weakened contracts. These demonstrate detection of the specified defects in controlled local scenarios; they do not certify a production service's security or concurrency correctness.

### Portfolio takeaway

Built scenario-based API checks that make tenant boundaries and concurrent-update expectations executable and verifiable.

Evidence: `IMPLEMENTATION_STATUS.md` version 0.4 notes; `skills/coding-companion/references/scenario-probes.md`; `tests/test_scenarios.py`.

## 5. Retaining useful repair knowledge with privacy controls

### Problem

Past repairs can help future work, but blindly retaining source, transcripts, or unverified suggestions risks exposing project data and recycling incorrect advice. Deleting a lesson also needs to affect derived state and cached responses.

### Solution

Coding Companion stores private project-scoped lessons after successful current verification. Retrieval returns at most five nonexpired verified lessons. Export and deletion are explicit operations. Withdrawal invalidates derived lessons, candidates, and learned components, removes owned evidence and registered owned backups, scrubs live content and replay excerpts, and advances a retrieval epoch. External exports are tracked for separate removal.

### Demonstrated outcome

The implementation provides bounded, inspectable memory and deletion propagation without storing raw source or chat transcripts as lessons. It explicitly distinguishes local deletion from removal of external copies or model unlearning. Productivity improvements from memory have not been established by customer benchmarks.

### Portfolio takeaway

Designed project-scoped repair memory with verification, retention, export tracking, and deletion propagation across derived artifacts.

Evidence: `README.md` memory and improvement section; `IMPLEMENTATION_STATUS.md` privacy withdrawal notes; `tests/test_features.py`.

## Recommended portfolio structure

Publish one main project page titled **Coding Companion — Evidence-Based Validation for Coding Agents**. Use case study 1 as the lead story and cases 2–5 as supporting engineering deep dives. This presents one coherent product while showing reliability engineering, developer tooling, API testing, and privacy design.

Suggested project summary:

> Built a local Python companion that helps coding agents discover project checks, run reviewed tools, investigate defects, and verify repairs against current files. The system combines durable background coordination, acceptance-criteria preservation, API scenario testing, and private project memory. Local fixtures demonstrate specific defect detection and repair workflows, with explicit coverage limits.

Repository: https://github.com/marzukulamin/coding-companion. The repository is intended to remain private initially; portfolio visitors need access to view its source.
