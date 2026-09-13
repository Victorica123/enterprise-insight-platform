"""DB-API compatibility for the SQLite development path and MySQL pilot path."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_LONG_TEXT_COLUMNS = {
    "answer", "rewritten_question", "embedding", "embedding_v2",
    "answer_preview", "asset_ids_json", "confirmations_json", "content", "description",
    "details_json", "document_ids", "error_message", "evidence",
    "evidence_json", "evidence_snapshot_json", "input_json", "last_error",
    "feedback_note", "filename", "invalidation_reason", "lifecycle_reason", "metadata_json", "objective",
    "open_questions_json", "payload",
    "prd_json", "publication_json", "question", "reason", "replacement_evidence_json", "replacement_statement", "result", "result_json",
    "source_document_ids", "sources_json", "stages_json", "statement", "summary", "trace_json",
    "transcript", "transcript_segments_json", "chunk_title",
}


class CompatRow(Mapping[str, Any]):
    """Mapping row that also supports sqlite3.Row-style integer indexing."""

    def __init__(self, names: Sequence[str], values: Sequence[Any]) -> None:
        self._values = tuple(values)
        self._mapping = dict(zip(names, self._values, strict=False))

    def __getitem__(self, key: str | int) -> Any:
        return self._values[key] if isinstance(key, int) else self._mapping[key]

    def __iter__(self):
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def keys(self):
        return self._mapping.keys()


class MySqlCursorCompat:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid

    def fetchone(self) -> CompatRow | None:
        return self._wrap(self._cursor.fetchone())

    def fetchall(self) -> list[CompatRow]:
        return [CompatRow(self._column_names(), value) for value in self._cursor.fetchall()]

    def __iter__(self):
        names = self._column_names()
        return (CompatRow(names, value) for value in self._cursor)

    def _wrap(self, value: Sequence[Any] | None) -> CompatRow | None:
        if value is None:
            return None
        return CompatRow(self._column_names(), value)

    def _column_names(self) -> list[str]:
        return [str(column[0]) for column in self._cursor.description or ()]


class MySqlConnectionCompat:
    """Subset of sqlite3.Connection used by the application stores."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> MySqlCursorCompat:
        translated, translated_parameters, begin = translate_mysql_sql(sql, tuple(parameters))
        cursor = self._connection.cursor()
        if begin:
            self._connection.begin()
            return MySqlCursorCompat(cursor)
        try:
            cursor.execute(translated, translated_parameters)
        except Exception as exc:
            if _mysql_error_code(exc) == 1061 and _is_create_index(translated):
                return MySqlCursorCompat(cursor)
            raise _as_sqlite_exception(exc) from exc
        return MySqlCursorCompat(cursor)

    def executemany(
        self, sql: str, parameter_rows: Iterable[Iterable[Any]]
    ) -> MySqlCursorCompat:
        rows = [tuple(row) for row in parameter_rows]
        translated, _, begin = translate_mysql_sql(sql, rows[0] if rows else ())
        if begin:
            raise sqlite3.OperationalError("executemany cannot start a transaction")
        normalized = [_normalize_parameters(sql, row) for row in rows]
        cursor = self._connection.cursor()
        try:
            cursor.executemany(translated, normalized)
        except Exception as exc:
            raise _as_sqlite_exception(exc) from exc
        return MySqlCursorCompat(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def connect_mysql(database_url: str) -> MySqlConnectionCompat:
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - container dependency guard
        raise RuntimeError(
            "AGENT_DATABASE_URL uses MySQL but PyMySQL is not installed."
        ) from exc

    parsed = urlparse(database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise RuntimeError("AGENT_DATABASE_URL must use mysql:// or mysql+pymysql://")
    options = parse_qs(parsed.query)
    raw = pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
        charset=options.get("charset", ["utf8mb4"])[0],
        autocommit=False,
        connect_timeout=5,
        read_timeout=30,
        write_timeout=30,
    )
    return MySqlConnectionCompat(raw)


def translate_mysql_sql(
    sql: str, parameters: tuple[Any, ...] = ()
) -> tuple[str, tuple[Any, ...], bool]:
    """Translate only the known SQLite syntax used by repository stores."""
    normalized = sql.strip()
    lowered = normalized.lower()
    if lowered in {"begin", "begin immediate", "start transaction"}:
        return "", (), True

    pragma = re.fullmatch(r"pragma\s+table_info\((\w+)\)", lowered)
    if pragma:
        return (
            "select column_name as name from information_schema.columns "
            "where table_schema = database() and table_name = %s order by ordinal_position",
            (pragma.group(1),),
            False,
        )

    if "sqlite_master" in lowered:
        match = re.search(r"name\s*=\s*'([^']+)'", normalized, re.IGNORECASE)
        table = match.group(1) if match else ""
        return (
            "select table_name as name from information_schema.tables "
            "where table_schema = database() and table_name = %s",
            (table,),
            False,
        )

    if lowered.startswith("create table"):
        normalized = _translate_create_table(normalized)
    elif _is_create_index(normalized):
        normalized = re.sub(
            r"create\s+(unique\s+)?index\s+if\s+not\s+exists",
            lambda match: f"create {match.group(1) or ''}index",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"\s+where\s+external_id\s*!=\s*''\s*$", "", normalized,
            flags=re.IGNORECASE,
        )
    elif lowered.startswith("alter table"):
        normalized = _translate_alter_table(normalized)

    normalized = re.sub(r"\binsert\s+or\s+ignore\b", "insert ignore", normalized, flags=re.IGNORECASE)
    normalized = re.sub(
        r"\bon\s+conflict\s*\([^)]*\)\s+do\s+update\s+set\b",
        "on duplicate key update", normalized, flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"\bexcluded\.([A-Za-z_][A-Za-z0-9_]*)\b",
        r"values(\1)", normalized, flags=re.IGNORECASE,
    )
    normalized = _quote_reserved_key(normalized).replace("?", "%s")
    return normalized, _normalize_parameters(sql, parameters), False


def _translate_create_table(sql: str) -> str:
    translated_lines: list[str] = []
    for line in sql.splitlines():
        match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s+)(.*)$", line)
        if not match:
            translated_lines.append(line)
            continue
        indent, column, spacing, definition = match.groups()
        if column.lower() in {"create", "foreign", "unique", "primary", "constraint"}:
            translated_lines.append(line)
            continue
        definition = re.sub(
            r"integer\s+primary\s+key\s+autoincrement",
            "bigint primary key auto_increment", definition, flags=re.IGNORECASE,
        )
        definition = re.sub(r"\breal\b", "double", definition, flags=re.IGNORECASE)
        if re.search(r"\btext\b", definition, re.IGNORECASE):
            mysql_type = "longtext" if column.lower() in _LONG_TEXT_COLUMNS else "varchar(191)"
            definition = re.sub(r"\btext\b", mysql_type, definition, count=1, flags=re.IGNORECASE)
            if mysql_type == "longtext":
                definition = re.sub(
                    r"\bdefault\s+('(?:''|[^'])*')", r"default (\1)", definition,
                    flags=re.IGNORECASE,
                )
        if column.lower() == "external_id":
            definition = re.sub(
                r"\s+not\s+null\s+default\s+''", " null", definition,
                flags=re.IGNORECASE,
            )
        definition = re.sub(
            r"default\s+current_timestamp",
            "default (concat(replace(utc_timestamp(), ' ', 'T'), '+00:00'))",
            definition,
            flags=re.IGNORECASE,
        )
        name = "`key`" if column.lower() == "key" else column
        translated_lines.append(f"{indent}{name}{spacing}{definition}")
    return "\n".join(translated_lines)


