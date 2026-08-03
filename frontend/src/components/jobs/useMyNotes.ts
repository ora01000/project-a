import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { MyNote, MyNoteDetail } from "../../types/myNote";

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export interface UseMyNotesResult {
  notes: MyNote[];
  selectedIdx: number | null;
  content: string;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  saveMessage: string | null;
  hasSelection: boolean;
  isRenameOpen: boolean;
  renameValue: string;
  isDeleteConfirmOpen: boolean;
  setContent: (value: string) => void;
  selectNote: (idx: number) => Promise<void>;
  createNote: () => Promise<void>;
  createNoteFromContent: (content: string, noteName?: string) => Promise<number | null>;
  openDeleteConfirm: () => void;
  closeDeleteConfirm: () => void;
  confirmDelete: () => Promise<void>;
  openRename: () => void;
  closeRename: () => void;
  setRenameValue: (value: string) => void;
  submitRename: () => Promise<void>;
}

export function useMyNotes(currentUser: AuthUser, active: boolean): UseMyNotesResult {
  const [notes, setNotes] = useState<MyNote[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRenameOpen, setIsRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);

  const lastSavedContentRef = useRef("");
  const contentRef = useRef(content);
  contentRef.current = content;

  const loadNotes = useCallback(async () => {
    const params = new URLSearchParams({ userid: currentUser.userid });
    const response = await fetch(`/api/mynotes?${params.toString()}`);
    if (!response.ok) {
      throw new Error(await parseError(response, "노트 목록을 불러오지 못했습니다."));
    }
    return (await response.json()) as MyNote[];
  }, [currentUser.userid]);

  const loadNoteDetail = useCallback(
    async (idx: number) => {
      const params = new URLSearchParams({ userid: currentUser.userid });
      const response = await fetch(`/api/mynotes/${idx}?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "노트를 불러오지 못했습니다."));
      }
      return (await response.json()) as MyNoteDetail;
    },
    [currentUser.userid],
  );

  const refreshNotes = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await loadNotes();
      setNotes(data);
      setSelectedIdx((current) => {
        if (current !== null && data.some((note) => note.idx === current)) {
          return current;
        }
        return data[0]?.idx ?? null;
      });
    } catch (err) {
      setNotes([]);
      setSelectedIdx(null);
      setContent("");
      lastSavedContentRef.current = "";
      setError(err instanceof Error ? err.message : "노트 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [loadNotes]);

  useEffect(() => {
    if (!active) {
      return;
    }
    void refreshNotes();
  }, [active, refreshNotes]);

  useEffect(() => {
    if (!active || selectedIdx === null) {
      setContent("");
      lastSavedContentRef.current = "";
      return;
    }

    let cancelled = false;
    void (async () => {
      setIsLoading(true);
      setError(null);
      try {
        const detail = await loadNoteDetail(selectedIdx);
        if (cancelled) {
          return;
        }
        setContent(detail.content);
        lastSavedContentRef.current = detail.content;
        setSaveMessage(null);
      } catch (err) {
        if (!cancelled) {
          setContent("");
          lastSavedContentRef.current = "";
          setError(err instanceof Error ? err.message : "노트를 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [active, selectedIdx, loadNoteDetail]);

  const saveContent = useCallback(
    async (silent = false) => {
      if (selectedIdx === null) {
        return true;
      }
      if (contentRef.current === lastSavedContentRef.current) {
        return true;
      }

      setIsSaving(true);
      if (!silent) {
        setError(null);
      }
      try {
        const response = await fetch(`/api/mynotes/${selectedIdx}/content`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            userid: currentUser.userid,
            content: contentRef.current,
          }),
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "노트 저장에 실패했습니다."));
        }
        const updated = (await response.json()) as MyNote;
        lastSavedContentRef.current = contentRef.current;
        setNotes((current) =>
          current.map((note) => (note.idx === updated.idx ? updated : note)),
        );
        setSaveMessage("저장됨");
        return true;
      } catch (err) {
        if (!silent) {
          setError(err instanceof Error ? err.message : "노트 저장에 실패했습니다.");
        }
        return false;
      } finally {
        setIsSaving(false);
      }
    },
    [currentUser.userid, selectedIdx],
  );

  const selectNote = useCallback(
    async (idx: number) => {
      if (idx === selectedIdx) {
        return;
      }
      await saveContent(true);
      setSelectedIdx(idx);
    },
    [saveContent, selectedIdx],
  );

  useEffect(() => {
    if (!active || selectedIdx === null) {
      return;
    }
    const interval = window.setInterval(() => {
      void saveContent(true);
    }, 10000);
    return () => window.clearInterval(interval);
  }, [active, selectedIdx, saveContent]);

  const createNote = useCallback(async () => {
    setError(null);
    try {
      const response = await fetch("/api/mynotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userid: currentUser.userid }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "노트 생성에 실패했습니다."));
      }
      const created = (await response.json()) as MyNoteDetail;
      setNotes((current) => [created, ...current]);
      setSelectedIdx(created.idx);
      setContent("");
      lastSavedContentRef.current = "";
      setSaveMessage(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "노트 생성에 실패했습니다.");
    }
  }, [currentUser.userid]);

  const createNoteFromContent = useCallback(
    async (noteContent: string, noteName?: string): Promise<number | null> => {
      setError(null);
      try {
        await saveContent(true);

        const response = await fetch("/api/mynotes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            userid: currentUser.userid,
            note_name: noteName?.trim() || undefined,
          }),
        });
        if (!response.ok) {
          throw new Error(await parseError(response, "노트 생성에 실패했습니다."));
        }
        const created = (await response.json()) as MyNoteDetail;

        const saveResponse = await fetch(`/api/mynotes/${created.idx}/content`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            userid: currentUser.userid,
            content: noteContent,
          }),
        });
        if (!saveResponse.ok) {
          throw new Error(await parseError(saveResponse, "노트 내용 저장에 실패했습니다."));
        }
        const saved = (await saveResponse.json()) as MyNote;

        setNotes((current) => [
          { ...created, ...saved, note_name: saved.note_name },
          ...current.filter((note) => note.idx !== created.idx),
        ]);
        setSelectedIdx(created.idx);
        setContent(noteContent);
        lastSavedContentRef.current = noteContent;
        setSaveMessage(null);
        return created.idx;
      } catch (err) {
        setError(err instanceof Error ? err.message : "노트 복사에 실패했습니다.");
        return null;
      }
    },
    [currentUser.userid, saveContent],
  );

  const confirmDelete = useCallback(async () => {
    if (selectedIdx === null) {
      return;
    }
    setError(null);
    try {
      const params = new URLSearchParams({ userid: currentUser.userid });
      const response = await fetch(`/api/mynotes/${selectedIdx}?${params.toString()}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "노트 삭제에 실패했습니다."));
      }
      setIsDeleteConfirmOpen(false);
      await refreshNotes();
    } catch (err) {
      setError(err instanceof Error ? err.message : "노트 삭제에 실패했습니다.");
    }
  }, [currentUser.userid, refreshNotes, selectedIdx]);

  const submitRename = useCallback(async () => {
    if (selectedIdx === null) {
      return;
    }
    const trimmed = renameValue.trim();
    if (!trimmed) {
      setError("노트 이름을 입력해 주세요.");
      return;
    }

    setError(null);
    try {
      const response = await fetch(`/api/mynotes/${selectedIdx}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          userid: currentUser.userid,
          note_name: trimmed,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "노트 이름 변경에 실패했습니다."));
      }
      const updated = (await response.json()) as MyNote;
      setNotes((current) =>
        current.map((note) => (note.idx === updated.idx ? updated : note)),
      );
      setIsRenameOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "노트 이름 변경에 실패했습니다.");
    }
  }, [currentUser.userid, renameValue, selectedIdx]);

  const selectedNote = useMemo(
    () => notes.find((note) => note.idx === selectedIdx) ?? null,
    [notes, selectedIdx],
  );

  const openRename = useCallback(() => {
    setRenameValue(selectedNote?.note_name ?? "");
    setIsRenameOpen(true);
  }, [selectedNote?.note_name]);

  return {
    notes,
    selectedIdx,
    content,
    isLoading,
    isSaving,
    error,
    saveMessage,
    hasSelection: selectedIdx !== null,
    isRenameOpen,
    renameValue,
    isDeleteConfirmOpen,
    setContent,
    selectNote,
    createNote,
    createNoteFromContent,
    openDeleteConfirm: () => setIsDeleteConfirmOpen(true),
    closeDeleteConfirm: () => setIsDeleteConfirmOpen(false),
    confirmDelete,
    openRename,
    closeRename: () => setIsRenameOpen(false),
    setRenameValue,
    submitRename,
  };
}
