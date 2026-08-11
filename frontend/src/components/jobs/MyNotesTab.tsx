import { useEffect, useState } from "react";

import type { AuthUser } from "../../types/auth";
import { AssistantMessageContent } from "../AssistantMessageContent";
import { ConfirmDialog } from "../ConfirmDialog";
import type { UseMyNotesResult } from "./useMyNotes";
import { JobReportEmailModal } from "./JobReportEmailModal";

type NotePanelMode = "edit" | "preview";

function noteButtonClass(isSelected: boolean): string {
  return isSelected
    ? "border-sky-600 bg-sky-950/60 text-sky-100"
    : "border-transparent bg-transparent text-slate-300 hover:bg-slate-800/70 hover:text-slate-100";
}

function panelModeButtonClass(isSelected: boolean): string {
  return isSelected
    ? "border-slate-600 bg-slate-800 text-sky-200"
    : "border-transparent text-slate-400 hover:bg-slate-800/60 hover:text-slate-200";
}

interface MyNotesTabProps {
  myNotes: UseMyNotesResult;
  currentUser: AuthUser;
}

export function MyNotesTab({ myNotes, currentUser }: MyNotesTabProps) {
  const {
    notes,
    selectedIdx,
    content,
    isLoading,
    isSaving,
    error,
    saveMessage,
    isRenameOpen,
    renameValue,
    isDeleteConfirmOpen,
    setContent,
    selectNote,
    closeDeleteConfirm,
    confirmDelete,
    closeRename,
    setRenameValue,
    submitRename,
  } = myNotes;

  const [panelMode, setPanelMode] = useState<NotePanelMode>("edit");
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [emailSuccess, setEmailSuccess] = useState<string | null>(null);
  const selectedNote = notes.find((note) => note.idx === selectedIdx) ?? null;
  const hasNoteContent = content.trim().length > 0;

  useEffect(() => {
    setPanelMode("edit");
  }, [selectedIdx]);

  return (
    <>
      <div className="flex min-h-0 flex-1 gap-3 overflow-hidden p-3">
        <aside className="flex w-[148px] shrink-0 flex-col border-r border-slate-700/80 pr-3">
          <h3 className="mb-2 text-xs font-semibold text-slate-300">노트 목록</h3>
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain">
            {isLoading && notes.length === 0 ? (
              <p className="text-xs text-slate-500">불러오는 중...</p>
            ) : null}
            {!isLoading && notes.length === 0 ? (
              <p className="text-xs text-slate-500">노트가 없습니다.</p>
            ) : null}
            {notes.map((note) => {
              const isSelected = note.idx === selectedIdx;
              return (
                <button
                  key={note.idx}
                  type="button"
                  onClick={() => void selectNote(note.idx)}
                  className={`block w-full rounded-md border px-2 py-1.5 text-left text-[11px] font-medium transition-colors ${noteButtonClass(isSelected)}`}
                  title={note.note_name}
                >
                  <span className="line-clamp-2 break-words">{note.note_name}</span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="mb-2 flex shrink-0 items-center justify-between gap-2">
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setPanelMode("edit")}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium ${panelModeButtonClass(panelMode === "edit")}`}
              >
                노트 편집
              </button>
              <button
                type="button"
                onClick={() => setPanelMode("preview")}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium ${panelModeButtonClass(panelMode === "preview")}`}
              >
                미리보기
              </button>
            </div>
            <div className="flex items-center gap-2">
              {selectedNote ? (
                <button
                  type="button"
                  disabled={!hasNoteContent}
                  onClick={() => {
                    setEmailSuccess(null);
                    setEmailModalOpen(true);
                  }}
                  className="shrink-0 rounded-md border border-slate-600 bg-slate-800/80 px-2 py-1 text-[10px] font-medium text-slate-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  메일 전송
                </button>
              ) : null}
              {saveMessage || isSaving ? (
                <span className="text-[10px] text-slate-500">
                  {isSaving ? "저장 중..." : saveMessage}
                </span>
              ) : null}
            </div>
          </div>

          {emailSuccess ? <p className="mb-2 text-xs text-emerald-300">{emailSuccess}</p> : null}

          {error ? <p className="mb-2 text-sm text-rose-300">{error}</p> : null}

          {!selectedNote ? (
            <p className="text-sm text-slate-500">
              노트를 선택하거나 상단의 새로운 노트를 눌러 시작하세요.
            </p>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {panelMode === "edit" ? (
                <textarea
                  value={content}
                  onChange={(event) => setContent(event.target.value)}
                  placeholder="작업 결과나 채팅 응답을 붙여넣고 편집하세요. (Markdown 지원)"
                  className="min-h-0 flex-1 resize-none rounded-md border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-600 focus:outline-none"
                />
              ) : (
                <div className="note-preview-panel flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-700/80 bg-slate-950/40">
                  <div className="min-h-0 flex-1 overflow-auto overscroll-contain p-3">
                    {content.trim() ? (
                      <AssistantMessageContent content={content} />
                    ) : (
                      <p className="text-sm text-slate-500">미리볼 내용이 없습니다.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {isDeleteConfirmOpen && selectedNote ? (
        <ConfirmDialog
          title="노트 삭제"
          message={`"${selectedNote.note_name}" 노트를 삭제하시겠습니까?`}
          confirmLabel="삭제"
          onConfirm={() => void confirmDelete()}
          onCancel={closeDeleteConfirm}
        />
      ) : null}

      {emailModalOpen && selectedNote ? (
        <JobReportEmailModal
          subject={selectedNote.note_name}
          sendEndpoint={`/api/mynotes/${selectedNote.idx}/send-email`}
          extraBody={{ userid: currentUser.userid }}
          onClose={() => setEmailModalOpen(false)}
          onSent={(message) => setEmailSuccess(message)}
        />
      ) : null}

      {isRenameOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
          <div
            role="dialog"
            aria-modal="true"
            className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
          >
            <h2 className="text-base font-semibold text-slate-100">이름 변경</h2>
            <input
              type="text"
              value={renameValue}
              maxLength={50}
              onChange={(event) => setRenameValue(event.target.value)}
              className="mt-3 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-sky-600 focus:outline-none"
              placeholder="노트 이름"
              autoFocus
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={closeRename}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => void submitRename()}
                className="rounded-md border border-sky-700 bg-sky-950/60 px-3 py-1.5 text-sm font-medium text-sky-100 hover:bg-sky-900/70"
              >
                저장
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
