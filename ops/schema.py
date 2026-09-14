"""[Sol] Empreinte du schéma : tout changement exige une migration explicite."""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from yumnews.domain.models import Base

parts = []
for table in Base.metadata.sorted_tables:
    parts.append(str(CreateTable(table).compile(dialect=postgresql.dialect())))
    parts.extend(
        sorted(
            str(CreateIndex(index).compile(dialect=postgresql.dialect()))
            for index in table.indexes
        )
    )
print(hashlib.sha256("\n".join(parts).encode()).hexdigest())
