"""Shell completion scripts for bash, zsh, and fish."""
from __future__ import annotations
COMMANDS = "status scan pull push sync force-sync release release-manager undo-redo doctor config theme init notes time completion watch diff conflict repos pr issue actions plugins"
BASH = r'''_hikari_completion() {
 local cur prev; COMPREPLY=(); cur="${COMP_WORDS[COMP_CWORD]}"; prev="${COMP_WORDS[COMP_CWORD-1]}"
 local commands="status scan pull push sync force-sync release release-manager undo-redo doctor config theme init notes time completion watch diff conflict repos pr issue actions plugins"
 case "${prev}" in release) COMPREPLY=($(compgen -W "patch current custom minor major" -- "${cur}")); return 0;; esac
 if [[ ${cur} == -* ]]; then COMPREPLY=($(compgen -W "--help --version --yes --json" -- "${cur}")); else COMPREPLY=($(compgen -W "${commands}" -- "${cur}") $(compgen -d -- "${cur}")); fi
}
complete -F _hikari_completion hikari
'''
ZSH = '#compdef hikari\n_arguments "1:command:(' + COMMANDS + ')" "*::arg:->args"\n'
FISH = "\n".join(f'complete -c hikari -n "__fish_use_subcommand" -a "{c}"' for c in COMMANDS.split()) + "\n"
TEMPLATES = {"bash": BASH, "zsh": ZSH, "fish": FISH}
def render(shell: str) -> str:
    if shell not in TEMPLATES: raise ValueError("shell must be bash, zsh, or fish")
    return TEMPLATES[shell]
