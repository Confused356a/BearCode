#!/usr/bin/env python3

from rich.console import Console
import sys
console = Console(highlight=False)



def print_info(msg:str)->None:
    console.print(f"\n  [cyan]ℹ {msg}[/cyan]")



def print_divider() -> None:
    console.print(f"\n[dim]  {'─' * 50}[/dim]")


def print_assistant_text(text:str)->None:
    sys.stdout.write(text)
    sys.stdout.flush()



# ─── Sub-agent display ──────────────────────────────────────


def print_sub_agent_start(agent_type: str, description: str) -> None:
    console.print(f"\n  [magenta]┌─ Sub-agent [{agent_type}]: {description}[/magenta]")


def print_sub_agent_end(agent_type: str, _description: str) -> None:
    console.print(f"  [magenta]└─ Sub-agent [{agent_type}] completed[/magenta]")