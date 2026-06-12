#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import PurePosixPath
import re


TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs"}
DOCUMENTATION_PARTS = {"doc", "docs", "documentation", "requirements", "tasks", "openspec"}
DEBUG_PARTS = {"debug", "logs", "log"}
FIXTURE_PARTS = {
    "fixture",
    "fixtures",
    "mock",
    "mocks",
    "example",
    "examples",
    "sample",
    "samples",
}
DOCUMENTATION_SUFFIXES = {".md", ".rst", ".txt"}
DATA_SUPPORT_PARTS = {"contract", "contracts", "response", "responses", "snapshot", "snapshots"}
DATA_SUPPORT_SUFFIXES = {".json", ".md", ".rst", ".txt", ".xml", ".yaml", ".yml"}
TEST_FILE_RE = re.compile(r"(^test[_-]|[_-]test\.|\.test\.|\.spec\.)", re.IGNORECASE)
MARKUP_NAMESPACE_RE = re.compile(
    r"\b(xmlns(?::\w+)?|xsi:schemaLocation)\s*=\s*[\"'][^\"']*https?://",
    re.IGNORECASE,
)


def classify_file_role(file: str, snippet: str = "") -> str:
    path = PurePosixPath(file.replace("\\", "/"))
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()

    if MARKUP_NAMESPACE_RE.search(snippet):
        return "markup-namespace"
    if parts & DEBUG_PARTS or name.endswith((".log", ".trace")):
        return "debug"
    if parts & TEST_PARTS or TEST_FILE_RE.search(name):
        return "test"
    if parts & FIXTURE_PARTS:
        return "fixture"
    if parts & DATA_SUPPORT_PARTS and path.suffix.lower() in DATA_SUPPORT_SUFFIXES:
        return "fixture" if parts & {"response", "responses", "snapshot", "snapshots"} else "documentation"
    if parts & DOCUMENTATION_PARTS or path.suffix.lower() in DOCUMENTATION_SUFFIXES:
        return "documentation"
    return "production"


def suppression_reason(role: str) -> str:
    reasons = {
        "test": "文本规则命中位于测试代码中，默认不作为生产风险。",
        "documentation": "文本规则命中位于说明或需求文档中，默认不作为生产风险。",
        "debug": "文本规则命中位于调试或日志文件中，默认不作为生产风险。",
        "fixture": "文本规则命中位于 fixture、mock 或示例数据中，默认不作为生产风险。",
        "markup-namespace": "命中来自 XML namespace 或 schemaLocation 标准声明。",
    }
    return reasons.get(role, "")


def partition_findings(
    findings: list[dict],
    include_support: bool = False,
) -> tuple[list[dict], list[dict]]:
    active = []
    suppressed = []
    for finding in findings:
        item = dict(finding)
        role = classify_file_role(item.get("file", ""), item.get("snippet", ""))
        item["file_role"] = role
        item["suppression_reason"] = ""
        if item.get("source", "text-rule") == "text-rule" and role != "production" and not include_support:
            item["suppression_reason"] = suppression_reason(role)
            suppressed.append(item)
        else:
            active.append(item)
    return active, suppressed


def summarize_suppressed(findings: list[dict]) -> dict:
    by_reason = Counter(item.get("file_role", "unknown") for item in findings)
    return {
        "total": len(findings),
        "by_reason": dict(sorted(by_reason.items())),
    }
