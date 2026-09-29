from __future__ import annotations

import urllib.parse

from backend.app.db.mynotes import MyNoteRecord, _sanitize_user_id
from backend.app.services.redis_client import get_redis

MY_NOTE_CONTENT_PREFIX = "mynote:content:"


def build_mynote_content_key(userid: str, note_name: str) -> str:
    safe_userid = _sanitize_user_id(userid)
    encoded_name = urllib.parse.quote(note_name.strip(), safe="")
    return f"{MY_NOTE_CONTENT_PREFIX}{safe_userid}:{encoded_name}"


async def get_mynote_content_from_redis(userid: str, note_name: str) -> str | None:
    redis = get_redis()
    return await redis.get(build_mynote_content_key(userid, note_name))


async def set_mynote_content_in_redis(userid: str, note_name: str, content: str) -> None:
    redis = get_redis()
    await redis.set(build_mynote_content_key(userid, note_name), content)


async def delete_mynote_content_from_redis(userid: str, note_name: str) -> None:
    redis = get_redis()
    await redis.delete(build_mynote_content_key(userid, note_name))


async def rename_mynote_content_in_redis(
    userid: str,
    *,
    old_note_name: str,
    new_note_name: str,
) -> None:
    if old_note_name.strip() == new_note_name.strip():
        return

    redis = get_redis()
    old_key = build_mynote_content_key(userid, old_note_name)
    new_key = build_mynote_content_key(userid, new_note_name)
    content = await redis.get(old_key)
    if content is None:
        return
    await redis.set(new_key, content)
    await redis.delete(old_key)


async def hydrate_mynote_content(record: MyNoteRecord, *, file_content: str) -> str:
    cached = await get_mynote_content_from_redis(record.userid, record.note_name)
    if cached is not None:
        return cached
    await set_mynote_content_in_redis(record.userid, record.note_name, file_content)
    return file_content
