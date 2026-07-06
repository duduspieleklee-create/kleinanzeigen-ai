"""Build/version metadata surfaced in the UI footer and the /version endpoint.

Values come from settings, which read them from environment variables baked
into the Docker image at build time (see app/api/Dockerfile and the CI build
job). Import BUILD_INFO wherever the version needs to be displayed, and call
register_globals() on any Jinja2Templates instance whose templates render
the {{ build_info }} footer, or reference build_info.commit_short for
cache-busting static asset URLs (e.g. /static/style.css?v=...).
"""
from app.api.config import settings

BUILD_INFO = {
    "version": settings.app_version,
    "commit": settings.git_sha,
    "commit_short": (settings.git_sha or "local")[:7],
    "build": settings.build_number,
    "built_at": settings.build_time,
    "environment": settings.environment,
}


def register_globals(templates) -> None:
    """Expose BUILD_INFO to a Jinja2Templates environment as `build_info`."""
    templates.env.globals["build_info"] = BUILD_INFO
