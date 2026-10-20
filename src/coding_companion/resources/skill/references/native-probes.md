# Native probes

The companion runs approved native executables with argument arrays and no shell. It does not install dependencies, grant network access, or provide OS isolation. Use a host sandbox when one is required. Untrusted execution is unsupported.

Create a JSON specification with these exact fields:

```json
{
  "check_id": "native.project-tests",
  "argv": ["/absolute/path/to/python", "-m", "pytest", "--junitxml", "{artifact_dir}/tests.xml"],
  "inputs": ["pyproject.toml", "src/*", "tests/*"],
  "parser": "junit",
  "report": "tests.xml",
  "category": "tests"
}
```

Use `probe approve SPEC_PATH --trust-workspace-execution` only with authorization to execute that exact project command. Approval binds the specification, executable bytes and matching input hashes. Changes require renewed trust. Keep required source/config/test inputs in the patterns. The native runner reports before/after project snapshots conservatively.

`check --check native.project-tests` executes the approved probe. Test probes require a bounded JUnit report with nonzero actual executed cases; an exit code alone cannot establish test success. A non-test build/lint command may use `parser: "exit_code"` and `report: null`, which proves only that specific command's exit status.

Output is bounded and redacted before storage. Timeouts, malformed/missing reports, truncation and changed inputs remain non-success outcomes. Windows launch is suspended until Job Object assignment succeeds, with lifetime/per-process memory bounds. This does not grant filesystem/network isolation. POSIX reports process-group and memory enforcement limits explicitly.

Specs can also use `parser: "sarif"` for a non-test scanner's bounded SARIF 2.1.0 report. Test probes retain JUnit count requirements. Existing interpreter/script arguments and tool binaries are hashed; changing those files or detected module versions requires renewed trust.

The packaged `junit_probe.py` runs real stdlib unittest discovery. `browser_probe.py` (optional Playwright/browser) and `api_probe.py` accept declared loopback contracts; `sqlite_probe.py` opens a bounded customer database read-only and checks an in-memory backup. All are ordinary approved native probes, with `--report {artifact_dir}/tests.xml`; they are not automatically run by the watcher. Their CLI `--help` defines the additional contract/input arguments.

Independent package evaluation, executable activation and local training are separate reviewed commands. Diagnostic evidence cannot authorize them, change host trust or enable provider-model training.

`probe propose --json` lists nonexecuting tool proposals. For supported installed npm tools, `probe propose CHECK_ID --output FILE --json` saves one exact spec without approving it or replacing an existing file. Store the review file outside the project or export it before approval. Root-package IDs are `native.web.typecheck`, `native.web.lint`, `native.web.build` and `native.web.tests`; nested packages add a stable package suffix.

Web proposals use Node and the packaged `node_probe.mjs` wrapper to invoke the installed CLI in its package directory. TypeScript needs `tsconfig.json`, ESLint needs a flat configuration, Vite builds into scratch, and Vitest emits JUnit in scratch. Declared tools without usable installations/configuration remain blocked. Normal and hoisted tool installations must resolve inside the project; discovery never downloads tools or runs package scripts. Node CLI package runtime artifacts are hashed within bounded limits, while transitive dependency code and external environment inputs are not exhaustively frozen.

JavaScript/TypeScript test/spec files and `__tests__` contents are preserved during repair verification. A green run obtained by changing those original assertions remains unresolved and requires review of the changed acceptance contract.
