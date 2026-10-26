"""Sabotage and regression tests for Phase P-1 (F-001 Governance guards)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
import pytest

from src.pipeline import durable_replace, run_pipeline

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _init_sandbox_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository with verify_done.py and pre-commit hook installed."""
    repo = tmp_path / "sandbox_repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "src").mkdir(parents=True)
    (repo / "tests" / "regression").mkdir(parents=True)
    (repo / "tests" / "immutable").mkdir(parents=True)

    shutil.copy2(REPO_ROOT / ".gitignore", repo / ".gitignore")
    shutil.copy2(REPO_ROOT / ".gitattributes", repo / ".gitattributes")
    shutil.copy2(REPO_ROOT / "scripts" / "verify_done.py", repo / "scripts" / "verify_done.py")
    shutil.copy2(REPO_ROOT / "src" / "__init__.py", repo / "src" / "__init__.py")
    shutil.copy2(REPO_ROOT / "src" / "pipeline.py", repo / "src" / "pipeline.py")
    shutil.copy2(REPO_ROOT / "CONSTRAINTS.md", repo / "CONSTRAINTS.md")
    shutil.copy2(REPO_ROOT / "feature_list.json", repo / "feature_list.json")
    (repo / "SPEC.md").write_text("# Master Spec Stub\n", encoding="utf-8", newline="\n")

    (repo / "tests" / "immutable" / "test_imm.py").write_text(
        "from pathlib import Path\n"
        "from src.pipeline import run_pipeline\n"
        "def test_imm(tmp_path: Path) -> None:\n"
        "    res = run_pipeline(tmp_path, {'project_id': 'P1'})\n"
        "    assert res['stage'] == 'VIDEO_NEW'\n",
        encoding="utf-8",
        newline="\n",
    )
    (repo / "tests" / "regression" / "test_reg.py").write_text(
        "import pytest\n"
        "from pathlib import Path\n"
        "from src.pipeline import durable_replace, run_pipeline\n"
        "def test_reg(tmp_path: Path) -> None:\n"
        "    with pytest.raises(ValueError):\n"
        "        run_pipeline(tmp_path, {})\n"
        "    src_f = tmp_path / 'a.tmp'\n"
        "    dst_f = tmp_path / 'a.txt'\n"
        "    src_f.write_text('ok', encoding='utf-8')\n"
        "    out = durable_replace(src_f, dst_f)\n"
        "    assert out == dst_f\n",
        encoding="utf-8",
        newline="\n",
    )

    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "builder@localhost"],
        ["git", "config", "user.name", "Builder"],
        ["git", "add", "."],
        ["git", "commit", "-m", "Initial baseline"],
    ):
        subprocess.run(
            cmd,
            cwd=str(repo),
            check=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )

    hook_dir = repo / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "pre-commit"
    hook_path.write_text(
        "#!/bin/sh\npython scripts/verify_done.py --pre-commit || exit 1\n",
        encoding="utf-8",
        newline="\n",
    )
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
    return repo


def _run_verifier_precommit(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/verify_done.py", "--pre-commit", "--repo-root", str(repo)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        check=False,
    )


def test_pipeline_invalid_input_raises(tmp_path: Path) -> None:
    """Verify invalid pipeline inputs raise explicit exceptions."""
    with pytest.raises(TypeError):
        run_pipeline("not_a_path", {"project_id": "X"})  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        durable_replace(tmp_path / "missing.tmp", tmp_path / "dst.txt")


def test_pipeline_valid_and_durable_replace(tmp_path: Path) -> None:
    """Verify valid pipeline execution and atomic replace behave correctly."""
    src_f = tmp_path / "src.tmp"
    dst_f = tmp_path / "dst.txt"
    src_f.write_text("content_ok", encoding="utf-8")
    out = durable_replace(src_f, dst_f)
    assert out == dst_f
    assert dst_f.read_text(encoding="utf-8") == "content_ok"

    res = run_pipeline(tmp_path, {"project_id": "PROJECT_VALID"})
    assert res["project_id"] == "PROJECT_VALID"
    assert res["stage"] == "VIDEO_NEW"
    assert res["state_file"] == str(tmp_path / "work" / "PROJECT_VALID.state.json")
    assert Path(res["state_file"]).exists()


def test_sabotage_failing_earlier_test_rejected(tmp_path: Path) -> None:
    """Sabotage 1: A failing regression test causes verify_done.py and pre-commit hook to reject commit."""
    repo = _init_sandbox_repo(tmp_path)
    (repo / "tests" / "regression" / "test_reg.py").write_text(
        "def test_broken() -> None:\n    assert 1 == 2\n",
        encoding="utf-8",
        newline="\n",
    )
    res = _run_verifier_precommit(repo)
    assert res.returncode != 0
    assert "FAIL Step 1 - Tests" in res.stderr

    # Also verify git commit itself is aborted by pre-commit hook
    commit_res = subprocess.run(
        ["git", "commit", "-am", "commit broken test"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert commit_res.returncode != 0


def test_sabotage_edited_protected_file_rejected(tmp_path: Path) -> None:
    """Sabotage 2: Touching SPEC.md, CONSTRAINTS.md, verify_done.py, or tests/immutable fails."""
    repo = _init_sandbox_repo(tmp_path)
    (repo / "SPEC.md").write_text("# Tampered Spec\n", encoding="utf-8", newline="\n")
    res = _run_verifier_precommit(repo)
    assert res.returncode != 0
    assert "FAIL Step 2 - Protected Files" in res.stderr

    commit_res = subprocess.run(
        ["git", "commit", "-am", "commit tampered spec"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert commit_res.returncode != 0


def test_sabotage_six_file_diff_rejected(tmp_path: Path) -> None:
    """Sabotage 3: Modifying 6 files exceeds the 5-file change budget and fails."""
    repo = _init_sandbox_repo(tmp_path)
    for idx in range(1, 7):
        (repo / f"note_{idx}.md").write_text(f"file {idx}\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True, stdin=subprocess.DEVNULL)

    res = _run_verifier_precommit(repo)
    assert res.returncode != 0
    assert "FAIL Step 3 - Diff Budget" in res.stderr

    commit_res = subprocess.run(
        ["git", "commit", "-m", "commit 6 files"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert commit_res.returncode != 0


def test_sabotage_uncalled_function_rejected(tmp_path: Path) -> None:
    """Sabotage 4: Adding a public function in src/ that nothing calls fails static wiring."""
    repo = _init_sandbox_repo(tmp_path)
    pipeline_py = repo / "src" / "pipeline.py"
    original = pipeline_py.read_text(encoding="utf-8")
    pipeline_py.write_text(
        original + "\ndef dead_uncalled_helper() -> int:\n    return 99\n",
        encoding="utf-8",
        newline="\n",
    )
    res = _run_verifier_precommit(repo)
    assert res.returncode != 0
    assert "FAIL Step 4 - Static Wiring / Mutation" in res.stderr

    commit_res = subprocess.run(
        ["git", "commit", "-am", "commit dead code"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert commit_res.returncode != 0


def test_sabotage_readonly_lock_blocks_edit(tmp_path: Path) -> None:
    """Sabotage 5: A read-only locked file blocks write attempts from the builder process."""
    locked_file = tmp_path / "test_locked_immutable.py"
    locked_file.write_text("assert True\n", encoding="utf-8", newline="\n")
    os.chmod(locked_file, stat.S_IREAD)
    try:
        with pytest.raises(PermissionError):
            locked_file.write_text("tampered\n", encoding="utf-8")
    finally:
        os.chmod(locked_file, stat.S_IWRITE | stat.S_IREAD)
