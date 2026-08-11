import { useCallback, useEffect, useMemo, useState } from "react";

import type { UserRecord } from "../../types/user";

export interface JobReportRequester {
  name: string;
  email: string;
  depart: string;
  madangId: string;
}

interface JobReportEmailModalProps {
  subject: string;
  sendEndpoint: string;
  requester?: JobReportRequester | null;
  extraBody?: Record<string, unknown>;
  onClose: () => void;
  onSent: (message: string) => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function formatRecipientLabel(depart: string, name: string, id: string): string {
  return `${depart}/${name}(${id})`;
}

function recipientButtonClass(isSelected: boolean): string {
  return isSelected
    ? "border-sky-600 bg-sky-950/60 text-sky-100"
    : "border-slate-600 bg-slate-900/80 text-slate-200 hover:border-slate-500 hover:bg-slate-800";
}

export function JobReportEmailModal({
  subject,
  sendEndpoint,
  requester = null,
  extraBody,
  onClose,
  onSent,
}: JobReportEmailModalProps) {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [selectedIdxSet, setSelectedIdxSet] = useState<Set<number>>(new Set());
  const [includeRequester, setIncludeRequester] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const requesterEmail = requester?.email.trim().toLowerCase() ?? "";
  const requesterHasEmail = requesterEmail.includes("@");
  const requesterLabel = requester
    ? formatRecipientLabel(
        requester.depart.trim() || "-",
        requester.name.trim() || "-",
        requester.madangId.trim() || requester.email.trim() || "-",
      )
    : "";

  const loadUsers = useCallback(async () => {
    setIsLoadingUsers(true);
    setError(null);
    try {
      const response = await fetch("/api/users");
      if (!response.ok) {
        throw new Error(await parseError(response, "사용자 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as UserRecord[];
      setUsers(data.filter((user) => user.email.includes("@")));
    } catch (err) {
      setUsers([]);
      setError(err instanceof Error ? err.message : "사용자 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoadingUsers(false);
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  const registeredUsers = useMemo(() => {
    if (!requesterHasEmail) {
      return users;
    }
    return users.filter((user) => user.email.trim().toLowerCase() !== requesterEmail);
  }, [requesterEmail, requesterHasEmail, users]);

  const filteredUsers = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) {
      return registeredUsers;
    }
    return registeredUsers.filter((user) => {
      const haystack = `${user.username} ${user.userid} ${user.email} ${user.depart}`.toLowerCase();
      return haystack.includes(keyword);
    });
  }, [registeredUsers, search]);

  const selectedCount = selectedIdxSet.size + (requester && includeRequester && requesterHasEmail ? 1 : 0);

  const toggleUser = (idx: number) => {
    setSelectedIdxSet((current) => {
      const next = new Set(current);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const handleSend = async () => {
    if (selectedCount === 0) {
      setError("수신자를 한 명 이상 선택해 주세요.");
      return;
    }

    setIsSending(true);
    setError(null);
    try {
      const response = await fetch(sendEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...extraBody,
          recipient_user_idxs: Array.from(selectedIdxSet),
          include_requester: Boolean(requester && includeRequester && requesterHasEmail),
        }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "메일 전송에 실패했습니다."));
      }
      const data = (await response.json()) as { message?: string };
      onSent(data.message ?? "메일을 전송했습니다.");
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "메일 전송에 실패했습니다.");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="job-report-email-dialog-title"
        className="flex max-h-[90vh] w-full max-w-lg flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="job-report-email-dialog-title" className="text-sm font-semibold text-slate-100">
              리포트 메일 전송
            </h2>
            <p className="mt-1 truncate text-[11px] text-slate-400" title={subject}>
              제목: {subject}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <label className="block space-y-1 text-xs">
          <span className="text-slate-400">수신자 검색</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="조직, 이름, 아이디"
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
          />
        </label>

        <div className="mt-3 min-h-0 flex-1 space-y-4 overflow-y-auto rounded-md border border-slate-700 bg-slate-950/60 p-3">
          {requester ? (
            <section>
              <h3 className="mb-2 text-[11px] font-semibold text-slate-300">SR 기안자</h3>
              {requesterHasEmail ? (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setIncludeRequester((current) => !current)}
                    title={requester.email}
                    aria-pressed={includeRequester}
                    className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${recipientButtonClass(includeRequester)}`}
                  >
                    {requesterLabel}
                  </button>
                </div>
              ) : (
                <p className="text-xs text-slate-500">기안자 이메일이 없어 선택할 수 없습니다.</p>
              )}
            </section>
          ) : null}

          <section>
            <h3 className="mb-2 text-[11px] font-semibold text-slate-300">등록된 사용자</h3>
            {isLoadingUsers ? (
              <p className="text-xs text-slate-500">사용자 목록 불러오는 중...</p>
            ) : null}
            {!isLoadingUsers && filteredUsers.length === 0 ? (
              <p className="text-xs text-slate-500">선택 가능한 사용자가 없습니다.</p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {filteredUsers.map((user) => {
                const isSelected = selectedIdxSet.has(user.idx);
                const label = formatRecipientLabel(user.depart, user.username, user.userid);
                return (
                  <button
                    key={user.idx}
                    type="button"
                    onClick={() => toggleUser(user.idx)}
                    title={user.email}
                    aria-pressed={isSelected}
                    className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${recipientButtonClass(isSelected)}`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </section>
        </div>

        <p className="mt-2 text-[11px] text-slate-500">선택 {selectedCount}명</p>

        {error ? (
          <p className="mt-3 rounded-md border border-rose-800 bg-rose-950/40 px-2 py-1.5 text-[11px] text-rose-200">
            {error}
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            취소
          </button>
          <button
            type="button"
            disabled={isSending || selectedCount === 0}
            onClick={() => void handleSend()}
            className="rounded-md bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600 disabled:opacity-50"
          >
            {isSending ? "전송 중..." : "메일 전송"}
          </button>
        </div>
      </div>
    </div>
  );
}
