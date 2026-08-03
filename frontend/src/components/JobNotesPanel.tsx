import { useCallback, useEffect, useState } from "react";

import type { AuthUser } from "../types/auth";
import { JobReviewTab } from "./jobs/JobReviewTab";
import { MyJobResultsTab } from "./jobs/MyJobResultsTab";
import { MyJobReviewTab } from "./jobs/MyJobReviewTab";
import { MyNotesHeaderButtons } from "./jobs/MyNotesHeaderButtons";
import { MyNotesTab } from "./jobs/MyNotesTab";
import { useMyNotes } from "./jobs/useMyNotes";

type JobNotesTab = "review" | "my-review" | "my-results" | "my-notes";

const TABS: { id: JobNotesTab; label: string }[] = [
  { id: "review", label: "작업 검토" },
  { id: "my-review", label: "나의 검토작업" },
  { id: "my-results", label: "나의 작업결과" },
  { id: "my-notes", label: "나의 노트" },
];

interface JobNotesPanelProps {
  className?: string;
  currentUser: AuthUser;
  onCopyToNoteReady?: (handler: (content: string, noteName?: string) => Promise<void>) => void;
}

function renderActiveTab(
  tab: JobNotesTab,
  currentUser: AuthUser,
  myNotes: ReturnType<typeof useMyNotes>,
  onCopyToNote: (content: string, noteName?: string) => Promise<void>,
) {
  switch (tab) {
    case "review":
      return <JobReviewTab active currentUser={currentUser} />;
    case "my-review":
      return <MyJobReviewTab active currentUser={currentUser} />;
    case "my-results":
      return <MyJobResultsTab active currentUser={currentUser} onCopyToNote={onCopyToNote} />;
    case "my-notes":
      return <MyNotesTab myNotes={myNotes} />;
  }
}

export function JobNotesPanel({
  className = "",
  currentUser,
  onCopyToNoteReady,
}: JobNotesPanelProps) {
  const [activeTab, setActiveTab] = useState<JobNotesTab>("review");
  const myNotes = useMyNotes(currentUser, activeTab === "my-notes");

  const handleCopyToNote = useCallback(
    async (content: string, noteName?: string) => {
      const noteIdx = await myNotes.createNoteFromContent(content, noteName);
      if (noteIdx !== null) {
        setActiveTab("my-notes");
      }
    },
    [myNotes.createNoteFromContent],
  );

  useEffect(() => {
    onCopyToNoteReady?.(handleCopyToNote);
  }, [handleCopyToNote, onCopyToNoteReady]);

  return (
    <section className={`relative flex min-h-0 min-w-0 flex-col ${className}`.trim()}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner"
      />

      <div className="relative z-10 flex min-h-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-slate-700/80 px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-200">작업 노트</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                접수된 작업요청서를 확인하고 처리 상태를 관리합니다.
              </p>
            </div>
            {activeTab === "my-notes" ? <MyNotesHeaderButtons myNotes={myNotes} /> : null}
          </div>
        </header>

        <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-700/80 px-3 pt-2">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`shrink-0 rounded-t-md px-3 py-2 text-xs font-medium ${
                activeTab === tab.id
                  ? "border border-b-0 border-slate-600 bg-slate-800 text-sky-200"
                  : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {renderActiveTab(activeTab, currentUser, myNotes, handleCopyToNote)}
        </div>
      </div>
    </section>
  );
}
