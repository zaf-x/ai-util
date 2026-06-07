"""
CLI Markdown — render markdown to curses-styled lines using rich.

Exports:
    render_markdown, render_plain, init_color_pairs
"""

from typing import Any, Dict, List, Optional, Tuple
from rich.console import Console
from rich.markdown import Markdown
from rich.segment import Segment
from rich.style import Style
from io import StringIO
import curses


__all__ = [
    "render_markdown",
    "render_plain",
    "init_color_pairs",
]

# Map rich color names (8-color palette) to curses color indices
RICH_TO_CURSES_COLORS: Dict[str, int] = {
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "blue": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
    "black": curses.COLOR_BLACK,
}

# Cache for color pairs: (fg, bg) -> pair_number
_color_pair_cache: Dict[Tuple[int, int], int] = {}
_next_pair = 1


def _get_color_pair(fg: int, bg: int = -1) -> int:
    """Get (or create) a curses color pair number for given foreground/background."""
    global _next_pair
    bg = bg if bg >= 0 else curses.COLOR_BLACK
    key = (fg, bg)
    if key not in _color_pair_cache:
        if _next_pair > 255:
            _next_pair = 1  # wrap around, reuse pairs
        curses.init_pair(_next_pair, fg, bg)
        _color_pair_cache[key] = _next_pair
        _next_pair += 1
    return curses.color_pair(_color_pair_cache[key])


def init_color_pairs() -> None:
    """Pre-initialise commonly used colour pairs for markdown rendering.

    Call this once after curses.initscr() / curses.start_color().
    """
    global _color_pair_cache, _next_pair
    _color_pair_cache.clear()
    _next_pair = 1
    # Pre-create pairs for the ANSI palette on default background
    for color_num in range(8):
        _get_color_pair(color_num)


def _rich_color_to_curses(color_name: Optional[str]) -> int:
    """Convert a rich colour name to a curses colour number."""
    if color_name is None:
        return curses.COLOR_WHITE  # default foreground
    return RICH_TO_CURSES_COLORS.get(color_name, curses.COLOR_WHITE)


def _style_to_curses_attr(style: Style) -> int:
    """Convert a rich Style to a single curses attribute + colour bitmask."""
    attr = 0

    fg_color = _rich_color_to_curses(style.color.name if style.color else None)
    bg_color = curses.COLOR_BLACK
    if style.bgcolor is not None:
        bg_color = _rich_color_to_curses(style.bgcolor.name)

    attr |= _get_color_pair(fg_color, bg_color)

    if style.bold:
        attr |= curses.A_BOLD
    if style.italic:
        attr |= curses.A_ITALIC
    if style.underline:
        attr |= curses.A_UNDERLINE
    if style.strike:
        attr |= curses.A_STANDOUT

    return attr


def render_markdown(text: str, width: int) -> List[List[Tuple[str, int]]]:
    """
    Render markdown to a list of lines.

    Each line is a list of (text_segment, curses_attribute) tuples
    that should be concatenated for display.

    Args:
        text: Raw markdown string.
        width: Target line width for wrapping.

    Returns:
        Lines ready for curses.addstr() usage.
    """
    md = Markdown(text, code_theme="monokai")
    console = Console(
        width=width,
        force_terminal=True,
        color_system="standard",
        legacy_windows=False,
    )

    rendered_segments = console.render(md)
    segments = list(Segment.split_lines(rendered_segments))

    lines: List[List[Tuple[str, int]]] = []
    for seg_line in segments:
        line: List[Tuple[str, int]] = []
        for segment in seg_line:
            if segment.text is None:
                continue
            attr = _style_to_curses_attr(segment.style or Style())
            line.append((segment.text, attr))
        lines.append(line)

    return lines


def render_plain(text: str, width: int) -> str:
    """Render markdown to plain text (no styling), for use in one-shot mode."""
    md = Markdown(text, code_theme="monokai")
    console = Console(width=width, force_terminal=False, color_system=None)
    with console.capture() as capture:
        console.print(md)
    return capture.get()
