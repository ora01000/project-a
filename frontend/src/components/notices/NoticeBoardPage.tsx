import { useCallback, useEffect, useState } from "react";

import type { AuthUser } from "../../types/auth";
import type { NoticeFormValues, NoticeRecord } from "../../types/notice";
import { noticeScheduleStatus } from "../../types/notice";
import { ROLE_ADMIN } from "../../types/user";
import { ConfirmDialog } from "../ConfirmDialog";
import { NoticeFormModal } from "./NoticeFormModal";

interface NoticeBoardPageProps {
  user: AuthUser;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function NoticeBoardPage({ user }: NoticeBoardPageProps) {
  const isAdmin = user.role === ROLE_ADMIN;
  const [notices, setNotices] = useState<NoticeRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [editingNotice, setEditingNotice] = useState<NoticeRecord | null>(null);
  const [deletingNotice, setDeletingNotice] = useState<NoticeRecord | null>(null);
  const [togglingIdx, setTogglingIdx] = useState<number | null>(null);

  const loadNotices = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/notices");
      if (!response.ok) {
        throw new Error(await parseError(response, "공지사항을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as NoticeRecord[];
      setNotices(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "공지사항을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadNotices();
  }, [loadNotices]);

  const handleCreate = async (values: NoticeFormValues) => {
    const response = await fetch("/api/notices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        writer: user.userid,
        from_date: values.from_date,
        until_date: values.until_date,
        title: values.title,
        notice: values.notice,
        welcome_popup: values.welcome_popup,
        viewer_role: user.role,
      }),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "공지사항 추가에 실패했습니다."));
    }
    await loadNotices();
  };

  const handleUpdate = async (values: NoticeFormValues) => {
    if (!editingNotice) {
      throw new Error("수정할 공지사항을 선택해 주세요.");
    }
    const response = await fetch(`/api/notices/${editingNotice.idx}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        from_date: values.from_date,
        until_date: values.until_date,
        title: values.title,
        notice: values.notice,
        welcome_popup: values.welcome_popup,
        viewer_role: user.role,
      }),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "공지사항 수정에 실패했습니다."));
    }
    await loadNotices();
  };

  const handleDelete = async () => {
    if (!deletingNotice) {
      return;
    }
    const response = await fetch("/api/notices", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idx_list: [deletingNotice.idx],
        viewer_role: user.role,
      }),
    });
    if (!response.ok) {
      setError(await parseError(response, "공지사항 삭제에 실패했습니다."));
      setDeletingNotice(null);
      return;
    }
    setDeletingNotice(null);
    await loadNotices();
  };

  const handleToggleWelcomePopup = async (notice: NoticeRecord) => {
    if (!isAdmin || togglingIdx != null) {
      return;
    }
    setTogglingIdx(notice.idx);
    setError(null);
    try {
      const response = await fetch(`/api/notices/${notice.idx}/welcome-popup`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          welcome_popup: !notice.welcome_popup,
          viewer_role: user.role,
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "웰컴백 표시 변경에 실패했습니다."));
      }
      const updated = (await response.json()) as NoticeRecord;
      setNotices((current) =>
        current.map((item) => (item.idx === updated.idx ? updated : item)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "웰컴백 표시 변경에 실패했습니다.");
    } finally {
      setTogglingIdx(null);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">공지사항</h2>
          <p className="mt-0.5 text-xs text-slate-500">notice_board 테이블 공지 목록입니다.</p>
        </div>
        {isAdmin ? (
          <button
            type="button"
            onClick={() => {
              setError(null);
              setEditingNotice(null);
              setFormMode("create");
            }}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            추가
          </button>
        ) : null}
      </header>

      {error ? (
        <div className="mx-4 mt-4 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">공지사항을 불러오는 중...</p>
        ) : notices.length === 0 ? (
          <p className="text-sm text-slate-500">등록된 공지사항이 없습니다.</p>
        ) : (
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                <th className="px-3 py-2">글번호</th>
                <th className="px-3 py-2">제목</th>
                <th className="px-3 py-2">작성자</th>
                <th className="px-3 py-2">작성일시</th>
                <th className="px-3 py-2">공지시작</th>
                <th className="px-3 py-2">공지기한</th>
                <th className="px-3 py-2">웰컴백 팝업 표시여부</th>
                {isAdmin ? <th className="px-3 py-2">작업</th> : null}
              </tr>
            </thead>
            <tbody>
              {notices.map((notice) => {
                const scheduleStatus = noticeScheduleStatus(notice);
                return (
                <tr key={notice.idx} className="border-b border-slate-800 text-slate-200">
                  <td className="px-3 py-2">{notice.idx}</td>
                  <td className="px-3 py-2">{notice.title}</td>
                  <td className="px-3 py-2">{notice.writer_name?.trim() || notice.writer}</td>
                  <td className="px-3 py-2 whitespace-nowrap font-mono text-xs">
                    {notice.write_date}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{notice.from_date}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{notice.until_date}</td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      role="switch"
                      aria-checked={notice.welcome_popup}
                      aria-label={`${notice.title} 웰컴백 팝업`}
                      disabled={!isAdmin || togglingIdx === notice.idx}
                      onClick={() => void handleToggleWelcomePopup(notice)}
                      className={`relative h-6 w-11 rounded-full transition ${
                        notice.welcome_popup ? "bg-sky-500" : "bg-slate-700"
                      } ${!isAdmin ? "cursor-default opacity-80" : ""}`}
                    >
                      <span
                        className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition ${
                          notice.welcome_popup ? "translate-x-5" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </td>
                  {isAdmin ? (
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setEditingNotice(notice);
                            setFormMode("edit");
                          }}
                          className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:bg-slate-800"
                        >
                          수정
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setDeletingNotice(notice);
                          }}
                          className="rounded-md border border-rose-800 px-2 py-1 text-xs text-rose-200 hover:bg-rose-950/40"
                        >
                          삭제
                        </button>
                        {scheduleStatus === "scheduled" ? (
                          <button
                            type="button"
                            tabIndex={-1}
                            className="cursor-default rounded-md border border-amber-700/70 bg-amber-950/40 px-2 py-1 text-xs font-medium text-amber-200"
                          >
                            공지예정
                          </button>
                        ) : null}
                        {scheduleStatus === "expired" ? (
                          <button
                            type="button"
                            tabIndex={-1}
                            className="cursor-default rounded-md border border-slate-600 bg-slate-800 px-2 py-1 text-xs font-medium text-slate-400"
                          >
                            만료
                          </button>
                        ) : null}
                      </div>
                    </td>
                  ) : null}
                </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {formMode && isAdmin ? (
        <NoticeFormModal
          mode={formMode}
          notice={formMode === "edit" ? editingNotice ?? undefined : undefined}
          writerUserid={user.userid}
          writerUsername={user.username}
          onClose={() => {
            setFormMode(null);
            setEditingNotice(null);
          }}
          onSave={formMode === "create" ? handleCreate : handleUpdate}
        />
      ) : null}

      {deletingNotice && isAdmin ? (
        <ConfirmDialog
          title="공지사항 삭제"
          message={`'${deletingNotice.title}' 공지사항을 삭제하시겠습니까?`}
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setDeletingNotice(null)}
          onConfirm={() => void handleDelete()}
        />
      ) : null}
    </div>
  );
}
