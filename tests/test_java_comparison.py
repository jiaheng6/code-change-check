from __future__ import annotations

from pathlib import Path
import sys
import unittest

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from java_comparison import compare_java_evidence


def evidence(kind: str, slot: str, source: str, value: str = "") -> dict:
    return {
        "id": f"src/SafetyService.java|SafetyService#run()|{kind}|{slot}",
        "kind": kind,
        "file": "src/SafetyService.java",
        "line": 10,
        "symbol": "SafetyService#run()",
        "slot": slot,
        "source_expression": source,
        "value": value,
        "arguments": [source] if kind == "call" else [],
    }


class JavaComparisonTest(unittest.TestCase):
    def test_detects_field_mapping_source_change(self):
        result = compare_java_evidence(
            [evidence("field-mapping", "fireEvent.count.value", "statistics.getTotalFireAlarms()")],
            [evidence("field-mapping", "fireEvent.count.value", "statistics.getFireSafetyIncidents()")],
        )

        finding = result["changes"][0]
        self.assertEqual(finding["type"], "field-mapping-source-changed")
        self.assertEqual(finding["severity"], "critical")

    def test_detects_internal_to_external_address_change(self):
        result = compare_java_evidence(
            [evidence("http-argument", "get", "internalBaseUrl", "internal")],
            [evidence("http-argument", "get", "publicBaseUrl", "external")],
        )

        self.assertEqual(result["changes"][0]["type"], "http-address-source-changed")
        self.assertEqual(result["changes"][0]["severity"], "critical")

    def test_detects_guard_removed(self):
        result = compare_java_evidence(
            [evidence("guard", "if", "tenantId != null", "permission")],
            [],
        )

        self.assertEqual(result["changes"][0]["type"], "guard-removed")


if __name__ == "__main__":
    unittest.main()
