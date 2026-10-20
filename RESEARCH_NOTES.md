# Research notes and design implications

Reviewed 12 October 2026. These sources informed the architecture, not a claim of exhaustive internet coverage. Product capabilities and service quotas need rechecking before release.

## Public concerns

A current developer discussion describes debugging as dependent on runtime context: deployed version, user actions, permissions, flags, responses, and logs. It also discusses silent failures and symptom-only diagnoses. This is anecdotal, self-selected discussion, including product promotion; it is not a reliability measurement. [Discussion](https://www.reddit.com/r/AI_Agents/comments/1x2y85d/ai_agents_write_the_code_who_debugs_it_when_a/)

Design response: authorized sanitized incident input, correlation IDs, business-invariant checks, a challenge journal, reproducible diagnosis, and adjacent regression verification. Do not interpret lack of an exception as success.

## Primary studies

| Source | Relevant finding and limits | Architecture consequence |
|---|---|---|
| [Perry et al., security user study](https://arxiv.org/abs/2211.03622) | Participants using an older codex-davinci-002 assistant produced less secure solutions on the study's security tasks and expressed greater confidence. This is a particular historical experiment. | Independent security/permission checks; confidence is not evidence. |
| [METR early-2025 randomized study](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) | With 16 experienced developers and 246 real issues, early-2025 tools increased completion time by 19% in that setting. | Measure complete repair/review time and companion overhead. |
| [METR February-2026 update](https://metr.org/blog/2026-02-24-uplift-update/) | Later measurement and selection difficulties prevented a reliable estimate of contemporary uplift. | Do not apply the earlier percentage to all current agents or models. |
| [Logging study](https://arxiv.org/abs/2604.09409) | The study investigates agent logging and instruction adherence; its findings motivate explicit observability checks. | Test useful correlation and failure visibility, not merely presence of a logging library. |
| [Breaking-change study](https://arxiv.org/abs/2603.27524) | Observational comparisons distinguish task types and report maintenance-related risks; dataset and attribution limits matter. | Verify public contracts and refactoring/update regressions. |
| [Maintenance study](https://arxiv.org/abs/2605.06464) | Observed repositories show humans perform much subsequent maintenance; update frequency alone does not establish quality. | Retain rationale, versions, ownership, reproducible evidence, and maintenance runbooks. |

None of these establishes GPT-6.1 Sol's specific performance, a fixed percentage of missed defects, or universal superiority of one assistant. The companion must be evaluated on its own supported tasks and environments.

## Technical foundations and constraints

| Primary documentation | Verified foundation | Decision |
|---|---|---|
| [Python support status](https://devguide.python.org/versions/) | Supported branches and lifecycles are explicit. | Minimum 3.12; use current patches and certify OS/interpreter combinations. |
| [Python SQLite interface](https://docs.python.org/3.12/library/sqlite3.html) | Local SQL interface, linked-library version, transactions, and backup mechanisms. | SQLite feature probes and tested backup/restore. |
| [SQLite usage](https://sqlite.org/whentouse.html) | Local low-writer-concurrency workloads fit SQLite; it has one writer at a time. | Project-local database and one coordinator. |
| [SQLite WAL](https://sqlite.org/wal.html) | WAL needs suitable local coordination and has version-specific caveats. | Rollback journal initially; gated opt-in WAL. |
| [FTS5](https://sqlite.org/fts5.html) | Full-text search depends on the SQLite build. | Optional search index with lexical fallback. |
| [Python subprocess](https://docs.python.org/3.12/library/subprocess.html) | Process invocation, output, timeouts, and platform behavior require care. | Bounded streaming runner, validated argv, explicit process-tree cleanup/isolation. |
| [Agent Skills](https://agentskills.io/specification) | Portable instruction/resources format. | Small skill plus executable core; no universal notification assumption. |
| [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | Structured protocol over stdin/stdout; logs use stderr. | Optional SDK adapter, no network service needed locally. |
| [OpenAI skills](https://learn.chatgpt.com/docs/build-skills) | Skills package instructions and supporting resources. | Progressive references and tools rather than a giant entrypoint. |
| [Codex hooks](https://learn.chatgpt.com/docs/hooks) | Local async informational delivery and cloud restrictions differ. | Capability-tested adapters and checkpoint fallback. |
| [Codex app-server](https://learn.chatgpt.com/docs/app-server) | Deep custom-client event/control integration. | Optional controlled integration, no arbitrary session attachment. |
| [Claude Code hooks](https://code.claude.com/docs/en/hooks) | Host-specific hook execution/delivery semantics. | Separate adapter certification. |
| [GitHub Free](https://docs.github.com/en/get-started/learning-about-github/githubs-plans) | Private repositories are supported with limited features. | Private source and authenticated releases. |
| [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) | Private CI quotas and overage billing. | Local-first CI, no required hosted jobs. |
| [GitHub budgets](https://docs.github.com/en/billing/how-tos/set-up-budgets) | Spending alerts and stopping controls differ. | Enforced stop-spending controls if metered CI is enabled. |
| [pip-audit security model](https://github.com/pypa/pip-audit#security-model) | Dependency resolution is not inherently safe static analysis. | Isolate/trust executable dependency processing. |
| [Playwright browsers](https://playwright.dev/docs/browsers) | Browser automation requires appropriate browser installation. | Optional explicit browser setup and blocked coverage when unavailable. |
| [axe-core](https://github.com/dequelabs/axe-core) | Automated accessibility checks include incomplete/manual review needs. | Preserve limits instead of declaring universal compliance. |

## Evidence classification

Source documentation establishes an available capability, not that this architecture already implements it. A study motivates tests, not a guarantee about every model. Public anecdotes supply candidate failure scenarios, not ground truth. Architecture choices are engineering decisions to be validated.

Compatibility entries therefore remain documented_not_tested until actual host tests. Design examples are synthetic. No proposed scanner, daemon, host integration, cloud environment, or training job has been executed.
