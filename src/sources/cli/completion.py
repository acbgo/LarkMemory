from __future__ import annotations

BASH_COMPLETION = r"""# LarkMemory Tab completion (bash)
# Source this file or run: source <(lark-memory completion bash)

_lark_memory_complete() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local line="${COMP_LINE}"
    local result
    result=$(lark-memory complete -- "$line" "$cur" 2>/dev/null)
    if [ -n "$result" ]; then
        local IFS=$'\n'
        COMPREPLY=($(compgen -W "$result" -- "$cur"))
    fi
    return 0
}

# Register as default fallback: triggers when a command has no native completion
complete -D -F _lark_memory_complete -o default 2>/dev/null || true
"""

ZSH_COMPLETION = r"""# LarkMemory Tab completion (zsh)
# Source this file or run: source <(lark-memory completion zsh)

_lark_memory_complete_zsh() {
    local line="${BUFFER}"
    local cur="${words[$CURRENT]}"
    local result
    result=$(lark-memory complete -- "$line" "$cur" 2>/dev/null)
    if [ -n "$result" ]; then
        local -a candidates
        candidates=("${(@f)result}")
        compadd -a -- candidates
    fi
    return 0
}

# Register as catch-all fallback completer
_lark_memory_complete_zsh "$@"
"""

# Wrapper function for zsh catch-all behavior
ZSH_COMPLETER_WRAPPER = r"""_lark_memory_complete_wrapper() {
    _lark_memory_complete_zsh
}
compdef _lark_memory_complete_wrapper '*' 2>/dev/null || true
"""


ZSH_AUTOSUGGEST_STRATEGY = r"""# LarkMemory zsh-autosuggestions strategy
# Provides inline grey-text preview of command parameters based on memory.
# Requires: zsh-autosuggestions plugin

_lark_memory_suggestion() {
    local cmd="${1:-$BUFFER}"
    [ -z "$cmd" ] && return
    local suggestion
    suggestion=$(lark-memory complete -- "$cmd" "" 2>/dev/null | head -1)
    [ -n "$suggestion" ] && echo "$suggestion"
}

# Register as the primary suggestion strategy
ZSH_AUTOSUGGEST_STRATEGY=(_lark_memory_suggestion $ZSH_AUTOSUGGEST_STRATEGY)
"""


def get_autosuggestion_strategy() -> str:
    return ZSH_AUTOSUGGEST_STRATEGY


def get_completion_script(shell: str) -> str:
    if shell == "zsh":
        return ZSH_COMPLETION + "\n" + ZSH_COMPLETER_WRAPPER
    return BASH_COMPLETION
