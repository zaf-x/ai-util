"""
CLI Entry Point — argparse dispatch for interactive and one-shot modes.

Usage:
    ai-chat                              # Interactive curses chat
    ai-chat --prompt "Hello"             # One-shot mode
    ai-chat --prompt "Hello" --stream    # One-shot with streaming
    python -m ai_util.cli                # Same as ai-chat

Exports:
    main (console_scripts entry point)
"""

import argparse
import sys
from typing import Any, Dict, List, Optional

from .bot import AIBot
from .tools import Tools
from .agent import Agent
from .cli_config import load_config, merge_with_cli_args
from .cli_curses import run_curses_app


__all__ = [
    "main",
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-chat",
        description="AI Chat CLI — interactive chat with AI models",
    )
    parser.add_argument("--api-key", help="OpenAI-compatible API key")
    parser.add_argument("--base-url", help="Custom API base URL")
    parser.add_argument("--model", help="Model name (default: gpt-4o)")
    parser.add_argument("--temperature", type=float, help="Sampling temperature (0–2)")
    parser.add_argument("--system-prompt", help="System prompt for the AI")
    parser.add_argument("--prompt", help="One-shot prompt mode (non-interactive)")
    parser.add_argument("--stream", action="store_true", default=None,
                        help="Stream output in one-shot mode")
    parser.add_argument("--no-stream", action="store_true", default=None,
                        help="Non-streaming output in one-shot mode")
    parser.add_argument("--config", help="Path to config file")
    return parser


def _create_agent(config: Dict[str, Any]) -> Agent:
    """Create an Agent from a config dict."""
    bot = AIBot(
        api_key=config.get("api_key"),
        base_url=config.get("base_url"),
        model=config.get("model", "gpt-4o"),
        system_prompt=config.get("system_prompt"),
        temperature=config.get("temperature", 0.7),
    )
    tools = Tools()
    return Agent(bot=bot, tools=tools)


def _run_one_shot(agent: Agent, prompt: str, use_stream: bool) -> None:
    """Run in one-shot mode: print response and exit."""
    if use_stream:
        for event in agent.stream_msg(prompt):
            if event["type"] == "content":
                print(event["data"], end="", flush=True)
            elif event["type"] == "done":
                print()
            elif event["type"] == "error":
                print(f"\nError: {event['data']}", file=sys.stderr)
    else:
        result = agent.send_msg(prompt)
        content = result.get("content", "") or ""
        print(content)


def _resolve_stream_flag(args: Any) -> bool:
    """Determine whether to use streaming in one-shot mode."""
    if args.stream:
        return True
    if args.no_stream:
        return False
    return sys.stdout.isatty()


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for ai-chat."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    merge_with_cli_args(config, args)

    agent = _create_agent(config)

    if config.get("prompt"):
        use_stream = _resolve_stream_flag(args)
        _run_one_shot(agent, config["prompt"], use_stream)
    else:
        run_curses_app(agent)


if __name__ == "__main__":
    main()
