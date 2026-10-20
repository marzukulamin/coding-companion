# Explicit HTTP scenario probes

Use only synthetic actors and an explicitly authorized loopback test application.
Do not put real credentials in contracts. Approve the exact native probe spec through
the normal `probe approve` flow before execution. The helper does not install services.

An access matrix requires expected status/JSON/header results for every actor/resource
pair. Testing one administrator does not establish tenant isolation.

```json
{
  "base_url": "http://127.0.0.1:8080",
  "access_matrix": {
    "actors": {
      "alice": {"X-Test-Actor": "alice"},
      "bob": {"X-Test-Actor": "bob"},
      "anonymous": {}
    },
    "resources": [{
      "path": "/test/tenants/alice",
      "expected_by_actor": {
        "alice": {"status": 200},
        "bob": {"status": 403},
        "anonymous": {"status": 401}
      }
    }]
  }
}
```

Concurrency steps use an explicit subsequent invariant. Successful individual requests
alone cannot establish whether writes were lost or duplicated.

```json
{
  "base_url": "http://127.0.0.1:8080",
  "steps": [
    {"parallel": [
      {"method": "POST", "path": "/test/increment", "expected": {"status": 200}},
      {"method": "POST", "path": "/test/increment", "expected": {"status": 200}}
    ]},
    {"path": "/test/state", "expected": {"status": 200, "json_fields": {"count": 2}}}
  ]
}
```

Review a native spec with `argv` equivalent to:

```text
python -m coding_companion.scenario_probe --contract scenarios.json --report {artifact_dir}/tests.xml --allow-mutation
```

Use an absolute native Python executable in the spec, category `tests`, parser `junit`,
report `tests.xml`, and input patterns covering the contract and relevant project code.
Omit `--allow-mutation` for read-only matrices. The supplied examples describe test-only
endpoints, not ordinary production authentication. A production permission policy must
come from the actual application requirements.

The probe checks declared requests and invariant readbacks only. It does not create
race conditions reliably on every application, simulate network failure, inject worker
crashes, certify arbitrary queues/caches, or prove complete authorization coverage.
