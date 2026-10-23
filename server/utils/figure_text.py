"""Request-local figure protection for Python pdf2zh_next runtimes.

BabelDOC has no figure-text switch. Its paragraph finder retains characters
assigned to non-text layouts verbatim. Adapt that boundary in the child process
only: never modify installed packages or the concurrent Flask server's globals.
"""
from pathlib import Path


FIGURE_LABELS = frozenset({"figure", "image", "figure_text", "figure_text_hybrid"})
CAPTION_LABELS = frozenset({"figure_caption", "figure_title", "chart_title"})


def protected_layout(char, layout_index, layout_map, original):
    """Keep captions separate; protect characters mostly inside detected figures."""
    layout = original(char, layout_index, layout_map)
    if layout is not None and layout.name in CAPTION_LABELS:
        return layout
    box = char.visual_bbox.box
    area = (box.x2 - box.x) * (box.y2 - box.y)
    if area <= 0:
        return layout
    for identifier in layout_index.intersection((box.x, box.y, box.x2, box.y2)):
        candidate = layout_map[identifier]
        if candidate.class_name not in FIGURE_LABELS:
            continue
        bounds = candidate.box
        overlap = max(0, min(box.x2, bounds.x2) - max(box.x, bounds.x)) * max(
            0, min(box.y2, bounds.y2) - max(box.y, bounds.y)
        )
        if overlap / area >= 0.5:
            from babeldoc.format.pdf.document_il.utils.layout_helper import Layout
            return Layout(candidate.id, "figure")
    return layout


def install_figure_protection():
    from babeldoc.format.pdf.document_il.midend import paragraph_finder

    original = paragraph_finder.get_character_layout

    def get_layout(char, layout_index, layout_map):
        return protected_layout(char, layout_index, layout_map, original)

    paragraph_finder.get_character_layout = get_layout


def figure_text_command(command):
    """Use the resolved engine's interpreter, preserving all CLI arguments."""
    from utils.deepseek_thinking import _invocation_prefix, _python_for_invocation_prefix

    prefix = _invocation_prefix(command)
    if "-m" in prefix:
        python = Path(prefix[0])
    else:
        python = _python_for_invocation_prefix(prefix)
        # Windows console entry points live in Scripts, python.exe one level up.
        if python is None:
            candidate = Path(prefix[0]).parent.parent / "python.exe"
            if candidate.is_file():
                python = candidate
    if python is None or not python.is_file():
        raise ValueError("Cannot resolve pdf2zh_next Python for skip-figure-text; use a managed Python environment.")
    return [str(python), "-u", str(Path(__file__).resolve()), *command[len(prefix):]]


if __name__ == "__main__":
    install_figure_protection()
    from pdf2zh_next.main import cli
    cli()