def _translate_alter_table(sql: str) -> str:
    match = re.search(
        r"add\s+column\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+)$", sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return sql
    column, definition = match.groups()
    mysql_type = "longtext" if column.lower() in _LONG_TEXT_COLUMNS else "varchar(191)"
    definition = re.sub(r"\btext\b", mysql_type, definition, count=1, flags=re.IGNORECASE)
    if mysql_type == "longtext":
        definition = re.sub(
            r"\bdefault\s+('(?:''|[^'])*')", r"default (\1)", definition,
            flags=re.IGNORECASE,
        )
    if column.lower() == "external_id":
        definition = re.sub(
            r"\s+not\s+null\s+default\s+''", " null", definition,
            flags=re.IGNORECASE,
        )
    definition = re.sub(r"\breal\b", "double", definition, flags=re.IGNORECASE)
    definition = re.sub(
        r"default\s+current_timestamp",
        "default (concat(replace(utc_timestamp(), ' ', 'T'), '+00:00'))",
        definition,
        flags=re.IGNORECASE,
    )
    return sql[: match.start(2)] + definition


def _normalize_parameters(sql: str, parameters: tuple[Any, ...]) -> tuple[Any, ...]:
    if not parameters or not re.search(r"insert\s+into\s+documents", sql, re.IGNORECASE):
        return parameters
    columns_match = re.search(
        r"insert\s+into\s+documents\s*\(([^)]+)\)", sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not columns_match:
        return parameters
    columns = [column.strip().lower() for column in columns_match.group(1).split(",")]
    values = list(parameters)
    if "external_id" in columns:
        index = columns.index("external_id")
        if index < len(values) and values[index] == "":
            values[index] = None
    return tuple(values)


def _quote_reserved_key(sql: str) -> str:
    sql = re.sub(r"\bas\s+key\b", "as `key`", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bkey\s*=", "`key` =", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\((\s*)key(\s*[,\)])", r"(\1`key`\2", sql, flags=re.IGNORECASE)
    sql = re.sub(r",(\s*)key(\s*[,\)])", r",\1`key`\2", sql, flags=re.IGNORECASE)
    return re.sub(r"\bselect\s+key\b", "select `key`", sql, flags=re.IGNORECASE)


def _mysql_error_code(exc: Exception) -> int | None:
    args = getattr(exc, "args", ())
    return int(args[0]) if args and isinstance(args[0], int) else None


def _is_create_index(sql: str) -> bool:
    return bool(re.match(r"\s*create\s+(?:unique\s+)?index\b", sql, re.IGNORECASE))


def _as_sqlite_exception(exc: Exception) -> sqlite3.Error:
    return (
        sqlite3.IntegrityError(str(exc))
        if _mysql_error_code(exc) in {1062, 1451, 1452}
        else sqlite3.OperationalError(str(exc))
    )
