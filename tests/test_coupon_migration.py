"""[Sol] Ancien schéma réel, préservation des données et retour applicatif."""

import os
from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session

from ops.migrations.coupons import upgrade
from yumnews.domain.models import Payment


@pytest.fixture(params=["sqlite", "postgresql"])
def legacy_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path}/migration.db")

        @event.listens_for(engine, "connect")
        def foreign_keys(dbapi_connection, _):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        schema = None
    else:
        url = os.environ.get("SOL_TEST_POSTGRES_URL")
        if not url:
            pytest.skip("PostgreSQL isolé : définir SOL_TEST_POSTGRES_URL")
        schema = "sol_test_" + uuid.uuid4().hex
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    with engine.begin() as connection:
        sql = (
            Path(__file__)
            .with_name("fixtures")
            .joinpath(f"legacy_1080ebac_{request.param}.sql")
            .read_text()
        )
        for statement in sql.split(";"):
            if statement.strip():
                connection.exec_driver_sql(statement)
        connection.exec_driver_sql("""INSERT INTO users
            (id,email,password_hash,display_name,email_verified,is_admin,is_active,created_at,updated_at)
            VALUES (1,'legacy@example.com','fixture','Legacy',false,false,true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""")
        insert_old_payment(connection, "before")
    yield engine
    engine.dispose()
    if schema:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def insert_old_payment(connection, order):
    from sqlalchemy import text

    connection.execute(
        text("""INSERT INTO payments
        (user_id,order_id,provider,status,amount_cents,currency,description,created_at,updated_at)
        VALUES (1,:order,'square','succeeded',2000,'EUR','Legacy',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""),
        {"order": order},
    )


def migrate(engine):
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        upgrade(connection)


def test_migrate_existing_payments_twice_and_old_app_can_still_write(legacy_engine):
    migrate(legacy_engine)
    migrate(legacy_engine)
    with legacy_engine.begin() as connection:
        insert_old_payment(connection, "after")
        inspector = inspect(connection)
        assert {"affiliates", "coupons", "redemptions", "discord_passphrases"} <= set(
            inspector.get_table_names()
        )
        assert any(
            fk["constrained_columns"] == ["coupon_id"]
            and fk["referred_table"] == "coupons"
            for fk in inspector.get_foreign_keys("payments")
        )
        if connection.dialect.name == "sqlite":
            assert any(
                row[3] == "coupon_id" and row[6] == "SET NULL"
                for row in connection.exec_driver_sql(
                    "PRAGMA foreign_key_list(payments)"
                )
            )
        else:
            assert any(
                fk["constrained_columns"] == ["coupon_id"]
                and fk["options"].get("ondelete") == "SET NULL"
                for fk in inspector.get_foreign_keys("payments")
            )
        assert any(
            i["column_names"] == ["coupon_id"]
            for i in inspector.get_indexes("payments")
        )
    with Session(legacy_engine) as session:
        payments = session.query(Payment).order_by(Payment.id).all()
        assert [p.order_id for p in payments] == ["before", "after"]
        assert all(
            p.amount_cents == 2000 and p.discount_cents == 0 and p.coupon_id is None
            for p in payments
        )


def test_failed_migration_transaction_leaves_old_schema_intact(legacy_engine):
    with pytest.raises(RuntimeError):
        with legacy_engine.begin() as connection:
            if legacy_engine.dialect.name == "sqlite":
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            upgrade(connection)
            raise RuntimeError("Interruption simulée avant commit")
    inspector = inspect(legacy_engine)
    assert "coupons" not in inspector.get_table_names()
    assert "coupon_id" not in {c["name"] for c in inspector.get_columns("payments")}
