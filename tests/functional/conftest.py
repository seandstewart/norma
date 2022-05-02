from __future__ import annotations

import dataclasses
import datetime
import os
from typing import Iterable

import asyncpg
import psycopg
import psycopg_pool as pgpool
import pytest
import typic

from yesql import uow
from yesql.core.drivers.postgresql import _asyncpg, _psycopg


@pytest.fixture(scope="session")
def foo_serde() -> uow.SerDes[Foo]:
    return uow.SerDes(
        serializer=lambda f: {"bar": f.bar},
        deserializer=typic.protocol(Foo, is_optional=True).transmute,
        bulk_deserializer=typic.protocol(Iterable[Foo]).transmute,
    )


@pytest.fixture(params=["asyncpg_executor", "async_psycopg_executor"])
def async_executor(request, asyncpg_executor, async_psycopg_executor):
    name_to_executor = {
        "asyncpg_executor": asyncpg_executor,
        "async_psycopg_executor": async_psycopg_executor,
    }
    executor = name_to_executor[request.param]
    return executor


@pytest.fixture(params=["sync_psycopg_executor"])
def sync_executor(request, sync_psycopg_executor):
    name_to_executor = {
        "sync_psycopg_executor": sync_psycopg_executor,
    }
    executor = name_to_executor[request.param]
    return executor


@pytest.fixture(scope="package", autouse=True)
async def database():
    """Create the root test database, if it doesn't exist."""
    c: asyncpg.Connection = await asyncpg.connect(dsn=PG_INIT_DSN)
    try:
        await c.execute("CREATE DATABASE test;")
    except asyncpg.DuplicateDatabaseError:
        pass
    finally:
        await c.close(timeout=1)
        os.environ["postgres_pool_dsn"] = PG_TEST_DSN


@pytest.fixture(scope="package")
async def asyncpg_executor(database):
    async with _asyncpg.AsyncPGQueryExecutor(
        min_size=1,
        max_size=1,
    ) as executor:
        await executor.pool.execute(PG_TEST_SCHEMA)
        yield executor


@pytest.fixture(scope="package")
async def async_psycopg_executor(database):
    try:
        async with _psycopg.AsyncPsycoPGQueryExecutor(
            min_size=1,
            max_size=1,
        ) as executor:
            pool: pgpool.AsyncConnectionPool = executor.pool
            c: psycopg.AsyncConnection
            async with pool.connection() as c:
                await c.execute(PG_TEST_SCHEMA)
            yield executor
    except pgpool.PoolTimeout:
        async with _psycopg.AsyncPsycoPGQueryExecutor(
            min_size=1,
            max_size=1,
        ) as executor:
            pool: pgpool.AsyncConnectionPool = executor.pool
            c: psycopg.AsyncConnection
            async with pool.connection() as c:
                await c.execute(PG_TEST_SCHEMA)
            yield executor


@pytest.fixture(scope="package")
def sync_psycopg_executor(database):
    with _psycopg.PsycoPGQueryExecutor(
        min_size=1,
        max_size=1,
    ) as executor:
        pool: pgpool.ConnectionPool = executor.pool
        c: psycopg.Connection
        with pool.connection(timeout=10) as c:
            c.execute(PG_TEST_SCHEMA)
        yield executor


PG_INIT_DSN = "postgres://postgres:@localhost:5432/?sslmode=disable"
PG_TEST_DSN = "postgres://postgres:@localhost:5432/test?sslmode=disable"
PG_TEST_SCHEMA = """
CREATE TEMPORARY TABLE foo
(
    id         BIGINT GENERATED BY DEFAULT AS IDENTITY,
    bar        TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclasses.dataclass
class Foo:
    bar: str
    id: int = None
    created_at: datetime.datetime = None
