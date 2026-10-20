from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_requirements", ROOT / "tools/validate_requirements.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class RequirementTests(unittest.TestCase):
    def setUp(self):
        self.ledger = json.loads((ROOT / "design/requirements.json").read_text(encoding="utf-8"))

    def test_ledger_covers_original_requirements_with_valid_evidence(self):
        self.assertEqual(validator.validate_ledger(self.ledger)["status"], "passed")

    def test_missing_duplicate_and_wording_drift_are_rejected(self):
        for mutation in (lambda entries: entries.pop(), lambda entries: entries.append(copy.deepcopy(entries[0])), lambda entries: entries[0].update(requirement="Changed requirement")):
            ledger = copy.deepcopy(self.ledger)
            mutation(ledger["requirements"])
            with self.assertRaises(ValueError):
                validator.validate_ledger(ledger)

    def test_unproven_completion_and_invalid_test_symbols_are_rejected(self):
        for changes in ({"status": "implemented", "sources": [], "tests": [], "remaining": []}, {"tests": ["tests/test_runtime.py::RuntimeTests.test_nonexistent"]}, {"sources": ["../outside.py"]}, {"status": "partial", "remaining": []}):
            ledger = copy.deepcopy(self.ledger)
            ledger["requirements"][0].update(changes)
            with self.assertRaises(ValueError):
                validator.validate_ledger(ledger)
