from __future__ import annotations

import shutil
import uuid
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


@pytest.fixture
def temp_dir():
    root = Path.cwd() / ".tmp-tests"
    root.mkdir(exist_ok=True)
    d = root / f"cli-hook-{uuid.uuid4().hex}"
    d.mkdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)


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

    def test_bash_template_has_completion_function(self):
        template = get_hook_template("bash")
        assert "_lark_memory_complete" in template
        assert "complete -D" in template

    def test_bash_insert_completion_appends_all_suggestions(self):
        template = get_hook_template("bash")
        assert "local suggestions=($result)" in template
        assert 'result="${suggestions[*]}"' in template
        assert '"\\e[Z": _lark_memory_insert_completion' in template
        assert "| head -1" not in template

    def test_zsh_template_has_completion_function(self):
        template = get_hook_template("zsh")
        assert "_lark_memory_complete_zsh" in template
        assert "compdef" in template


class TestInstallUninstall:
    def _rc_file(self, temp_dir: Path) -> Path:
        return temp_dir / ".bashrc"

    def test_install_creates_config_with_markers(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        ok, msg = install("bash")
        assert ok
        content = rc_file.read_text(encoding="utf-8")
        assert HOOK_MARKER_START in content
        assert HOOK_MARKER_END in content

    def test_uninstall_removes_marker_block(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
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

    def test_install_is_idempotent(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        install("bash")
        install("bash")
        content = rc_file.read_text(encoding="utf-8")
        assert content.count(HOOK_MARKER_START) == 1
        assert content.count(HOOK_MARKER_END) == 1

    def test_uninstall_nonexistent_config(self, temp_dir, monkeypatch):
        rc_file = temp_dir / ".nonexistent"
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        ok, msg = uninstall("bash")
        assert ok

    def test_uninstall_without_hook_block(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
        rc_file.write_text("export PATH=/usr/bin:$PATH\n", encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        ok, msg = uninstall("bash")
        assert ok
        content = rc_file.read_text(encoding="utf-8")
        assert "export PATH" in content

    def test_is_installed_true(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
        rc_file.write_text(get_hook_template("bash"), encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        assert is_installed("bash") is True

    def test_is_installed_false(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
        rc_file.write_text("export PATH=/usr/bin:$PATH\n", encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        assert is_installed("bash") is False

    def test_install_preserves_existing_content(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
        rc_file.write_text("export PATH=/usr/bin:$PATH\n", encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        install("bash")
        content = rc_file.read_text(encoding="utf-8")
        assert "export PATH" in content
        assert HOOK_MARKER_START in content

    def test_install_bash_optimizes_inputrc(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
        inputrc = temp_dir / ".inputrc"
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        monkeypatch.setattr(
            "src.sources.cli.hook.Path.home",
            lambda: temp_dir,
        )
        install("bash")
        assert inputrc.exists()
        content = inputrc.read_text(encoding="utf-8")
        assert "show-all-if-ambiguous" in content

    def test_install_zsh_creates_autosuggest_strategy(self, temp_dir, monkeypatch):
        rc_file = temp_dir / ".zshrc"
        lark_dir = temp_dir / ".larkmemory"
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        monkeypatch.setattr(
            "src.sources.cli.hook.Path.home",
            lambda: temp_dir,
        )
        install("zsh")
        strategy_file = lark_dir / "zsh-autosuggest-strategy.zsh"
        assert strategy_file.exists()
        content = strategy_file.read_text(encoding="utf-8")
        assert "ZSH_AUTOSUGGEST_STRATEGY" in content

    def test_uninstall_cleans_strategy_file(self, temp_dir, monkeypatch):
        rc_file = temp_dir / ".zshrc"
        rc_file.write_text(get_hook_template("zsh"), encoding="utf-8")
        lark_dir = temp_dir / ".larkmemory"
        lark_dir.mkdir()
        strategy_file = lark_dir / "zsh-autosuggest-strategy.zsh"
        strategy_file.write_text("strategy", encoding="utf-8")
        monkeypatch.setattr(
            "src.sources.cli.hook.get_config_path",
            lambda shell=None: rc_file,
        )
        monkeypatch.setattr(
            "src.sources.cli.hook.Path.home",
            lambda: temp_dir,
        )
        uninstall("zsh")
        assert not strategy_file.exists()

    def test_reinstall_replaces_old_block(self, temp_dir, monkeypatch):
        rc_file = self._rc_file(temp_dir)
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
