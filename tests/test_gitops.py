from __future__ import annotations

import shutil
import subprocess

import pytest

from app.core import gitops
from app.core.gitops import GitManager
from app.core.models import Commit
from tests.conftest import wait_until

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.fixture(autouse=True)
def isolated_git_config(tmp_path, monkeypatch):
    """Keeps the user's global/system Git config (identity, hooks, signing) out of the tests."""
    cfg = tmp_path / "gitconfig"
    cfg.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(var, raising=False)


def git(cwd, *args) -> str:
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    (root / "syllabus.json").write_text("{}", encoding="utf-8")
    (root / ".gitignore").write_text(".index/\n", encoding="utf-8")
    (root / ".index").mkdir()
    (root / ".index" / "index.db").write_bytes(b"db")
    return root


@pytest.fixture
def manager(repo, qapp):
    m = GitManager(repo, user_name="Ana Lopes")
    yield m
    m.shutdown(5000)


def collect(m: GitManager) -> dict[str, list]:
    events: dict[str, list] = {"committed": [], "failed": [], "pushed": [], "pulled": [], "log": [], "status": []}
    m.committed.connect(events["committed"].append)
    m.operation_failed.connect(events["failed"].append)
    m.pushed.connect(lambda: events["pushed"].append(True))
    m.pulled.connect(lambda: events["pulled"].append(True))
    m.log_ready.connect(events["log"].append)
    m.status_changed.connect(lambda: events["status"].append(True))
    return events


def test_ensure_repo_creates_repo_and_initial_commit(manager, repo):
    assert manager.available()
    assert not manager.is_repo()
    assert manager.ensure_repo()
    assert (repo / ".git").is_dir() and manager.is_repo()
    assert manager.branch() == "main"
    assert git(repo, "log", "--format=%s") == "Initialize study library"
    assert git(repo, "ls-files").splitlines() == [".gitignore", "syllabus.json"]
    assert git(repo, "config", "--local", "user.name") == "Ana Lopes"
    assert git(repo, "config", "--local", "user.email") == "ana-lopes@study-library.local"
    assert manager.ensure_repo()
    assert len(manager.log()) == 1


def test_ensure_repo_keeps_existing_identity(repo, qapp, tmp_path, monkeypatch):
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = Global Person\n\temail = global@example.com\n", encoding="utf-8")
    m = GitManager(repo)
    try:
        assert m.ensure_repo()
        assert git(repo, "log", "--format=%an <%ae>") == "Global Person <global@example.com>"
    finally:
        m.shutdown()


def test_ensure_repo_uses_enclosing_work_tree(tmp_path, qapp):
    outer = tmp_path / "project"
    lib_dir = outer / "library"
    lib_dir.mkdir(parents=True)
    git(outer, "init", "-q", "-b", "main")
    (outer / "unrelated.txt").write_text("x", encoding="utf-8")
    (lib_dir / "syllabus.json").write_text("{}", encoding="utf-8")
    m = GitManager(lib_dir)
    try:
        assert m.ensure_repo()
        assert not (lib_dir / ".git").exists()
        assert git(outer, "ls-files").splitlines() == ["library/syllabus.json"]
        assert "unrelated.txt" in git(outer, "status", "--porcelain")
        assert [c.message for c in m.log()] == ["Initialize study library"]
    finally:
        m.shutdown()


