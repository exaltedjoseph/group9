"""Git versioning of the library folder through the git CLI (commits run on a background thread)."""
from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot

from .library import slugify
from .models import Commit

INITIAL_MESSAGE = "Initialize study library"
DEFAULT_AUTHOR = "Study Library"
EMAIL_DOMAIN = "study-library.local"
_LOG_FORMAT = "%H%x1f%h%x1f%an%x1f%at%x1f%s%x1e"
_MAX_PATHSPEC_CHARS = 12_000
_QUICK_TIMEOUT = 30
_NETWORK_TIMEOUT = 300
# Edits that land within this window share one commit, since they often touch the same JSON files.
_COMMIT_SETTLE = 0.4

MSG_NO_GIT = "Git isn\u2019t installed. Install Git to keep a history of your library."
MSG_NO_REMOTE = "No remote is configured. Add a remote URL in Settings."
MSG_AUTH = "The remote rejected your credentials. Sign in to your Git host and try again."
MSG_NOT_FOUND = "The remote repository couldn\u2019t be found. Check the remote URL in Settings."
MSG_OFFLINE = "Can\u2019t reach the remote. Check your internet connection."
MSG_PUSH_REJECTED = "The remote has changes you don\u2019t have yet. Pull first, then push again."
MSG_DIVERGED = ("Your library and the remote have diverged, so they can\u2019t be merged automatically. "
                "Resolve it with Git, then try again.")
MSG_OVERWRITE = "Pulling would overwrite local changes. Commit or remove them first."
MSG_TIMEOUT = "Git took too long to respond."


class GitError(Exception):
    """A Git problem whose message is safe to show."""


def combine_messages(messages: list[str]) -> str:
    """One commit message for several edits: the first as the subject, all of them in the body."""
    unique = list(dict.fromkeys(m.strip() for m in messages if m and m.strip()))
    if len(unique) <= 1:
        return unique[0] if unique else ""
    return f"{unique[0]} (+{len(unique) - 1} more)\n\n" + "\n".join(f"- {m}" for m in unique)


def _short(output: str) -> str:
    lines = [ln.strip() for ln in (output or "").splitlines() if ln.strip()]
    useful = [ln for ln in lines if ln.lower().startswith(("fatal:", "error:"))] or lines
    text = useful[-1] if useful else ""
    for prefix in ("fatal: ", "error: "):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
    return text[:200]


def _remote_error(output: str, action: str) -> str:
    low = (output or "").lower()
    if "no configured push destination" in low or "no such remote" in low or "no remote repository" in low:
        return MSG_NO_REMOTE
    if any(s in low for s in ("authentication failed", "permission denied", "could not read username",
                              "could not read password", "access denied", "the requested url returned error: 403",
                              "the requested url returned error: 401", "invalid username or password")):
        return MSG_AUTH
    if "repository not found" in low or "does not appear to be a git repository" in low \
            or "returned error: 404" in low:
        return MSG_NOT_FOUND
    if any(s in low for s in ("could not resolve host", "failed to connect", "connection timed out",
                              "unable to access", "network is unreachable", "connection refused",
                              "could not read from remote")):
        return MSG_OFFLINE
    if "[rejected]" in low or "non-fast-forward" in low or "fetch first" in low:
        return MSG_PUSH_REJECTED
    if "not possible to fast-forward" in low or "diverg" in low or "conflict" in low:
        return MSG_DIVERGED
    if "would be overwritten" in low or "untracked working tree files" in low:
        return MSG_OVERWRITE
    if "couldn't find remote ref" in low:
        return "The remote doesn\u2019t have this branch yet. Push first."
    detail = _short(output)
    return f"Git couldn\u2019t {action}" + (f": {detail}" if detail else ".")


