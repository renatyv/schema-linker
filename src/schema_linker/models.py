from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from schema_linker.query_timeout import DEFAULT_QUERY_TIMEOUT


@dataclass(frozen=True)
class SchemaLinkOptions:
    include_tables: frozenset[str] | None = None
    exclude_tables: frozenset[str] = frozenset()
    low_cardinality_ratio: float = 0.05
    unique_drop_ratio: float = 0.98
    containment_threshold: float = 0.8
    max_distinct_values: int = 10_000
    minhash_permutations: int = 128
    query_timeout: int = DEFAULT_QUERY_TIMEOUT
    schema: str | None = None
    include_technical_tables: bool = False


@dataclass(frozen=True)
class ColumnRef:
    table: str
    column: str
    type_group: str
    is_primary_or_unique: bool
    is_id_like: bool
    total_rows: int
    non_nulls: int
    distinct_count: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.table, self.column)

    @property
    def label(self) -> str:
        return f"{self.table}.{self.column}"

    @property
    def cardinality_ratio(self) -> float:
        if self.non_nulls == 0:
            return 0.0
        return self.distinct_count / self.non_nulls


@dataclass(frozen=True)
class DeclaredLink:
    from_table: str
    from_columns: tuple[str, ...]
    to_table: str
    to_columns: tuple[str, ...]


@dataclass(frozen=True)
class CandidatePair:
    left: ColumnRef
    right: ColumnRef
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class InferredLink:
    source: ColumnRef
    target: ColumnRef
    containment: float
    evidence: tuple[str, ...]
    notes: tuple[str, ...]


SchemaLinkProgress = Callable[[int, int, str], None]
