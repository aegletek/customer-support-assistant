from pathlib import Path

from orbit_core.admin import (
    AdminClient,
    AdminClientSettings,
    AdminOnboarding,
    load_usecase_manifest,
)


MANIFEST_PATH = Path(__file__).with_name("usecase-manifest.yaml")


def build_admin_onboarding(
    settings: AdminClientSettings | None = None,
) -> AdminOnboarding:
    """Build optional, fail-open Admin Dashboard onboarding for this service."""

    settings = settings or AdminClientSettings()
    manifest = load_usecase_manifest(
        MANIFEST_PATH,
        environment=settings.environment,
        service_base_url=settings.service_base_url,
    )
    return AdminOnboarding(
        manifest,
        AdminClient(settings),
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
    )
