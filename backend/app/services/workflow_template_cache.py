"""Redis cache for workflow template names and filenames."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.app.db.workflow_template import list_workflow_templates
from backend.app.services.redis_client import get_redis

logger = logging.getLogger(__name__)

NAMES_KEY = "workflow:template:names"
FILENAMES_KEY = "workflow:template:filenames"


async def refresh_workflow_template_cache(database_path: str | Path) -> None:
    """Rebuild Redis sets from the ``workflow_template`` table."""
    try:
        redis = get_redis()
    except RuntimeError:
        logger.warning("workflow template cache refresh skipped: redis unavailable")
        return
    records = list_workflow_templates(database_path)
    pipe = redis.pipeline()
    pipe.delete(NAMES_KEY, FILENAMES_KEY)
    names = [row.template_name for row in records if row.template_name]
    filenames = [row.template_filename for row in records if row.template_filename]
    if names:
        pipe.sadd(NAMES_KEY, *names)
    if filenames:
        pipe.sadd(FILENAMES_KEY, *filenames)
    await pipe.execute()


async def cached_template_name_exists(
    database_path: str | Path, template_name: str
) -> bool:
    key = (template_name or "").strip()
    if not key:
        return False
    try:
        redis = get_redis()
        if await redis.exists(NAMES_KEY):
            return bool(await redis.sismember(NAMES_KEY, key))
    except Exception:
        logger.exception("workflow template name cache lookup failed")
    from backend.app.db.workflow_template import get_workflow_template_by_name

    return get_workflow_template_by_name(database_path, key) is not None


async def cached_template_filename_exists(
    database_path: str | Path, template_filename: str
) -> bool:
    key = (template_filename or "").strip()
    if not key:
        return False
    try:
        redis = get_redis()
        if await redis.exists(FILENAMES_KEY):
            return bool(await redis.sismember(FILENAMES_KEY, key))
    except Exception:
        logger.exception("workflow template filename cache lookup failed")
    from backend.app.db.workflow_template import get_workflow_template_by_filename

    return get_workflow_template_by_filename(database_path, key) is not None


async def add_template_to_cache(*, template_name: str, template_filename: str) -> None:
    try:
        redis = get_redis()
        pipe = redis.pipeline()
        if template_name:
            pipe.sadd(NAMES_KEY, template_name)
        if template_filename:
            pipe.sadd(FILENAMES_KEY, template_filename)
        await pipe.execute()
    except Exception:
        logger.exception("workflow template cache add failed")


async def replace_template_in_cache(
    *,
    old_template_name: str,
    old_template_filename: str,
    template_name: str,
    template_filename: str,
) -> None:
    try:
        redis = get_redis()
        pipe = redis.pipeline()
        if old_template_name and old_template_name != template_name:
            pipe.srem(NAMES_KEY, old_template_name)
        if old_template_filename and old_template_filename != template_filename:
            pipe.srem(FILENAMES_KEY, old_template_filename)
        if template_name:
            pipe.sadd(NAMES_KEY, template_name)
        if template_filename:
            pipe.sadd(FILENAMES_KEY, template_filename)
        await pipe.execute()
    except Exception:
        logger.exception("workflow template cache replace failed")
