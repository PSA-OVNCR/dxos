# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""ops/pin_actions.py: đổi `uses: owner/repo@vN` thành `@<sha40> # vN` (resolver giả, không cần mạng)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("pin_actions", ROOT / "ops/pin_actions.py")
pin_actions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pin_actions)

SHA_CHECKOUT = "11bd71901bbe5b1630ceea73d27597364c9af683"
SHA_PYTHON = "a26af69be951a213d495a4c3e4e4022e16d87065"
SHA_OTHER = "0123456789abcdef0123456789abcdef01234567"
KNOWN = {("actions/checkout", "v4"): SHA_CHECKOUT, ("actions/setup-python", "v5"): SHA_PYTHON}

WORKFLOW = """name: ci
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - uses: actions/checkout@v4   # ghi chú cũ
      - run: echo "uses: actions/checkout@v4 nằm trong chuỗi lệnh, không phải bước"
"""


def _calls():
    calls = []

    def resolver(repo, tag):
        calls.append((repo, tag))
        return KNOWN.get((repo, tag), SHA_OTHER)

    return calls, resolver


def _wf(tmp_path, text=WORKFLOW):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    (d / "ci.yml").write_text(text, encoding="utf-8")
    return d


def test_rewrites_tag_to_sha_with_comment(tmp_path):
    d = _wf(tmp_path)
    calls, resolver = _calls()
    changes = pin_actions.pin(d, resolver)
    text = (d / "ci.yml").read_text(encoding="utf-8")
    assert f"      - uses: actions/checkout@{SHA_CHECKOUT} # v4\n" in text
    assert f"      - uses: actions/setup-python@{SHA_PYTHON} # v5\n" in text
    assert f"- uses: actions/checkout@{SHA_CHECKOUT} # v4 (ghi chú cũ)\n" in text      # giữ ghi chú cũ
    assert 'echo "uses: actions/checkout@v4 nằm trong chuỗi lệnh' in text        # không đụng chuỗi lệnh
    assert sorted(calls) == [("actions/checkout", "v4"), ("actions/setup-python", "v5")]  # mỗi cặp một lần
    assert len(changes) == 3


def test_subpath_action_asks_owner_repo_only(tmp_path):
    d = _wf(tmp_path, "steps:\n  - uses: github/codeql-action/analyze@v3\n")
    calls, resolver = _calls()
    pin_actions.pin(d, resolver)
    assert calls == [("github/codeql-action", "v3")]
    assert f"github/codeql-action/analyze@{SHA_OTHER} # v3\n" in (d / "ci.yml").read_text(encoding="utf-8")


def test_already_pinned_untouched(tmp_path):
    pinned = f"steps:\n  - uses: actions/checkout@{SHA_CHECKOUT} # v4\n  - uses: ./local-action\n" \
             "  - uses: docker://alpine:3.20\n"
    d = _wf(tmp_path, pinned)
    calls, resolver = _calls()
    assert pin_actions.find_uses(d) == []
    assert pin_actions.pin(d, resolver) == []
    assert calls == []                                                              # không hỏi mạng
    assert (d / "ci.yml").read_text(encoding="utf-8") == pinned                    # chạy lần hai không đổi gì


def test_run_twice_is_idempotent(tmp_path):
    d = _wf(tmp_path)
    _, resolver = _calls()
    pin_actions.pin(d, resolver)
    first = (d / "ci.yml").read_text(encoding="utf-8")
    assert pin_actions.pin(d, resolver) == []
    assert (d / "ci.yml").read_text(encoding="utf-8") == first


def test_dry_run_writes_nothing(tmp_path):
    d = _wf(tmp_path)
    calls, resolver = _calls()
    changes = pin_actions.pin(d, resolver, dry_run=True)
    assert (d / "ci.yml").read_text(encoding="utf-8") == WORKFLOW
    assert len(changes) == 3 and calls == []                                        # liệt kê, không hỏi mạng


def test_resolver_failure_leaves_every_file_untouched(tmp_path):
    d = _wf(tmp_path)

    def resolver(repo, tag):
        if repo == "actions/setup-python":
            raise ValueError("không có tag")
        return SHA_CHECKOUT

    try:
        pin_actions.pin(d, resolver)
    except ValueError as e:
        assert "không có tag" in str(e)
    else:
        raise AssertionError("phải báo lỗi khi không phân giải được")
    assert (d / "ci.yml").read_text(encoding="utf-8") == WORKFLOW


def test_sha_format_is_validated(tmp_path):
    d = _wf(tmp_path)
    try:
        pin_actions.pin(d, lambda repo, tag: "v4")
    except ValueError as e:
        assert "SHA" in str(e)
    else:
        raise AssertionError("phải từ chối SHA sai định dạng")


def test_main_dry_run_lists_without_network(tmp_path, capsys):
    d = _wf(tmp_path)
    assert pin_actions.main(["--dry-run", "--root", str(d)]) == 0
    out = capsys.readouterr().out
    assert "actions/checkout@v4" in out and "actions/setup-python@v5" in out
    assert (d / "ci.yml").read_text(encoding="utf-8") == WORKFLOW


def test_repo_workflows_are_fully_pinned():
    """Sau V37 mọi `uses:` từ xa trong kho đã là SHA 40 ký tự (find_uses chỉ liệt kê cái chưa ghim)."""
    assert pin_actions.find_uses(ROOT / ".github" / "workflows") == []


class _Run:
    def __init__(self, stdout):
        self.stdout = stdout


def _stub_ls_remote(monkeypatch, stdout):
    seen = []

    def run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return _Run(stdout)

    monkeypatch.setattr(pin_actions.subprocess, "run", run)
    return seen


def test_git_resolver_prefers_peeled_commit_of_annotated_tag(monkeypatch):
    out = f"{SHA_OTHER}\trefs/tags/v4\n{SHA_CHECKOUT}\trefs/tags/v4^{{}}\n"
    seen = _stub_ls_remote(monkeypatch, out)
    assert pin_actions.git_resolver("actions/checkout", "v4") == SHA_CHECKOUT
    cmd, kwargs = seen[0]
    assert cmd == ["git", "ls-remote", "https://github.com/actions/checkout",
                   "refs/tags/v4", "refs/tags/v4^{}"]
    assert kwargs["check"] is True and "shell" not in kwargs


def test_git_resolver_uses_lightweight_tag_when_not_annotated(monkeypatch):
    _stub_ls_remote(monkeypatch, f"{SHA_PYTHON}\trefs/tags/v5\n")
    assert pin_actions.git_resolver("actions/setup-python", "v5") == SHA_PYTHON


def test_git_resolver_rejects_missing_tag(monkeypatch):
    _stub_ls_remote(monkeypatch, "")                                            # ls-remote không thấy tag nào
    try:
        pin_actions.git_resolver("actions/checkout", "main")
    except ValueError as e:
        assert "actions/checkout" in str(e) and "main" in str(e)
    else:
        raise AssertionError("phải báo lỗi khi không có tag")
