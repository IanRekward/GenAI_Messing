"""Publish-step regression tests.

Both cases here caused a real 14-day outage: pushes were rejected server-side
("email privacy restrictions") every morning, the error was printed under
--quiet and discarded, and every run still logged "run ok".
"""
import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

import run_dashboard


class _GitRecorder:
    """Stands in for subprocess.run, replaying scripted results per git subcommand."""

    def __init__(self, backlog="1", push_rc=0, push_stderr=""):
        self.backlog = backlog
        self.push_rc = push_rc
        self.push_stderr = push_stderr
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv[1:])
        sub = argv[1]
        if sub == "diff":
            return subprocess.CompletedProcess(argv, 1, "", "")
        if sub == "rev-list":
            return subprocess.CompletedProcess(argv, 0, self.backlog + "\n", "")
        if sub == "push":
            return subprocess.CompletedProcess(argv, self.push_rc, "", self.push_stderr)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def ran(self, sub):
        return [c for c in self.calls if c and c[0] == sub]


@pytest.fixture
def dashboard_file(tmp_path):
    p = tmp_path / "dashboard.html"
    p.write_text("<html></html>", encoding="utf-8")
    return p


def _publish(dashboard_file, git, env=None):
    with patch.object(subprocess, "run", git), \
         patch.object(run_dashboard, "shutil"):
        run_dashboard._publish_to_github(dashboard_file, env or {}, quiet=True)


def test_failed_push_is_logged_not_swallowed(dashboard_file, caplog):
    git = _GitRecorder(push_rc=1, push_stderr="! [remote rejected] main -> main")
    with patch("src.alerts._send_pushover", return_value=True), \
         caplog.at_level(logging.ERROR, logger="dashboard_run"):
        _publish(dashboard_file, git)

    assert "publish failed" in caplog.text
    assert "remote rejected" in caplog.text


def test_failed_push_alerts_pushover(dashboard_file):
    git = _GitRecorder(backlog="12", push_rc=1, push_stderr="email privacy restrictions")
    with patch("src.alerts._send_pushover", return_value=True) as send:
        _publish(dashboard_file, git, env={"PUSHOVER_APP_TOKEN": "t", "PUSHOVER_USER_KEY": "u"})

    send.assert_called_once()
    title, message, _ = send.call_args[0]
    assert "FAILED" in title
    assert "12 commit(s)" in message
    assert "email privacy restrictions" in message


def test_successful_push_does_not_alert(dashboard_file):
    git = _GitRecorder(push_rc=0)
    with patch("src.alerts._send_pushover") as send:
        _publish(dashboard_file, git)

    assert git.ran("push")
    send.assert_not_called()


def test_backlog_is_pushed_even_when_nothing_staged(dashboard_file):
    """The old code returned early on an unchanged dashboard, so commits stranded
    by a prior failure were never retried."""
    git = _GitRecorder(backlog="5")
    git_diff_clean = git.__call__

    def no_staged_diff(argv, **kwargs):
        if argv[1] == "diff":
            git.calls.append(argv[1:])
            return subprocess.CompletedProcess(argv, 0, "", "")
        return git_diff_clean(argv, **kwargs)

    with patch.object(subprocess, "run", no_staged_diff), \
         patch.object(run_dashboard, "shutil"), \
         patch("src.alerts._send_pushover"):
        run_dashboard._publish_to_github(dashboard_file, {}, quiet=True)

    assert not git.ran("commit"), "nothing staged, so nothing should be committed"
    assert git.ran("push"), "the 5-commit backlog must still be pushed"


def test_no_backlog_skips_push(dashboard_file):
    git = _GitRecorder(backlog="0")
    with patch("src.alerts._send_pushover") as send:
        _publish(dashboard_file, git)

    assert not git.ran("push")
    send.assert_not_called()
