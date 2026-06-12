#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from audit_coverage import build_plan_review


AUDIT_PLAN_VERSION = 1
AUDIT_PLAN_FIELDS = [
    "project",
    "baseline",
    "base_ref",
    "target_ref",
    "svn_revision",
    "commit_limit",
    "map_requirements",
    "no_map_requirements",
    "spec",
    "strict_spec",
    "contract",
    "strict_contract",
    "contract_source",
    "no_contract",
    "confirm_contracts",
    "no_confirm_contracts",
    "rules",
    "java_analysis",
    "tool_cache",
    "offline",
    "output",
    "scan_all",
    "include_support_findings",
    "response_snapshot",
]


def resolve_path(value: str | None, base: Path | None = None) -> str | None:
    if not value:
        return value
    path = Path(value)
    if not path.is_absolute() and base is not None:
        path = base / path
    return str(path.resolve())


def resolve_path_list(values: list[str], base: Path) -> list[str]:
    return [resolve_path(value, base) or value for value in values]


def build_audit_plan(args: argparse.Namespace) -> dict:
    project = Path(args.project).resolve()
    plan = {
        "version": AUDIT_PLAN_VERSION,
        "confirmed": False,
        "confirmation_hash": "",
    }
    for field in AUDIT_PLAN_FIELDS:
        plan[field] = getattr(args, field)

    plan["project"] = str(project)
    plan["baseline"] = resolve_path(args.baseline)
    plan["spec"] = resolve_path_list(args.spec, project)
    plan["contract"] = resolve_path_list(args.contract, project)
    plan["response_snapshot"] = resolve_path_list(args.response_snapshot, project)
    plan["rules"] = resolve_path(args.rules)
    plan["output"] = resolve_path(args.output)
    plan["tool_cache"] = resolve_path(args.tool_cache, project)
    plan.update(build_plan_review(plan))
    return plan


def save_audit_plan(path: Path, plan: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def load_audit_plan(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != AUDIT_PLAN_VERSION:
        raise ValueError(f"不支持的审计计划版本：{data.get('version')}")
    return data


def audit_plan_digest(plan: dict) -> str:
    content = {
        key: value
        for key, value in plan.items()
        if key not in {"confirmed", "confirmation_hash"}
    }
    serialized = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def confirm_audit_plan(path: Path) -> None:
    plan = load_audit_plan(path)
    plan["confirmed"] = True
    plan["confirmation_hash"] = audit_plan_digest(plan)
    save_audit_plan(path, plan)


def apply_audit_plan(args: argparse.Namespace, plan: dict) -> argparse.Namespace:
    if not plan.get("confirmed"):
        raise ValueError("审计计划尚未确认，拒绝执行。")
    if plan.get("confirmation_hash") != audit_plan_digest(plan):
        raise ValueError("审计计划确认后已被修改，拒绝执行。")
    for field in AUDIT_PLAN_FIELDS:
        if field in plan:
            setattr(args, field, plan[field])
    args.interactive = False
    args.no_interactive = True
    return args
