"""Verify that bare 'except Exception: pass' patterns are eliminated."""
import ast
from pathlib import Path

import pytest

CHECKED_FILES = [
    "src/database/connection.py",
    "src/analysis/cleaner.py",
    "src/analysis/sentiment.py",
    "src/analysis/anomaly.py",
    "src/ai_engine/llm_analyzer.py",
]

PROJECT_ROOT = Path(__file__).parent.parent


def _find_bare_except_pass(filepath: Path) -> list[int]:
    """Find line numbers where 'except Exception: pass' occurs."""
    bare_lines = []
    try:
        source = filepath.read_text()
    except FileNotFoundError:
        return []

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if (
                len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)
                and node.type is not None
                and isinstance(node.type, ast.Name)
                and node.type.id == "Exception"
            ):
                bare_lines.append(node.lineno)
    return bare_lines


@pytest.mark.parametrize("filepath", CHECKED_FILES)
def test_no_bare_except_exception_pass(filepath):
    full_path = PROJECT_ROOT / filepath
    bare_lines = _find_bare_except_pass(full_path)
    assert bare_lines == [], (
        f"{filepath} has bare 'except Exception: pass' at lines: {bare_lines}. "
        "Replace with specific exception types or add logging."
    )
