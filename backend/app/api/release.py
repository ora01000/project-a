from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.config import PROJECT_ROOT

router = APIRouter(tags=["release"])

RELEASE_NOTES_PATH = PROJECT_ROOT / "RELEASE.md"


class ReleaseNotesResponse(BaseModel):
    content: str
    path: str = "RELEASE.md"


@router.get("/release-notes", response_model=ReleaseNotesResponse)
async def get_release_notes() -> ReleaseNotesResponse:
    path = RELEASE_NOTES_PATH
    if not path.is_file():
        raise HTTPException(status_code=404, detail="RELEASE.md 파일을 찾을 수 없습니다.")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"RELEASE.md를 읽지 못했습니다: {exc}") from exc
    return ReleaseNotesResponse(content=content, path=str(Path(path.name)))