class GitManager(QObject):
    """Versions the library folder with Git. Lives on the GUI thread; work runs on one worker thread."""

    status_changed = Signal()
    committed = Signal(str)
    pushed = Signal()
    pulled = Signal()
    log_ready = Signal(list)
    operation_failed = Signal(str)

    _job_result = Signal(str, object)

    def __init__(self, repo_dir: Path, enabled: bool = True, auto_push: bool = False, user_name: str = "",
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.repo_dir = Path(repo_dir)
        self.enabled = bool(enabled)
        self.auto_push = bool(auto_push)
        self.user_name = (user_name or "").strip()
        self._exe: str | None | bool = False
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._pending = 0
        self._lock = threading.Lock()
        self._closed = False
        self._job_result.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    # ================================================================== process helpers
    def _git_exe(self) -> str | None:
        if self._exe is False:
            self._exe = shutil.which("git")
        return self._exe or None

    def _run(self, *args: str, timeout: float = _QUICK_TIMEOUT) -> subprocess.CompletedProcess:
        exe = self._git_exe()
        if not exe:
            raise GitError(MSG_NO_GIT)
        env = os.environ.copy()
        env.update({"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "LANGUAGE": "en"})
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        cmd = [exe, "-c", "core.quotepath=false", "-c", "commit.gpgsign=false", *args]
        try:
            return subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", stdin=subprocess.DEVNULL, timeout=timeout, env=env, **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise GitError(MSG_TIMEOUT) from exc
        except OSError as exc:
            raise GitError(f"Git couldn\u2019t run: {exc.strerror or exc}") from exc

    def _out(self, *args: str, timeout: float = _QUICK_TIMEOUT) -> str:
        r = self._run(*args, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""

    def _check(self, *args: str, action: str, timeout: float = _QUICK_TIMEOUT) -> subprocess.CompletedProcess:
        r = self._run(*args, timeout=timeout)
        if r.returncode != 0:
            raise GitError(f"Git couldn\u2019t {action}: {_short(r.stderr or r.stdout)}")
        return r

    # ================================================================== state
    def available(self) -> bool:
        return self._git_exe() is not None

    def is_repo(self) -> bool:
        if not self.available() or not self.repo_dir.is_dir():
            return False
        try:
            return self._out("rev-parse", "--is-inside-work-tree") == "true"
        except GitError:
            return False

    def _has_commits(self) -> bool:
        return self._run("rev-parse", "--verify", "-q", "HEAD").returncode == 0

    def busy(self) -> bool:
        with self._lock:
            return self._pending > 0

    def branch(self) -> str:
        if not self.is_repo():
            return ""
        try:
            return self._out("branch", "--show-current") or self._out("rev-parse", "--short", "HEAD")
        except GitError:
            return ""

    def _remote_name(self) -> str:
        remotes = self._out("remote").split()
        if not remotes:
            return ""
        return "origin" if "origin" in remotes else remotes[0]

    def has_remote(self) -> bool:
        if not self.is_repo():
            return False
        try:
            return bool(self._remote_name())
        except GitError:
            return False

    def remote_url(self) -> str:
        if not self.is_repo():
            return ""
        try:
            name = self._remote_name()
            return self._out("remote", "get-url", name) if name else ""
        except GitError:
            return ""

    # ================================================================== settings
    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.status_changed.emit()

    def set_auto_push(self, auto_push: bool) -> None:
        self.auto_push = bool(auto_push)
        self.status_changed.emit()

    def set_user_name(self, name: str) -> None:
        """Updates the author name; also rewrites the repo identity if this app created it."""
        self.user_name = (name or "").strip()
        if not self.is_repo():
            return
        try:
            local_email = self._out("config", "--local", "--get", "user.email")
            if local_email.endswith("@" + EMAIL_DOMAIN):
                self._run("config", "--local", "user.name", self.user_name or DEFAULT_AUTHOR)
                self._run("config", "--local", "user.email", self._email())
        except GitError:
            pass

    def _email(self) -> str:
        return f"{slugify(self.user_name or DEFAULT_AUTHOR, 'study-library')}@{EMAIL_DOMAIN}"

    def set_remote(self, url: str) -> bool:
        """Sets (or with an empty url removes) the `origin` remote. Synchronous."""
        url = (url or "").strip()
        try:
            self._ensure_repo()
            remotes = self._out("remote").split()
            if not url:
                if "origin" in remotes:
                    self._check("remote", "remove", "origin", action="remove the remote")
            elif "origin" in remotes:
                self._check("remote", "set-url", "origin", url, action="change the remote")
            else:
                self._check("remote", "add", "origin", url, action="add the remote")
        except GitError as exc:
            self.operation_failed.emit(str(exc))
            return False
        self.status_changed.emit()
        return True

    # ================================================================== repository setup
    def ensure_repo(self) -> bool:
        """Makes sure the library folder is in a Git repo with at least one commit. Synchronous."""
        if not self.enabled:
            return False
        try:
            self._ensure_repo()
        except GitError as exc:
            self.operation_failed.emit(str(exc))
            return False
        self.status_changed.emit()
        return True

    def _ensure_repo(self) -> None:
        if not self.available():
            raise GitError(MSG_NO_GIT)
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        if self._run("rev-parse", "--show-toplevel").returncode != 0:
            if self._run("init", "-b", "main").returncode != 0:
                self._check("init", action="create a repository")
                self._run("symbolic-ref", "HEAD", "refs/heads/main")
        self._ensure_identity()
        if not self._has_commits():
            self._check("add", "-A", "--", ".", action="add the library files")
            if self._run("diff", "--cached", "--quiet", "--", ".").returncode != 0:
                self._check("commit", "--no-verify", "-q", "-m", INITIAL_MESSAGE, "--", ".",
                            action="create the first commit")
            else:
                self._check("commit", "--no-verify", "-q", "--allow-empty", "-m", INITIAL_MESSAGE,
                            action="create the first commit")

    def _ensure_identity(self) -> None:
        if not self._out("config", "--get", "user.name"):
            self._run("config", "--local", "user.name", self.user_name or DEFAULT_AUTHOR)
        if not self._out("config", "--get", "user.email"):
            self._run("config", "--local", "user.email", self._email())

    # ================================================================== history
    def log(self, limit: int = 100) -> list[Commit]:
        """Most recent commits touching the library folder. Synchronous."""
        try:
            if not self.is_repo() or not self._has_commits():
                return []
            r = self._run("log", "-n", str(max(1, int(limit))), "--date=unix", f"--pretty=format:{_LOG_FORMAT}",
                          "--", ".")
        except GitError:
            return []
        if r.returncode != 0:
            return []
        commits = []
        for record in r.stdout.split("\x1e"):
            fields = record.strip("\r\n").split("\x1f")
            if len(fields) < 5:
                continue
            full, short, author, ts, subject = fields[:5]
            try:
                stamp = float(ts)
            except ValueError:
                stamp = 0.0
            commits.append(Commit(full.strip(), short.strip(), author, stamp, subject))
        return commits

    # ================================================================== async jobs
    def commit(self, message: str, paths: list[str] | tuple[str, ...] = ()) -> None:
        """Queues a commit of `paths` (relative to the library folder). No-op when disabled."""
        if not self.enabled:
            return
        self._submit("commit", message, [str(p) for p in paths if str(p).strip()])

    def push(self) -> None:
        self._submit("push")

    def pull(self) -> None:
        self._submit("pull")

    def request_log(self, limit: int = 100) -> None:
        self._submit("log", limit)

    def _submit(self, kind: str, *args) -> None:
        if self._closed:
            return
        with self._lock:
            self._pending += 1
            first = self._pending == 1
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._worker, name="GitWorker", daemon=True)
                self._thread.start()
        self._queue.put((kind, args))
        if first:
            self.status_changed.emit()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Lets queued jobs finish (up to `timeout_ms`) and stops the worker."""
        self._closed = True
        thread = self._thread
        if thread is not None and thread.is_alive():
            self._queue.put(None)
            thread.join(max(0, timeout_ms) / 1000)

    def _take_commits(self, args: tuple, backlog: list) -> tuple[tuple, int]:
        """Merges every queued commit into this one; other jobs keep their order in `backlog`."""
        if not self._closed:
            time.sleep(_COMMIT_SETTLE)
        messages, paths, everything = [args[0]], list(args[1]), not args[1]
        merged = 1
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            if job is not None and job[0] == "commit":
                messages.append(job[1][0])
                paths.extend(job[1][1])
                everything = everything or not job[1][1]
                merged += 1
            else:
                backlog.append(job)
        return (combine_messages(messages), [] if everything else paths), merged

    def _worker(self) -> None:
        backlog: list = []
        while True:
            job = backlog.pop(0) if backlog else self._queue.get()
            if job is None:
                return
            kind, args = job
            merged = 1
            if kind == "commit":
                args, merged = self._take_commits(args, backlog)
            try:
                handler = {"commit": self._do_commit, "push": self._do_push, "pull": self._do_pull,
                           "log": self._do_log}[kind]
                handler(*args)
            except GitError as exc:
                self._job_result.emit("failed", str(exc))
            except Exception as exc:
                self._job_result.emit("failed", f"Git ran into a problem: {type(exc).__name__}: {exc}"[:240])
            finally:
                with self._lock:
                    self._pending -= merged
                    idle = self._pending == 0
                if idle:
                    self._job_result.emit("status", None)

    @Slot(str, object)
    def _deliver(self, kind: str, payload) -> None:
        if kind == "committed":
            self.committed.emit(payload)
        elif kind == "pushed":
            self.pushed.emit()
        elif kind == "pulled":
            self.pulled.emit()
        elif kind == "log":
            self.log_ready.emit(payload)
        elif kind == "failed":
            self.operation_failed.emit(payload)
        if kind != "log":
            self.status_changed.emit()

    def _pathspec(self, paths: list[str]) -> list[str]:
        paths = sorted({p.replace("\\", "/") for p in paths}) or ["."]
        if sum(len(p) + 3 for p in paths) > _MAX_PATHSPEC_CHARS:
            return ["."]
        if paths == ["."]:
            return paths
        tracked = {t for t in self._out("ls-files", "-z", "--", *paths).split("\0") if t}
        keep = [p for p in paths if (self.repo_dir / p).exists() or p in tracked
                or any(t.startswith(p.rstrip("/") + "/") for t in tracked)]
        return keep

    def _do_commit(self, message: str, paths: list[str]) -> None:
        if not self.enabled:
            return
        if not self.is_repo() or not self._has_commits():
            self._ensure_repo()
        else:
            self._ensure_identity()
        spec = self._pathspec(paths)
        if not spec:
            return
        self._check("add", "-A", "--", *spec, action="stage the changes")
        if self._run("diff", "--cached", "--quiet", "--", *spec).returncode == 0:
            return
        message = (message or "").strip() or "Update library"
        self._check("commit", "--no-verify", "-q", "-m", message, "--", *spec, action="commit the changes")
        self._job_result.emit("committed", self._out("rev-parse", "--short", "HEAD"))
        if self.auto_push and self._remote_name():
            self._do_push()

    def _do_push(self) -> None:
        if not self.is_repo():
            raise GitError(MSG_NO_REMOTE)
        remote = self._remote_name()
        if not remote:
            raise GitError(MSG_NO_REMOTE)
        branch = self._out("branch", "--show-current")
        has_upstream = self._run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0
        args = ["push"] if has_upstream or not branch else ["push", "-u", remote, branch]
        r = self._run(*args, timeout=_NETWORK_TIMEOUT)
        if r.returncode != 0:
            raise GitError(_remote_error(r.stderr or r.stdout, "push"))
        self._job_result.emit("pushed", None)

    def _do_pull(self) -> None:
        if not self.is_repo():
            raise GitError(MSG_NO_REMOTE)
        remote = self._remote_name()
        if not remote:
            raise GitError(MSG_NO_REMOTE)
        has_upstream = self._run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0
        branch = self._out("branch", "--show-current")
        args = ["pull", "--ff-only"] if has_upstream or not branch else ["pull", "--ff-only", remote, branch]
        r = self._run(*args, timeout=_NETWORK_TIMEOUT)
        if r.returncode != 0:
            raise GitError(_remote_error(r.stderr or r.stdout, "pull"))
        self._job_result.emit("pulled", None)

    def _do_log(self, limit: int) -> None:
        self._job_result.emit("log", self.log(limit))
