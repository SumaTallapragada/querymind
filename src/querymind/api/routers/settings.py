"""`GET /settings` -- read-only application configuration, for the Phase 18 frontend's Settings
page. The one route in this package backed by `Settings` directly rather than an engine --
there is no pipeline behavior to reuse here, only values already sitting on the one `Settings`
instance the whole process was built from. Never returns a secret: no password, API key, or
connection string, only a database *name* and an LLM *provider*/*model* pair.

Requires `ADMIN` (Phase 22B) -- deployment/environment configuration, even the non-secret parts
of it, is an operator concern. The Phase 18 frontend has no login UI yet, so this is a known,
intentional consequence for its Settings page until one exists (documented in the Phase 22B
deliverable report, alongside the same tradeoff for the query/streaming endpoints).
"""

from __future__ import annotations

from importlib.metadata import version as package_version

from fastapi import APIRouter, status

from querymind.api.dependencies import RequireAdmin, SettingsDep
from querymind.api.models.response import SettingsResponse

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "",
    response_model=SettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="Read-only application configuration",
    description=(
        "Application name, version, environment, database engine/name, LLM provider/model, and "
        "which streaming transports this backend serves. Never includes a password, API key, or "
        "connection string. Requires the `admin` role."
    ),
)
async def get_settings_info(settings: SettingsDep, _admin: RequireAdmin) -> SettingsResponse:
    llm_provider_config = settings.llm_provider_config
    return SettingsResponse(
        app_name=settings.app_name,
        version=package_version("querymind"),
        environment=settings.app_env,
        api_v1_prefix=settings.api_v1_prefix,
        database_engine="PostgreSQL",
        database_name=settings.postgres_db,
        llm_provider=llm_provider_config.provider.value,
        llm_model=llm_provider_config.model,
        streaming_transports=("sse", "websocket"),
    )
