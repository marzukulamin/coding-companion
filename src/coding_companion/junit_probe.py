"""Trusted stdlib unittest probe. It executes explicitly approved project tests."""
from __future__ import annotations

import argparse
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


class Recording(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.cases, self.current = [], None

    def startTest(self, test):
        super().startTest(test)
        self.current = ET.Element("testcase", name=test.id())
        self.cases.append(self.current)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        ET.SubElement(self.current, "failure", message=err[0].__name__)

    def addError(self, test, err):
        super().addError(test, err)
        ET.SubElement(self.current, "error", message=err[0].__name__)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        ET.SubElement(self.current, "skipped", message="Test explicitly skipped")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        ET.SubElement(self.current, "failure", message="Unexpected success")

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        ET.SubElement(self.current, "skipped", message="Expected failure does not establish repaired behavior")

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            ET.SubElement(self.current, "failure", message=err[0].__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--start-directory", default="tests")
    parser.add_argument("--pattern", default="test*.py")
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    suite = unittest.defaultTestLoader.discover(args.start_directory, pattern=args.pattern)
    discovered = suite.countTestCases()
    result = Recording()
    suite.run(result)
    report = ET.Element("testsuite", tests=str(len(result.cases)), failures=str(sum(c.find("failure") is not None for c in result.cases)), errors=str(sum(c.find("error") is not None for c in result.cases)), skipped=str(sum(c.find("skipped") is not None for c in result.cases)))
    report.extend(result.cases)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(report).write(args.report, encoding="utf-8", xml_declaration=True)
    return 2 if discovered == 0 else 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