def test_commit_only_given_paths(manager, repo):
    manager.ensure_repo()
    events = collect(manager)
    (repo / "data").mkdir()
    (repo / "data" / "resources.json").write_text("[1]", encoding="utf-8")
    (repo / "resources").mkdir()
    (repo / "resources" / "notes \u2013 caf\u00e9.txt").write_text("hi", encoding="utf-8")
    (repo / "other.txt").write_text("not mine", encoding="utf-8")
    (repo / "staged.txt").write_text("staged elsewhere", encoding="utf-8")
    git(repo, "add", "staged.txt")

    manager.commit("Add resource: Caf\u00e9 \u201cnotes\u201d",
                   ["data/resources.json", "resources/notes \u2013 caf\u00e9.txt"])
    assert wait_until(lambda: events["committed"] or events["failed"])
    assert events["failed"] == []
    short = events["committed"][0]
    assert short and git(repo, "rev-parse", "--short", "HEAD") == short
    assert git(repo, "log", "-1", "--format=%s") == "Add resource: Caf\u00e9 \u201cnotes\u201d"
    files = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(files) == ["data/resources.json", "resources/notes \u2013 caf\u00e9.txt"]
    status = git(repo, "status", "--porcelain")
    assert "?? other.txt" in status and "A  staged.txt" in status
    assert wait_until(lambda: not manager.busy())
    assert events["status"]


def test_combine_messages():
    assert gitops.combine_messages([]) == ""
    assert gitops.combine_messages(["Add resource: A", " Add resource: A "]) == "Add resource: A"
    assert gitops.combine_messages(["Add resource: A", "Edit resource: B"]) == (
        "Add resource: A (+1 more)\n\n- Add resource: A\n- Edit resource: B")


def test_quick_commits_merge_into_one(manager, repo):
    manager.ensure_repo()
    events = collect(manager)
    (repo / "data").mkdir()
    (repo / "data" / "resources.json").write_text("[1]", encoding="utf-8")
    manager.commit("Add resource: A", ["data/resources.json"])
    (repo / "data" / "resources.json").write_text("[1, 2]", encoding="utf-8")
    (repo / "syllabus.json").write_text('{"v": 2}', encoding="utf-8")
    manager.commit("Edit resource: B", ["data/resources.json", "syllabus.json"])
    manager.request_log(10)
    assert wait_until(lambda: events["log"] and not manager.busy())
    assert events["failed"] == [] and len(events["committed"]) == 1
    assert git(repo, "log", "-1", "--format=%s") == "Add resource: A (+1 more)"
    assert "- Edit resource: B" in git(repo, "log", "-1", "--format=%b")
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()) == [
        "data/resources.json", "syllabus.json"]
    assert git(repo, "status", "--porcelain") == ""
    assert [c.message for c in events["log"][-1]][:2] == ["Add resource: A (+1 more)", "Initialize study library"]


def test_commit_deletions_and_missing_paths(manager, repo):
    manager.ensure_repo()
    events = collect(manager)
    (repo / "syllabus.json").unlink()
    manager.commit("Delete syllabus", ["syllabus.json", "resources/never-existed.pdf"])
    assert wait_until(lambda: events["committed"] or events["failed"])
    assert events["failed"] == []
    assert "syllabus.json" not in git(repo, "ls-files").splitlines()


def test_commit_without_changes_is_silent(manager, repo):
    manager.ensure_repo()
    events = collect(manager)
    manager.commit("Nothing", ["syllabus.json"])
    manager.request_log(10)
    assert wait_until(lambda: events["log"])
    assert events["committed"] == [] and events["failed"] == []
    assert len(git(repo, "log", "--format=%h").splitlines()) == 1


def test_commit_creates_repo_lazily(manager, repo):
    events = collect(manager)
    (repo / "new.txt").write_text("x", encoding="utf-8")
    manager.commit("Add new", ["new.txt"])
    assert wait_until(lambda: not manager.busy() and (events["status"] or events["failed"]))
    assert events["failed"] == []
    assert manager.is_repo()
    assert [c.message for c in manager.log()] == ["Initialize study library"]


def test_disabled_commit_is_noop(manager, repo):
    manager.ensure_repo()
    manager.set_enabled(False)
    events = collect(manager)
    (repo / "x.txt").write_text("x", encoding="utf-8")
    manager.commit("Should not happen", ["x.txt"])
    assert not manager.busy()
    assert wait_until(lambda: False, timeout=0.3) is False
    assert events["committed"] == []
    assert len(manager.log()) == 1
    assert manager.ensure_repo() is False


