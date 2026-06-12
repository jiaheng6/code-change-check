#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import re
from pathlib import Path


JSON_REFERENCE_RE = re.compile(
    r"(?P<reference>(?:[A-Za-z0-9_.-]+[\\/])+(?:\*|[A-Za-z0-9_.-]+)\.json)",
    re.IGNORECASE,
)
CODE_TOKEN_RE = re.compile(r"\b[A-Za-z_$][A-Za-z0-9_$]{3,}\b")
ENDPOINT_TOKEN_RE = re.compile(r"/([A-Za-z_$][A-Za-z0-9_$]{3,})")
SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
SKIP_DIRS = {
    ".code-change-check",
    ".git",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
TOKEN_STOPWORDS = {
    "OpenSpec",
    "JSON",
    "String",
    "Integer",
    "Boolean",
    "Long",
    "Double",
    "Float",
    "Object",
    "response",
    "request",
    "value",
    "label",
    "data",
    "field",
    "fields",
    "true",
    "false",
    "null",
}
BUILD_FILES = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
}


def expand_input_files(entries: list[str], suffixes: set[str]) -> list[Path]:
    files = []
    for entry in entries:
        path = Path(entry)
        if path.is_file() and path.suffix.lower() in suffixes:
            files.append(path.resolve())
        elif path.is_dir():
            files.extend(
                item.resolve()
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in suffixes
            )
    return sorted(set(files), key=lambda item: item.as_posix())


def candidate_bases(project: Path, document: Path) -> list[Path]:
    bases = []
    for start in (project.resolve(), document.parent.resolve()):
        current = start
        for _ in range(8):
            if current not in bases:
                bases.append(current)
            if current.parent == current:
                break
            current = current.parent
    return bases


def resolve_json_reference(project: Path, document: Path, reference: str) -> list[Path]:
    normalized = reference.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        bases = [Path(path.anchor)]
        normalized = normalized[len(path.anchor) :].lstrip("/")
    else:
        bases = candidate_bases(project, document)
    matches = []
    for base in bases:
        try:
            candidates = base.glob(normalized) if "*" in normalized else [base / normalized]
            for candidate in candidates:
                if candidate.is_file() and candidate.suffix.lower() == ".json":
                    matches.append(candidate.resolve())
        except (OSError, ValueError):
            continue
    return sorted(set(matches), key=lambda item: item.as_posix())


def discover_referenced_json_artifacts(
    project: Path,
    documents: list[Path],
    selected_contract_files: list[Path],
) -> dict:
    selected = {path.resolve() for path in selected_contract_files}
    referenced_by_path: dict[Path, dict] = {}
    unresolved = []
    for document in documents:
        if not document.is_file():
            continue
        try:
            text = document.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in JSON_REFERENCE_RE.finditer(text):
            reference = match.group("reference")
            matches = resolve_json_reference(project, document, reference)
            if not matches:
                unresolved.append(
                    {
                        "reference": reference,
                        "source_file": str(document.resolve()),
                    }
                )
            for path in matches:
                referenced_by_path.setdefault(
                    path,
                    {
                        "path": str(path),
                        "reference": reference,
                        "source_file": str(document.resolve()),
                    },
                )
    referenced = list(referenced_by_path.values())
    missing = [
        item
        for path, item in referenced_by_path.items()
        if path not in selected
    ]
    return {
        "referenced": referenced,
        "missing": missing,
        "unresolved": unresolved,
    }


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_contract_snapshot_roles(
    contract_files: list[Path],
    snapshot_files: list[Path],
) -> dict:
    contracts = [path.resolve() for path in contract_files if path.is_file()]
    snapshots = [path.resolve() for path in snapshot_files if path.is_file()]
    contract_hashes = {}
    for contract in contracts:
        try:
            contract_hashes[contract] = file_digest(contract)
        except OSError:
            continue
    issues = []
    valid = []
    for snapshot in snapshots:
        conflict = None
        for contract in contracts:
            if snapshot == contract:
                conflict = {
                    "type": "same-path",
                    "contract_file": str(contract),
                    "snapshot_file": str(snapshot),
                    "message": "期望契约与实际响应快照使用了同一文件，已拒绝比较，避免虚假通过。",
                }
                break
        if conflict is None:
            try:
                snapshot_hash = file_digest(snapshot)
            except OSError:
                valid.append(snapshot)
                continue
            matching_contract = next(
                (
                    contract
                    for contract, digest in contract_hashes.items()
                    if digest == snapshot_hash
                ),
                None,
            )
            if matching_contract is not None:
                conflict = {
                    "type": "same-content",
                    "contract_file": str(matching_contract),
                    "snapshot_file": str(snapshot),
                    "message": "期望契约与实际响应快照内容完全相同，已拒绝比较，避免虚假通过。",
                }
        if conflict:
            issues.append(conflict)
        else:
            valid.append(snapshot)
    return {
        "issues": issues,
        "valid_snapshot_files": valid,
    }


