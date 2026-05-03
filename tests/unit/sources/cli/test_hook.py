from __future__ import annotations

from pathlib import Path

import pytest
from src.sources.cli.hook import (
    HOOK_MARKER_END,
    HOOK_MARKER_START,
    detect_shell,
    get_config_path,
    get_hook_template,
    install,
    is_installed,
    uninstall,
)


class TestDetectShell:
    def test_defaults_to_bash(self, monkeypatch):
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.delenv("ZSH_VERSION", raising=False)
        assert detect_shell() == "bash"

    def test_detects_zsh_from_shell(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/zsh")
        assert detect_shell() == "zsh"

    def test_detects_zsh_from_version(self, monkeypatch):
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.setenv("ZSH_VERSION", "5.8")
        assert detect_shell() == "zsh"


class TestGetConfigPath:
    def test_bash_rc(self, monkeypatch):
        monkeypatch.setattr(
            "src.sources.cli.hook.Path.home",
            lambda: __import__("pathlib").Path("/home/testuser"),
        )
        path = get_config_path("bash")
        assert path.name == ".bashrc"
        assert "testuser" in str(path)

    def test_zsh_rc(self, monkeypatch):
        monkeypatch.setattr(
            "src.sources.cli.hook.Path.home",
            lambda: __import__("pathlib").Path("/home/testuser"),
        )
        path = get_config_path("zsh")
        assert path.name == ".zshrc"
        assert "testuser" in str(path)


class TestHookTemplates:
    def test_bash_template_has_markers(self):
        template = get_hook_template("bash")
        assert HOOK_MARKER_START in template
        assert HOOK_MARKER_END in template

    def test_zsh_template_has_markers(self):
        template = get_hook_template("zsh")
        assert HOOK_MARKER_START in template
        assert HOOK_MARKER_END in template

    def test_bash_template_filters_lark_memory(self):
        template = get_hook_template("bash")
        assert '"lark-memory"' in template or "lark-memory" in template

    def test_bash_template_has_preexec(self):
        template = get_hook_template("bash")
        assert "_lark_preexec" in template

    def test_bash_template_has_precmd(self):
        template = get_hook_template("bash")
        assert "_lark_precmd" in template

    def test_bash_template_redirects_stderr(self):
        template = get_hook_template("bash")
        assert "/dev/null" in template


class TestInstallUninstall:
    def test_install_creates_config_with_markers(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        ok, msg = install("bash")
        assert ok
        content = rc_file.read_text(encoding="utf-8")
        assert HOOK_MARKER_START in content
        assert HOOK_MARKER_END in content

    def test_uninstall_removes_marker_block(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text(
            "export PATH=/usr/local/bin:$PATH\n\n"
            + get_hook_template("bash")
            + "\n\nexport EDITOR=vim\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        ok, msg = uninstall("bash")
        assert ok
        content = rc_file.read_text(encoding="utf-8")
        assert HOOK_MARKER_START not in content
        assert HOOK_MARKER_END not in content
        assert "export PATH" in content
        assert "export EDITOR" in content

    def test_install_is_idempotent(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        install("bash")
        install("bash")
        content = rc_file.read_text(encoding="utf-8")
        assert content.count(HOOK_MARKER_START) == 1
        assert content.count(HOOK_MARKER_END) == 1

    def test_uninstall_nonexistent_config(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".nonexistent"
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        ok, msg = uninstall("bash")
        assert ok

    def test_uninstall_without_hook_block(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("export PATH=/usr/bin:$PATH\n", encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        ok, msg = uninstall("bash")
        assert ok
        content = rc_file.read_text(encoding="utf-8")
        assert "export PATH" in content

    def test_is_installed_true(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text(get_hook_template("bash"), encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        assert is_installed("bash") is True

    def test_is_installed_false(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("export PATH=/usr/bin:$PATH\n", encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        assert is_installed("bash") is False

    def test_install_preserves_existing_content(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text("export PATH=/usr/bin:$PATH\n", encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        install("bash")
        content = rc_file.read_text(encoding="utf-8")
        assert "export PATH" in content
        assert HOOK_MARKER_START in content

    def test_reinstall_replaces_old_block(self, tmp_path, monkeypatch):
        rc_file = tmp_path / ".bashrc"
        rc_file.write_text(
            "export PATH=/usr/bin:$PATH\n\n"
            "# >>> LarkMemory hook >>>\n"
            "old_broken_hook_content\n"
            "# <<< LarkMemory hook <<<\n"
            "\nexport EDITOR=vim\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        install("bash")
        content = rc_file.read_text(encoding="utf-8")
        assert content.count(HOOK_MARKER_START) == 1
        assert "old_broken_hook_content" not in content
        assert "_lark_preexec" in content
