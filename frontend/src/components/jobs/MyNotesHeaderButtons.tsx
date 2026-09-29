import type { UseMyNotesResult } from "./useMyNotes";

interface MyNotesHeaderButtonsProps {
  myNotes: UseMyNotesResult;
}

export function MyNotesHeaderButtons({ myNotes }: MyNotesHeaderButtonsProps) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => void myNotes.createNote()}
        className="rounded-md border border-sky-700 bg-sky-950/60 px-2.5 py-1 text-xs font-medium text-sky-100 hover:bg-sky-900/70"
      >
        새로운 노트
      </button>
      <button
        type="button"
        disabled={!myNotes.hasSelection}
        onClick={myNotes.openRename}
        className="rounded-md border border-slate-600 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        이름 변경
      </button>
      <button
        type="button"
        disabled={!myNotes.hasSelection}
        onClick={myNotes.openDeleteConfirm}
        className="rounded-md border border-rose-700 bg-rose-950/60 px-2.5 py-1 text-xs font-medium text-rose-100 hover:bg-rose-900/70 disabled:cursor-not-allowed disabled:opacity-40"
      >
        노트 삭제
      </button>
    </div>
  );
}