def contract_tokens(text: str) -> list[str]:
    tokens = set(ENDPOINT_TOKEN_RE.findall(text))
    tokens.update(CODE_TOKEN_RE.findall(text))
    return sorted(
        token
        for token in tokens
        if token not in TOKEN_STOPWORDS and not token.isupper()
    )


def iter_source_files(project: Path):
    for path in project.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        try:
            relative = path.relative_to(project)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        yield path, relative.as_posix()


def build_token_occurrences(project: Path, tokens: set[str]) -> dict[str, list[dict]]:
    occurrences = {token: [] for token in tokens}
    if not tokens:
        return occurrences
    for path, relative in iter_source_files(project):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            matched_tokens = tokens.intersection(CODE_TOKEN_RE.findall(line))
            for token in matched_tokens:
                if len(occurrences[token]) < 30:
                    occurrences[token].append(
                        {
                            "file": relative,
                            "line": line_number,
                            "token": token,
                            "snippet": line.strip()[:240],
                        }
                    )
    return occurrences


def build_manual_review_obligations(
    project: Path,
    unchecked_contracts: list[dict],
    contracts: list[dict],
) -> list[dict]:
    contracts_by_id = {contract.get("id", ""): contract for contract in contracts}
    obligation_tokens = {}
    all_tokens = set()
    for unchecked in unchecked_contracts:
        contract_id = unchecked.get("contract_id", "")
        tokens = contract_tokens(contracts_by_id.get(contract_id, {}).get("text", ""))
        obligation_tokens[contract_id] = tokens
        all_tokens.update(tokens)
    occurrences = build_token_occurrences(project, all_tokens)
    obligations = []
    for unchecked in unchecked_contracts:
        contract_id = unchecked.get("contract_id", "")
        contract = contracts_by_id.get(contract_id, {})
        tokens = obligation_tokens.get(contract_id, [])
        candidates_by_location = {}
        for token in tokens:
            for candidate in occurrences.get(token, []):
                key = (candidate["file"], candidate["line"])
                existing = candidates_by_location.setdefault(
                    key,
                    {
                        "file": candidate["file"],
                        "line": candidate["line"],
                        "tokens": [],
                        "snippet": candidate["snippet"],
                        "score": 0,
                    },
                )
                if token not in existing["tokens"]:
                    existing["tokens"].append(token)
                    existing["score"] += 1
        candidates = sorted(
            candidates_by_location.values(),
            key=lambda item: (-item["score"], item["file"], item["line"]),
        )[:8]
        obligations.append(
            {
                "contract_id": contract_id,
                "priority": "high",
                "kind": unchecked.get("kind", contract.get("kind", "")),
                "file": unchecked.get("file", contract.get("file", "")),
                "line": int(unchecked.get("line", contract.get("line", 1))),
                "contract_text": contract.get("text", ""),
                "reason": unchecked.get("reason", ""),
                "tokens": tokens,
                "candidates": candidates,
            }
        )
    return obligations


