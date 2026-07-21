"""Shared utilities for Excel export generators.

Security
--------
``sanitize_cell`` prevents CSV/spreadsheet formula injection by prefixing any
string value that begins with a formula-trigger character (=, +, -, @) with a
single-quote character.  Excel and LibreOffice Calc treat a leading single-quote
as a literal-string prefix and display the value without executing it as a formula.

Non-string values (int, float, bool, None) are returned unchanged — they are
never interpreted as formulas by openpyxl.
"""
from __future__ import annotations

# Characters that trigger formula execution in Excel / LibreOffice Calc when
# they appear at the start of a cell value.
_FORMULA_TRIGGERS: frozenset[str] = frozenset({"=", "+", "-", "@"})


def sanitize_cell(value: object) -> object:
    """Return *value* safe for writing into an Excel cell.

    If *value* is a string whose first character is a formula trigger (``=``,
    ``+``, ``-``, ``@``), a single-quote is prepended so the spreadsheet
    application treats it as a literal string rather than a formula.

    All non-string values (numbers, booleans, None, dates) are returned as-is
    because openpyxl never interprets them as formulas.

    Examples::

        sanitize_cell("=1+1")          # -> "'=1+1"
        sanitize_cell("+SUM(A1:A9)")   # -> "'+SUM(A1:A9)"
        sanitize_cell("web-server-01") # -> "web-server-01"  (unchanged)
        sanitize_cell(1024)            # -> 1024             (unchanged)
        sanitize_cell(None)            # -> None             (unchanged)
    """
    if isinstance(value, str) and value and value[0] in _FORMULA_TRIGGERS:
        return f"'{value}"
    return value
