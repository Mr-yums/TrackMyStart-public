"""[Sol] Migration additive coupons, depuis le schéma 1080ebac346f.

Exécution explicite uniquement : DATABASE_URL=... python ops/migrations/coupons.py
Arrêter les écritures et sauvegarder la base avant application. Ne modifie pas
le marqueur de déploiement ; aucune suppression de données au retour applicatif.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import create_engine, inspect
from yumnews.domain.models import Base


def upgrade(connection):
    dialect = connection.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise RuntimeError("Migration prévue pour PostgreSQL ou SQLite.")
    if "payments" not in inspect(connection).get_table_names():
        raise RuntimeError(
            "Schéma initial absent : utiliser init-db pour une base neuve."
        )
    if dialect == "postgresql":
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(880020260910)")
        connection.exec_driver_sql("LOCK TABLE payments IN ACCESS EXCLUSIVE MODE")
    for name in ("affiliates", "coupons"):
        Base.metadata.tables[name].create(connection, checkfirst=True)
    columns = {col["name"] for col in inspect(connection).get_columns("payments")}
    if "coupon_id" not in columns:
        connection.exec_driver_sql(
            "ALTER TABLE payments ADD COLUMN coupon_id INTEGER REFERENCES coupons(id) ON DELETE SET NULL"
        )
    if "discount_cents" not in columns:
        connection.exec_driver_sql(
            "ALTER TABLE payments ADD COLUMN discount_cents INTEGER NOT NULL DEFAULT 0"
        )
    for index in Base.metadata.tables["payments"].indexes:
        if any(col.name == "coupon_id" for col in index.columns):
            index.create(connection, checkfirst=True)
    for name in ("redemptions", "discord_passphrases"):
        Base.metadata.tables[name].create(connection, checkfirst=True)


if __name__ == "__main__":
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        # SQLite legacy transaction mode ne démarre pas de transaction sur DDL.
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        upgrade(connection)
    print("[Sol] Migration coupons appliquée ; marqueur de déploiement inchangé.")
