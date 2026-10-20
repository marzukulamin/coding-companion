# Implementation gap audit

12 October 2026. Review of requirements, implementation status, source adapters,
detector catalog, packaging metadata, compatibility records and local test execution.
This is a scoped audit, not an exhaustive correctness or security certification.

## Follow-up implementation in 0.4

- Added design/requirements.json covering all 172 IDs, a reference/completion validator,
  and regression cases for missing/duplicate/drifted requirements and invalid evidence.
- Added bounded local tsconfig/jsconfig path aliases, local JSONC inheritance and
  unconditional local workspace exports. Unsupported resolution remains a full scan.
- Added browser focus-state, keyboard actions and visible-center pointer hit testing,
  with five real Chrome regressions including intentional overlays.
- Added explicit loopback actor/resource matrices and bounded concurrent HTTP steps,
  seeded leak/lost-update cases, current native repair verification and rejection of
  weakened contracts. This covers selected C09/C15 scenarios, not their entire catalog.
- Applied the owner's selected MIT license and included it in both release artifacts.
- Added reproducible release gates with input/log hashes and manual CI evidence retention.

Remaining catalog, host, isolation and independent project/platform certification work
is still tracked below and in the ledger. Automatic patch generation remains unsupported.

## Highest-priority work

| Priority | Gap | Evidence and concrete completion gate |
|---|---|---|
| 1 | Requirement-to-code-to-test tracking | IMPLEMENTATION_PLAN.md maps requirements to phases and acceptance families, but does not identify concrete runtime functions, tests or per-requirement completion. Add a machine-readable ledger with implemented/partial/deferred status, source/test references and explicit missing acceptance cases. Validate references and prevent marking a requirement complete solely because its architecture exists. |
| 1 | Live host integration and delivery | hooks.py supplies local Codex configuration and bounded static-check output. Actual active-turn delivery remains unverified in IMPLEMENTATION_STATUS.md; a Claude-specific delivery adapter is not established by this source review. Prove seeded finding delivery and repair in each advertised real host, including duplicates, stale results and visible fallback. |
| 1 | Portability certification | The manual workflow defines three operating systems and Python 3.12–3.14, but recorded validation covers Windows/Python 3.13. Run the matrix and retain results; add explicitly scoped remote/container/restricted-network fixtures before advertising them. |
| 1 | Real-project and effectiveness evidence | Recorded browser/web integrations are synthetic fixtures. evaluation.py and matched-trial analysis do not themselves produce independent agent trials. Run representative held-out clean/defective projects; measure missed defects, false alerts, verified repairs, overhead and uncertainty. |
| 2 | Broader project routing | impact.py uses lexical JS/TS relationships with conservative fallbacks. Add alias/workspace/package-export resolution and broader language graphs with deletion/configuration/ambiguous-import regression cases. adapters.py already proposes Go/Rust/.NET/Java commands; proposals are not complete tool-specific diagnostic adapters or certification. |
| 2 | Remaining detector scope | packs.py contains narrow heuristics and supplied-evidence contracts. Implement independently scoped live packs for authorization/tenant isolation, API streaming/webhooks, migration/restore, queue/cache behavior, concurrency, resilience and deployment. Each needs a seeded failure, clean case, missing prerequisite, invalid evidence and current repair verification. |
| 2 | UI/accessibility depth | Current HTML checks cover alt attributes and duplicate IDs; the browser helper checks declared bounded assertions. Add interaction sequences, modal/focus restoration, hit testing, contrast and accessible-name checks with intentional-overlay clean cases. |
| 2 | Resource and trust hardening | Status explicitly leaves long-running static-parser interruption and broader load/soak benchmarks open. Native execution does not isolate filesystem/network authority. Implement verified sandbox execution before allowing untrusted candidate evaluation; test cancellation and resource bounds independently. Node transitive dependencies/external environment provenance also remain incomplete. |
| 3 | Optional model-analysis adapter | A11 calls for labeled hypothesis generation with deterministic fallback. Captured AI contracts and local ranking do not implement a general model-analysis provider adapter. Keep this optional; add failure/budget/data-use controls if the feature is retained. |
| 3 | Automatic improvement execution | P5 supports supplied external evaluation evidence and reviewed package activation. It explicitly does not generate patches or run independent isolated candidate evaluation. Build an isolated evaluator and held-out gate before adding automatic patch generation. |
| 3 | Distribution policy and delivery | D05 requires explicit reuse/distribution rights. No LICENSE file or project license metadata was found; policy choice remains an owner decision. D06 authenticated private release download/version pinning is not established by local ZIP/wheel building. This checkout also has no Git repository, so private remote settings/history cannot be audited here. |

## Easily overlooked documentation gaps

- design/compatibility.json still marks all entries documented_not_tested. Keep
  design targets distinct from measured runtime adapter certification; record the
  successful MCP stdio fixture without implying certification of a real agent host.
- IMPLEMENTATION_PLAN.md still contains early-stage wording, including A05's
  description of CLI commands as proposed. Reconcile it with the current runtime.
- Do not count captured RAG/model/training/performance records as live retrieval,
  model serving, training or load execution. Preserve this distinction in the ledger.
- Generated dist/validation.json records prior results; it is not proof that a fresh
  rerun passed in the present environment.

## Suggested next milestone

Start with the requirement ledger and fresh reproducible validation. Then establish
one end-to-end real host delivery path and real-project repair loop. Choose additional
detectors from actual target projects; avoid treating all 23 catalog families as a
single release requirement.

## Fresh validation

The initial restricted run could not create test projects in the sandbox's temporary
directory. With TEMP/TMP redirected to workspace storage, 103 tests ran: 101 passed,
one loopback HTTP fixture failed and one package-launch fixture errored. Both affected
tests passed when rerun with approved normal host access. This supports an environment
restriction diagnosis for those two results; it does not constitute a fresh full-suite
pass outside the sandbox. The restricted-run log is .companion/audit-tests.log.
