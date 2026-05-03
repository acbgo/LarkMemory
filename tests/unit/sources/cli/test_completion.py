from __future__ import annotations

from src.sources.cli.completion import BASH_COMPLETION, ZSH_COMPLETION, get_completion_script


class TestGetCompletionScript:
    def test_bash_script_calls_lark_memory_complete(self):
        script = get_completion_script("bash")
        assert "lark-memory complete" in script
        assert "_lark_memory_complete" in script
        assert "COMPREPLY" in script

    def test_bash_script_has_silent_failure(self):
        script = get_completion_script("bash")
        assert "2>/dev/null" in script
        assert "return 0" in script

    def test_bash_script_uses_default_fallback(self):
        script = get_completion_script("bash")
        assert "complete -D" in script

    def test_zsh_script_calls_lark_memory_complete(self):
        script = get_completion_script("zsh")
        assert "lark-memory complete" in script
        assert "_lark_memory_complete_zsh" in script

    def test_zsh_script_has_silent_failure(self):
        script = get_completion_script("zsh")
        assert "2>/dev/null" in script
        assert "return 0" in script

    def test_zsh_script_is_catch_all(self):
        script = get_completion_script("zsh")
        assert "compdef" in script

    def test_bash_script_does_not_contain_zsh_specific(self):
        script = get_completion_script("bash")
        assert "compdef" not in script
        assert "zsh" not in script.lower()

    def test_zsh_script_uses_compadd(self):
        script = get_completion_script("zsh")
        assert "compadd" in script

    def test_autosuggest_strategy_calls_complete(self):
        from src.sources.cli.completion import get_autosuggestion_strategy
        strategy = get_autosuggestion_strategy()
        assert "lark-memory complete" in strategy
        assert "_lark_memory_suggestion" in strategy
        assert "ZSH_AUTOSUGGEST_STRATEGY" in strategy
        assert "2>/dev/null" in strategy
