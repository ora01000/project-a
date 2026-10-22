"""Chat prompt suggestions (prompt_offer) for the interactive terminal."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.app.db.database import get_connection

DEFAULT_PROMPTS: tuple[str, ...] = (
    "사용할 수 있는 도구와 스킬을 소개해 줘",
    "관리 가능한 OKD클러스터와 데이터센터를 출력해줘",
    "현재 진행 중인 작업 목록을 보여줘",
    "vSphere 클러스터 용량 현황을 요약해줘",
    "인벤토리에서 호스트명이나 IP로 서버를 찾아줘",
)


@dataclass(frozen=True)
class PromptOffer:
    idx: int
    prompt: str


def ensure_prompt_offer_table(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_offer (
            idx SERIAL PRIMARY KEY,
            prompt VARCHAR(300) NOT NULL
        )
        """
    )


def seed_prompt_offers_if_empty(connection) -> None:
    ensure_prompt_offer_table(connection)
    row = connection.execute("SELECT COUNT(*) AS cnt FROM prompt_offer").fetchone()
    count = int(row["cnt"] if row is not None else 0)
    if count > 0:
        return
    for prompt in DEFAULT_PROMPTS:
        connection.execute(
            "INSERT INTO prompt_offer (prompt) VALUES (?)",
            (prompt,),
        )


def list_prompt_offers(database_path: str | Path) -> list[PromptOffer]:
    with get_connection(database_path) as connection:
        # Safe for processes started before schema was added; seed only if empty.
        ensure_prompt_offer_table(connection)
        seed_prompt_offers_if_empty(connection)
        rows = connection.execute(
            "SELECT idx, prompt FROM prompt_offer ORDER BY idx ASC"
        ).fetchall()
    return [
        PromptOffer(idx=int(row["idx"]), prompt=str(row["prompt"] or "").strip())
        for row in rows
        if str(row["prompt"] or "").strip()
    ]
