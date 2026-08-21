# ADR-0026: Ignore Python docstrings in the SQL boundary scanner

- **Status:** accepted
- **Date:** 2026-08-20
- **Scope:** repository governance and application SQL-boundary validation

## Context

The application SQL-boundary test parses Python modules and searches every
string constant for SQL keywords. That rule correctly prevents executable SQL
from moving into `app/bootstrap`, `app/features`, `app/interfaces`, or
`app/orchestration`, but Python docstrings are string constants too. A normal
docstring beginning with the English verb `Select` was therefore reported as
SQL even though the module neither contained a query nor imported `sqlite3`.

Changing that one sentence would make the current test pass but would leave the
same false positive available to every future module, class, synchronous
function, and asynchronous function docstring.

## Decision

The scanner identifies the first string expression owned by a Python module,
class, synchronous function, or asynchronous function as that owner's semantic
docstring and excludes only that AST node from SQL-literal matching. It
continues to scan every other string constant and continues to reject direct
`sqlite3` imports in application layers.

Regression tests must prove both sides of the boundary: SQL-like text in all
four supported docstring scopes is ignored, while the same text in a regular
runtime string remains an offender. The underlying architecture contract is
unchanged: SQL belongs only in the approved persistence layer.

## Consequences

Application documentation can use ordinary language without creating false
SQL-ownership reports. The scanner remains fail-closed for executable string
literals and concrete SQLite dependencies, and it gains no path allowlist or
baseline exception.

Rejected alternatives are rewording individual docstrings, weakening the SQL
keyword pattern for every string, and allowlisting the affected application
file.
