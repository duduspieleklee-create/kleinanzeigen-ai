import sentry_sdk

from app.api.config import settings
from app.shared.logging_config import logger


def init_sentry(component: str) -> None:
    """Initialise Sentry error tracking. No-op if SENTRY_DSN is unset, or in
    dev unless SENTRY_ENABLE_IN_DEV is also set (avoids noisy local events).
    """
    if not settings.sentry_dsn:
        return
    if settings.environment == "dev" and not settings.sentry_enable_in_dev:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=settings.git_sha,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    sentry_sdk.set_tag("component", component)
    logger.info(f"Sentry error tracking enabled for component={component}")
