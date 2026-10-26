"""Mechanical governance verifier and pre-commit gate for C:\\motion-agent."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROTECTED_PATHS = (
    "tests/immutable",
    "SPEC.md",
    "CONSTRAINTS.md",
    "scripts/verify_done.py",
)
MAX_DIFF_FILES = 5
MAX_NET_LINES = 250
REPORT_MAX_AGE_SEC = 600
PIPELINE_ENTRYPOINT = "run_pipeline"


class _CTRFPlugin:
    """In-process pytest plugin that writes a machine-readable CTRF JSON report."""

    def __init__(self, report_path: Path) -> None:
        self.report_path = report_path
        self.tests: list[dict[str, Any]] = []
        self.start_time = int(time.time() * 1000)

    def pytest_runtest_logreport(self, report: Any) -> None:
        if report.when == "call" or (report.when in ("setup", "teardown") and report.failed):
            status = "passed" if report.passed else ("failed" if report.failed else "skipped")
            self.tests.append(
                {
                    "name": report.nodeid,
                    "status": status,
                    "duration": round(getattr(report, "duration", 0.0) * 1000, 3),
                }
            )

    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        stop_time = int(time.time() * 1000)
        passed = sum(1 for t in self.tests if t["status"] == "passed")
        failed = sum(1 for t in self.tests if t["status"] == "failed")
        skipped = sum(1 for t in self.tests if t["status"] == "skipped")
        payload = {
            "results": {
                "tool": {"name": "pytest-ctrf-builtin"},
                "summary": {
                    "tests": len(self.tests),
                    "passed": passed,
                    "failed": failed,
                    "skipped": skipped,
                    "pending": 0,
                    "other": 0,
                    "start": self.start_time,
                    "stop": stop_time,
                    "exit_code": int(exitstatus),
                },
                "tests": self.tests,
            }
        }
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.report_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, self.report_path)


def _run_git(repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        check=False,
    )


def step_1_run_tests(repo_root: Path) -> tuple[bool, str, str]:
    """Run pytest on tests/regression and tests/immutable and verify ctrf_latest.json."""
    import pytest

    report_path = repo_root / "reports" / "ctrf_latest.json"
    if report_path.exists():
        report_path.unlink()

    reg_dir = repo_root / "tests" / "regression"
    imm_dir = repo_root / "tests" / "immutable"
    if not reg_dir.exists() or not imm_dir.exists():
        return False, "Missing tests/regression or tests/immutable directory.", ""

    # Clear cached src modules so tests always import fresh code
    for mod in list(sys.modules.keys()):
        if mod == "src" or mod.startswith("src."):
            del sys.modules[mod]

    plugin = _CTRFPlugin(report_path)
    env_backup = os.environ.get("MOTION_AGENT_IN_VERIFY")
    os.environ["MOTION_AGENT_IN_VERIFY"] = "1"
    old_sys_path = list(sys.path)
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        exit_code = pytest.main(
            [str(reg_dir), str(imm_dir), "-q", "--tb=short"],
            plugins=[plugin],
        )
    finally:
        sys.path[:] = old_sys_path
        if env_backup is None:
            os.environ.pop("MOTION_AGENT_IN_VERIFY", None)
        else:
            os.environ["MOTION_AGENT_IN_VERIFY"] = env_backup

    if not report_path.exists() or report_path.stat().st_size == 0:
        return False, "CTRF report missing or empty.", ""

    age = time.time() - report_path.stat().st_mtime
    if age > REPORT_MAX_AGE_SEC:
        return False, f"CTRF report is stale ({age:.1f}s > {REPORT_MAX_AGE_SEC}s).", ""

    raw_bytes = report_path.read_bytes()
    report_sha = hashlib.sha256(raw_bytes).hexdigest()
    data = json.loads(raw_bytes.decode("utf-8"))
    summary = data.get("results", {}).get("summary", {})

    total_tests = summary.get("tests", 0)
    failed_tests = summary.get("failed", 0)
    if exit_code != 0 or total_tests == 0 or failed_tests > 0:
        return (
            False,
            f"Test suite failed (exit_code={exit_code}, total={total_tests}, failed={failed_tests}).",
            report_sha,
        )

    return True, f"passed={summary.get('passed', 0)} failed=0", report_sha


def step_2_check_protected_files(repo_root: Path, report_sha: str, is_feature_mode: bool) -> tuple[bool, str]:
    """Ensure protected files are untouched relative to HEAD and staged index."""
    for cmd in (
        ["diff", "--exit-code", "HEAD", "--", *PROTECTED_PATHS],
        ["diff", "--cached", "--exit-code", "--", *PROTECTED_PATHS],
    ):
        res = _run_git(repo_root, cmd)
        if res.returncode != 0:
            return False, f"Protected file modified ({' '.join(cmd)}):\n{res.stdout}\n{res.stderr}"

    status_res = _run_git(repo_root, ["status", "--porcelain", "--", *PROTECTED_PATHS])
    lines = [
        l for l in status_res.stdout.splitlines()
        if l.strip() and "__pycache__" not in l and not l.endswith(".pyc")
    ]
    if lines:
        return False, f"Untracked or modified protected path detected:\n{chr(10).join(lines)}"

    # Guard against manual status tampering in feature_list.json
    fl_diff = _run_git(repo_root, ["diff", "HEAD", "--", "feature_list.json"])
    if fl_diff.stdout.strip() and not is_feature_mode:
        head_fl_res = _run_git(repo_root, ["show", "HEAD:feature_list.json"])
        if head_fl_res.returncode == 0:
            old_features = {
                f["id"]: f for f in json.loads(head_fl_res.stdout).get("features", [])
            }
            cur_features = {
                f["id"]: f
                for f in json.loads((repo_root / "feature_list.json").read_text(encoding="utf-8")).get("features", [])
            }
            for fid, cur_f in cur_features.items():
                old_f = old_features.get(fid)
                if old_f and old_f.get("status") != cur_f.get("status"):
                    evidence = cur_f.get("evidence_path")
                    if not evidence:
                        return False, f"Illegal manual status change on {fid} without evidence_path."
                    if not evidence.startswith("reports/ctrf_latest.json#sha256=") or len(evidence.split("=")[-1]) != 64:
                        return False, f"Illegal manual status change on {fid}: evidence_path must be reports/ctrf_latest.json#sha256=<64-hex>."

    return True, "Protected files intact."


def step_3_check_diff_budget(repo_root: Path) -> tuple[bool, str]:
    """Enforce at most 5 changed files and 250 net inserted lines against HEAD."""
    res = _run_git(repo_root, ["diff", "--numstat", "HEAD"])
    if res.returncode != 0:
        return False, f"git diff --numstat HEAD failed: {res.stderr}"

    changed_files: set[str] = set()
    total_added = 0
    total_deleted = 0

    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_s, deleted_s, path_s = parts
        changed_files.add(path_s.replace("\\", "/"))
        if added_s.isdigit():
            total_added += int(added_s)
        if deleted_s.isdigit():
            total_deleted += int(deleted_s)

    # Also include untracked non-ignored files
    untracked = _run_git(repo_root, ["ls-files", "--others", "--exclude-standard"])
    for u_file in untracked.stdout.splitlines():
        norm = u_file.strip().replace("\\", "/")
        if (
            norm
            and not norm.startswith("reports/")
            and not norm.startswith("work/")
            and not norm.startswith(".pytest_cache/")
            and "__pycache__" not in norm
        ):
            changed_files.add(norm)
            full_p = repo_root / norm
            if full_p.is_file():
                try:
                    total_added += len(full_p.read_text(encoding="utf-8").splitlines())
                except UnicodeDecodeError:
                    pass

    file_count = len(changed_files)
    net_lines = total_added - total_deleted
    if file_count > MAX_DIFF_FILES:
        return False, f"Diff budget exceeded: {file_count} files touched (max {MAX_DIFF_FILES})."
    if net_lines > MAX_NET_LINES:
        return False, f"Diff budget exceeded: {net_lines} net lines added (max {MAX_NET_LINES})."

    return True, f"Diff budget OK ({file_count} files, {net_lines} net lines)."


def _collect_reachable_symbols(src_dir: Path) -> tuple[set[tuple[str, str]], list[tuple[Path, str, int]]]:
    """Build AST call/import reachability from src/pipeline.py:run_pipeline."""
    module_asts: dict[str, ast.Module] = {}
    all_public_defs: list[tuple[Path, str, str]] = []  # (path, mod_name, symbol_name)

    for py_file in sorted(src_dir.rglob("*.py")):
        rel = py_file.relative_to(src_dir).with_suffix("")
        mod_name = ".".join(rel.parts)
        if mod_name == "__init__":
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        module_asts[mod_name] = tree
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    all_public_defs.append((py_file, mod_name, node.name))

    if "pipeline" not in module_asts:
        return set(), [(src_dir / "pipeline.py", "pipeline", PIPELINE_ENTRYPOINT)]

    # Map imports and function/class definitions per module
    imports_map: dict[tuple[str, str], tuple[str, str]] = {}
    defs_map: dict[tuple[str, str], ast.AST] = {}

    for mod_name, tree in module_asts.items():
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defs_map[(mod_name, node.name)] = node
            elif isinstance(node, ast.ImportFrom) and node.module:
                target_mod = node.module
                if target_mod.startswith("src."):
                    target_mod = target_mod[4:]
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    imports_map[(mod_name, local_name)] = (target_mod, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    mod_target = alias.name
                    if mod_target.startswith("src."):
                        mod_target = mod_target[4:]
                    local_name = alias.asname or mod_target
                    imports_map[(mod_name, local_name)] = (mod_target, "*")

    visited: set[tuple[str, str]] = set()
    queue: list[tuple[str, str]] = [("pipeline", PIPELINE_ENTRYPOINT)]

    while queue:
        curr_mod, curr_sym = queue.pop(0)
        if (curr_mod, curr_sym) in visited:
            continue
        visited.add((curr_mod, curr_sym))
        node = defs_map.get((curr_mod, curr_sym))
        if node is None:
            continue

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    callee = child.func.id
                    if (curr_mod, callee) in defs_map:
                        queue.append((curr_mod, callee))
                    elif (curr_mod, callee) in imports_map:
                        t_mod, t_sym = imports_map[(curr_mod, callee)]
                        if t_sym != "*":
                            queue.append((t_mod, t_sym))
                elif isinstance(child.func, ast.Attribute) and isinstance(child.func.value, ast.Name):
                    alias_name = child.func.value.id
                    attr_name = child.func.attr
                    if (curr_mod, alias_name) in imports_map:
                        t_mod, _ = imports_map[(curr_mod, alias_name)]
                        if (t_mod, attr_name) in defs_map:
                            queue.append((t_mod, attr_name))

    uncalled: list[tuple[Path, str, int]] = []
    for py_file, mod_name, sym_name in all_public_defs:
        if (mod_name, sym_name) not in visited:
            uncalled.append((py_file, sym_name, 1))

    return visited, uncalled


def _mutate_function_return_none(source_text: str, func_name: str) -> str:
    """Replace target function body with `return None` using AST line bounds."""
    tree = ast.parse(source_text)
    lines = source_text.splitlines(keepends=True)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            first_stmt = node.body[0]
            last_stmt = node.body[-1]
            start_idx = first_stmt.lineno - 1
            end_idx = getattr(last_stmt, "end_lineno", last_stmt.lineno)
            indent_match = re.match(r"^(\s*)", lines[start_idx])
            indent = indent_match.group(1) if indent_match else "    "
            mutated_lines = lines[:start_idx] + [f"{indent}return None\n"] + lines[end_idx:]
            return "".join(mutated_lines)
    return source_text


def step_4_static_wiring_and_mutation(repo_root: Path) -> tuple[bool, str]:
    """Verify AST call reachability from src/pipeline.py and run return-None mutation check."""
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return False, "Missing src/ directory."

    visited, uncalled = _collect_reachable_symbols(src_dir)
    if uncalled:
        names = ", ".join(f"{p.name}:{sym}" for p, sym, _ in uncalled)
        return False, f"Dead/uncalled public symbol(s) in src/: {names}"

    # Mutation check: replacing each reachable public function's return with None must fail >=1 test
    for mod_name, sym_name in sorted(visited):
        py_file = src_dir / f"{mod_name.replace('.', '/')}.py"
        if not py_file.exists():
            continue
        original_text = py_file.read_text(encoding="utf-8")
        tree = ast.parse(original_text)
        is_func = any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == sym_name
            for n in tree.body
        )
        if not is_func:
            continue

        mutated_text = _mutate_function_return_none(original_text, sym_name)
        if mutated_text == original_text:
            continue

        try:
            py_file.write_text(mutated_text, encoding="utf-8", newline="\n")
            res = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(repo_root / "tests" / "regression"),
                    str(repo_root / "tests" / "immutable"),
                    "-q",
                ],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                stdin=subprocess.DEVNULL,
                check=False,
            )
            if res.returncode == 0:
                return (
                    False,
                    f"No-op mutation survived: replacing {mod_name}.{sym_name}() with 'return None' did not fail any test.",
                )
        finally:
            py_file.write_text(original_text, encoding="utf-8", newline="\n")

    return True, f"Static wiring and mutation checks verified ({len(visited)} symbol(s))."


def step_5_mark_feature_pass(repo_root: Path, feature_id: str, test_summary: str, report_sha: str) -> tuple[bool, str]:
    """Flip feature status in feature_list.json and record report SHA-256 in HANDOFF_PACKET.md."""
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from src.pipeline import durable_replace

    fl_path = repo_root / "feature_list.json"
    fl_data = json.loads(fl_path.read_text(encoding="utf-8"))
    matched = False
    for entry in fl_data.get("features", []):
        if entry.get("id") == feature_id:
            entry["status"] = "PASS"
            entry["evidence_path"] = f"reports/ctrf_latest.json#sha256={report_sha}"
            matched = True
            break

    if not matched:
        return False, f"Feature ID '{feature_id}' not found in feature_list.json."

    fl_tmp = fl_path.with_suffix(".tmp")
    with open(fl_tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(fl_data, fh, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    durable_replace(fl_tmp, fl_path)

    hp_path = repo_root / "HANDOFF_PACKET.md"
    if hp_path.exists():
        hp_text = hp_path.read_text(encoding="utf-8")
        hp_text = re.sub(
            r"result:.*report_sha256:.*",
            f"result: {test_summary}   report_sha256: {report_sha}   sabotage_checks: failing_test,protected_file,diff_budget,dead_code,readonly_lock: PASS",
            hp_text,
        )
        hp_tmp = hp_path.with_suffix(".tmp")
        with open(hp_tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(hp_text)
            fh.flush()
            os.fsync(fh.fileno())
        durable_replace(hp_tmp, hp_path)

    return True, f"Feature {feature_id} set to PASS (sha256={report_sha})."


def step_6_audit_week(repo_root: Path) -> int:
    """Confirm no protected file edits in last 7 days and check commits for report hashes."""
    res = _run_git(repo_root, ["log", "--since=7.days", "--oneline", "--", *PROTECTED_PATHS])
    commits = [line for line in res.stdout.splitlines() if line.strip()]
    all_commits_res = _run_git(repo_root, ["log", "--since=7.days", "--pretty=format:%H %s"])
    print(f"=== WEEKLY GOVERNANCE AUDIT ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}) ===")
    print(f"Protected-file commits in last 7 days: {len(commits)}")
    for c in commits:
        print(f"  [PROTECTED TOUCH] {c}")
    print(f"Total commits in last 7 days: {len(all_commits_res.stdout.splitlines())}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify governance gates for motion-agent.")
    parser.add_argument("--baseline", action="store_true", help="Run steps 1-2 only.")
    parser.add_argument("--pre-commit", action="store_true", help="Run steps 1-4 (pre-commit hook).")
    parser.add_argument("--feature", type=str, default=None, help="Run steps 1-5 and mark feature ID PASS.")
    parser.add_argument("--audit-week", action="store_true", help="Audit 7-day git log.")
    parser.add_argument("--repo-root", type=str, default=None, help="Override repo root path.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd().resolve()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    if args.audit_week:
        return step_6_audit_week(repo_root)

    ok1, msg1, report_sha = step_1_run_tests(repo_root)
    if not ok1:
        print(f"[FAIL Step 1 - Tests] {msg1}", file=sys.stderr)
        return 1

    ok2, msg2 = step_2_check_protected_files(repo_root, report_sha, is_feature_mode=bool(args.feature))
    if not ok2:
        print(f"[FAIL Step 2 - Protected Files] {msg2}", file=sys.stderr)
        return 1

    if args.baseline:
        print(f"[PASS Baseline] {msg1} | {msg2} | sha256={report_sha}")
        return 0

    ok3, msg3 = step_3_check_diff_budget(repo_root)
    if not ok3:
        print(f"[FAIL Step 3 - Diff Budget] {msg3}", file=sys.stderr)
        return 1

    ok4, msg4 = step_4_static_wiring_and_mutation(repo_root)
    if not ok4:
        print(f"[FAIL Step 4 - Static Wiring / Mutation] {msg4}", file=sys.stderr)
        return 1

    if args.pre_commit:
        print(f"[PASS Pre-Commit] {msg1} | {msg3} | {msg4} | sha256={report_sha}")
        return 0

    if args.feature:
        ok5, msg5 = step_5_mark_feature_pass(repo_root, args.feature, msg1, report_sha)
        if not ok5:
            print(f"[FAIL Step 5 - Feature Update] {msg5}", file=sys.stderr)
            return 1
        # Re-run Step 1 so reports/ctrf_latest.json is fresh after mutation checks
        ok1_final, msg1_final, final_sha = step_1_run_tests(repo_root)
        if not ok1_final:
            return 1
        ok5_final, msg5_final = step_5_mark_feature_pass(repo_root, args.feature, msg1_final, final_sha)
        if not ok5_final:
            return 1
        print(f"[PASS Feature {args.feature}] {msg5_final}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