def test_log_returns_commits(manager, repo):
    manager.ensure_repo()
    events = collect(manager)
    for i in range(3):
        (repo / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        manager.commit(f"Add f{i} \u2014 \u00e9t\u00e9", [f"f{i}.txt"])
        assert wait_until(lambda: len(events["committed"]) == i + 1 or events["failed"])
    commits = manager.log()
    assert all(isinstance(c, Commit) for c in commits)
    assert [c.message for c in commits] == ["Add f2 \u2014 \u00e9t\u00e9", "Add f1 \u2014 \u00e9t\u00e9",
                                            "Add f0 \u2014 \u00e9t\u00e9", "Initialize study library"]
    c = commits[0]
    assert len(c.hash) == 40 and c.hash.startswith(c.short_hash) and c.short_hash == events["committed"][-1]
    assert c.author == "Ana Lopes" and c.timestamp > 1_600_000_000
    assert len(manager.log(limit=2)) == 2
    manager.request_log(2)
    assert wait_until(lambda: events["log"])
    assert [x.hash for x in events["log"][0]] == [x.hash for x in commits[:2]]


def test_remote_push_and_pull(manager, repo, tmp_path):
    manager.ensure_repo()
    events = collect(manager)
    assert not manager.has_remote() and manager.remote_url() == ""
    manager.push()
    assert wait_until(lambda: events["failed"])
    assert events["failed"][0] == gitops.MSG_NO_REMOTE

    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    assert manager.set_remote(str(bare))
    assert manager.has_remote() and manager.remote_url() == str(bare)
    manager.push()
    assert wait_until(lambda: events["pushed"] or len(events["failed"]) > 1)
    assert len(events["failed"]) == 1
    assert git(bare, "log", "--format=%s", "main") == "Initialize study library"

    manager.set_auto_push(True)
    (repo / "auto.txt").write_text("a", encoding="utf-8")
    manager.commit("Auto pushed", ["auto.txt"])
    assert wait_until(lambda: len(events["pushed"]) == 2 or len(events["failed"]) > 1)
    assert git(bare, "log", "-1", "--format=%s", "main") == "Auto pushed"

    manager.pull()
    assert wait_until(lambda: events["pulled"] or len(events["failed"]) > 1)
    assert events["pulled"] == [True] and len(events["failed"]) == 1

    assert manager.set_remote("")
    assert not manager.has_remote()


def test_git_missing(repo, qapp, monkeypatch):
    monkeypatch.setattr(gitops.shutil, "which", lambda name: None)
    m = GitManager(repo)
    events = collect(m)
    try:
        assert m.available() is False
        assert m.is_repo() is False
        assert m.ensure_repo() is False
        assert events["failed"] == [gitops.MSG_NO_GIT]
        assert m.log() == [] and m.branch() == "" and m.remote_url() == "" and not m.has_remote()
        m.commit("x", ["syllabus.json"])
        assert wait_until(lambda: len(events["failed"]) == 2)
        assert events["failed"][1] == gitops.MSG_NO_GIT
        assert not (repo / ".git").exists()
    finally:
        m.shutdown()


def test_shutdown_drains_queue(manager, repo):
    manager.ensure_repo()
    for i in range(3):
        (repo / f"s{i}.txt").write_text(str(i), encoding="utf-8")
        manager.commit(f"S{i}", [f"s{i}.txt"])
    manager.shutdown(15_000)
    assert [c.message for c in manager.log(2)] == ["S0 (+2 more)", "Initialize study library"]
    assert git(repo, "status", "--porcelain") == ""
    manager.commit("After shutdown", ["syllabus.json"])
    assert not manager.busy()


def test_set_user_name_updates_app_identity(manager, repo):
    manager.ensure_repo()
    manager.set_user_name("Ben")
    assert git(repo, "config", "--local", "user.name") == "Ben"
    assert git(repo, "config", "--local", "user.email") == "ben@study-library.local"
