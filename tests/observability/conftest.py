"""Shared fixtures and builders for Observability tests.

`metadata_registry`/`business_knowledge_registry`/`query_library` mirror
`tests/orchestrator/conftest.py` exactly (real, shipped project data,
session-scoped). `engine`/`connection_provider` mirror
`tests/sql_execution/conftest.py`'s `engine` fixture exactly, including
being function-scoped rather than session-scoped -- see that fixture's
own docstring for why a session-scoped `AsyncEngine` breaks across this
project's per-test event loops. Only `test_integration.py` uses any of
this; every other test file in this directory builds fully synthetic
`DiagnosticsEngine`/`HealthCheckEngine` collaborators or none at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

import querymind.models  # noqa: F401 -- populates Base.registry
from querymind.business_knowledge import BusinessKnowledgeRegistry
from querymind.core.config import Settings
from querymind.db.engine import create_engine
from querymind.metadata import ColumnDictionary, MetadataExtractor, MetadataRegistry
from querymind.models.base import Base
from querymind.query_library import QueryLibraryRegistry
from querymind.sql_execution import DatabaseConnectionProvider


@pytest.fixture(scope="session")
def metadata_registry() -> MetadataRegistry:
    registry = MetadataRegistry(MetadataExtractor(Base.registry), ColumnDictionary.default())
    registry.load()
    return registry


@pytest.fixture(scope="session")
def business_knowledge_registry() -> BusinessKnowledgeRegistry:
    registry = BusinessKnowledgeRegistry()
    registry.load()
    return registry


@pytest.fixture(scope="session")
def query_library() -> QueryLibraryRegistry:
    registry = QueryLibraryRegistry()
    registry.load()
    return registry


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Function-scoped -- see `tests/sql_execution/conftest.py`'s `engine` fixture docstring
    for why a session-scoped `AsyncEngine` breaks across this project's per-test event loops."""
    db_engine = create_engine(settings)
    yield db_engine
    await db_engine.dispose()


@pytest.fixture
def connection_provider(engine: AsyncEngine) -> DatabaseConnectionProvider:
    return DatabaseConnectionProvider(engine)