def assess_audit_coverage(
    *,
    changes: dict,
    contract_check: dict,
    java_analysis: dict,
    role_issues: list[dict],
    missing_referenced_artifacts: list[dict],
    manual_review_obligations: list[dict],
) -> dict:
    total = int(contract_check.get("total_contracts", 0))
    checked = int(contract_check.get("checked_contracts", 0))
    coverage_percent = round((checked / total) * 100, 1) if total else 100
    reasons = []
    if role_issues:
        reasons.append(
            {
                "code": "input-role-conflict",
                "severity": "blocked",
                "message": f"发现 {len(role_issues)} 个期望契约与实际响应快照角色冲突，冲突快照已拒绝参与比较。",
            }
        )
    if total and checked == 0:
        reasons.append(
            {
                "code": "zero-contract-coverage",
                "severity": "blocked",
                "message": f"已启用 {total} 条业务契约，但自动检查数为 0；不得把 0 违反解释为通过。",
            }
        )
    elif contract_check.get("unchecked_contracts"):
        reasons.append(
            {
                "code": "unchecked-contracts",
                "severity": "partial",
                "message": f"仍有 {len(contract_check.get('unchecked_contracts', []))} 条业务契约未检查。",
            }
        )
    if missing_referenced_artifacts:
        reasons.append(
            {
                "code": "missing-referenced-contract-artifacts",
                "severity": "partial",
                "message": f"选中文档引用了 {len(missing_referenced_artifacts)} 个未纳入审计的 JSON 契约材料。",
            }
        )
    if changes.get("source") == "snapshot" and changes.get("range") == "current":
        reasons.append(
            {
                "code": "full-scan-no-baseline",
                "severity": "partial",
                "message": "当前为无 baseline 的全量扫描，无法区分本次迭代新增问题与历史问题。",
            }
        )
    java_status = java_analysis.get("status", "disabled")
    java_coverage = java_analysis.get("coverage", {})
    if java_status == "blocked" or (
        int(java_coverage.get("java_files_total", 0)) > 0
        and int(java_coverage.get("java_files_parsed", 0)) == 0
    ):
        reasons.append(
            {
                "code": "java-analysis-blocked",
                "severity": "blocked",
                "message": "Java 核心语义分析未成功解析任何目标文件。",
            }
        )
    elif java_status == "partial" or not java_coverage.get("core_complete", True):
        reasons.append(
            {
                "code": "java-analysis-partial",
                "severity": "partial",
                "message": "Java 核心语义分析存在未解析文件或其他覆盖缺口。",
            }
        )
    if not java_coverage.get("graph_complete", True):
        reasons.append(
            {
                "code": "code-graph-incomplete",
                "severity": "partial",
                "message": "调用链和影响范围分析未完整完成。",
            }
        )
    if not java_coverage.get("comparison_complete", True):
        reasons.append(
            {
                "code": "java-comparison-incomplete",
                "severity": "partial",
                "message": "baseline/target Java 业务语义比较未完整完成。",
            }
        )
    status = "success"
    if any(item["severity"] == "blocked" for item in reasons):
        status = "blocked"
    elif reasons:
        status = "partial"
    return {
        "status": status,
        "contract_coverage_percent": coverage_percent,
        "manual_review_obligation_count": len(manual_review_obligations),
        "reasons": reasons,
        "message": {
            "success": "审计覆盖质量闸门通过。",
            "partial": "审计存在覆盖缺口，结论必须附带限制条件。",
            "blocked": "审计覆盖不足，禁止据此给出可以合并或未发现风险的结论。",
        }[status],
    }


def has_java_build_file(project: Path) -> bool:
    return any(path.is_file() and path.name in BUILD_FILES for path in project.rglob("*"))


def build_plan_review(plan: dict) -> dict:
    project = Path(plan["project"])
    spec_files = expand_input_files(plan.get("spec", []), {".md"})
    contract_files = expand_input_files(plan.get("contract", []), {".md", ".json", ".yaml", ".yml"})
    snapshot_files = expand_input_files(plan.get("response_snapshot", []), {".json"})
    documents = spec_files + [path for path in contract_files if path.suffix.lower() == ".md"]
    references = discover_referenced_json_artifacts(project, documents, contract_files)
    roles = validate_contract_snapshot_roles(
        [path for path in contract_files if path.suffix.lower() == ".json"],
        snapshot_files,
    )
    warnings = []
    if plan.get("scan_all") and not plan.get("baseline"):
        warnings.append(
            {
                "code": "full-scan-no-baseline",
                "severity": "high",
                "message": "全量扫描没有 baseline，无法区分本次迭代新增问题与历史问题。",
            }
        )
    if references["missing"]:
        warnings.append(
            {
                "code": "missing-referenced-contract-artifacts",
                "severity": "high",
                "message": f"选中文档引用了 {len(references['missing'])} 个未纳入审计的 JSON 契约材料。",
            }
        )
    if roles["issues"]:
        warnings.append(
            {
                "code": "input-role-conflict",
                "severity": "critical",
                "message": f"发现 {len(roles['issues'])} 个期望契约与实际响应快照角色冲突。",
            }
        )
    return {
        "review_warnings": warnings,
        "referenced_contract_artifacts": references["referenced"],
        "missing_referenced_contract_artifacts": references["missing"],
        "unresolved_contract_references": references["unresolved"],
        "input_role_issues": roles["issues"],
    }
