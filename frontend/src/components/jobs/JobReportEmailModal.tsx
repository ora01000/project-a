import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import type { UserRecord } from "../../types/user";
import { ROLE_PENDING } from "../../types/user";

export interface JobReportRequester {
  name: string;
  email: string;
  depart: string;
  madangId: string;
}

type RecipientColumn = "to" | "cc" | "bcc";

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

function columnTabClass(isActive: boolean): string {
  return isActive
    ? "border-sky-600 bg-sky-950/60 text-sky-100"
    : "border-slate-600 bg-slate-900/80 text-slate-300 hover:border-slate-500 hover:bg-slate-800";
}

function recipientChipClass(column: RecipientColumn): string {
  if (column === "to") {
    return "border-sky-700/80 bg-sky-950/50 text-sky-100";
  }
  if (column === "cc") {
    return "border-amber-700/80 bg-amber-950/40 text-amber-100";
  }
  return "border-violet-700/80 bg-violet-950/40 text-violet-100";
}

function userButtonClass(column: RecipientColumn, isInColumn: boolean): string {
  if (!isInColumn) {
    return "border-slate-600 bg-slate-900/80 text-slate-200 hover:border-slate-500 hover:bg-slate-800";
  }
  if (column === "to") {
    return "border-sky-600 bg-sky-950/60 text-sky-100";
  }
  if (column === "cc") {
    return "border-amber-600 bg-amber-950/60 text-amber-100";
  }
  return "border-violet-600 bg-violet-950/60 text-violet-100";
}

const COLUMN_LABELS: Record<RecipientColumn, string> = {
  to: "수신자",
  cc: "참조",
  bcc: "숨은참조",
};

const DEFAULT_FORWARD_MESSAGE = "AI를 통해 생성된 처리 결과를 메일로 전달드립니다.";

export function JobReportEmailModal({
  subject: initialSubject,
  sendEndpoint,
  requester = null,
  extraBody,
  onClose,
  onSent,
}: JobReportEmailModalProps) {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [toUserIdxs, setToUserIdxs] = useState<Set<number>>(new Set());
  const [ccUserIdxs, setCcUserIdxs] = useState<Set<number>>(new Set());
  const [bccUserIdxs, setBccUserIdxs] = useState<Set<number>>(new Set());
  const [includeRequester, setIncludeRequester] = useState(false);
  const [activeColumn, setActiveColumn] = useState<RecipientColumn>("to");
  const [emailSubject, setEmailSubject] = useState(initialSubject);
  const [forwardMessage, setForwardMessage] = useState(DEFAULT_FORWARD_MESSAGE);
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
      setUsers(
        data.filter((user) => user.email.includes("@") && user.role !== ROLE_PENDING),
      );
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

  useEffect(() => {
    setEmailSubject(initialSubject);
  }, [initialSubject]);

  const usersByIdx = useMemo(() => new Map(users.map((user) => [user.idx, user])), [users]);

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

  const activeSet = useMemo(() => {
    if (activeColumn === "cc") {
      return ccUserIdxs;
    }
    if (activeColumn === "bcc") {
      return bccUserIdxs;
    }
    return toUserIdxs;
  }, [activeColumn, bccUserIdxs, ccUserIdxs, toUserIdxs]);

  const setActiveSet = (updater: (current: Set<number>) => Set<number>) => {
    if (activeColumn === "cc") {
      setCcUserIdxs(updater);
      return;
    }
    if (activeColumn === "bcc") {
      setBccUserIdxs(updater);
      return;
    }
    setToUserIdxs(updater);
  };

  const removeFromColumn = (column: RecipientColumn, userIdx: number) => {
    const updater = (current: Set<number>) => {
      const next = new Set(current);
      next.delete(userIdx);
      return next;
    };
    if (column === "cc") {
      setCcUserIdxs(updater);
      return;
    }
    if (column === "bcc") {
      setBccUserIdxs(updater);
      return;
    }
    setToUserIdxs(updater);
  };

  const toggleUser = (idx: number) => {
    setActiveSet((current) => {
      const next = new Set(current);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const toCount = toUserIdxs.size + (includeRequester && requesterHasEmail ? 1 : 0);
  const totalSelected = toCount + ccUserIdxs.size + bccUserIdxs.size;

  const renderRecipientChips = (column: RecipientColumn, idxSet: Set<number>) => {
    const chips: ReactNode[] = [];

    if (column === "to" && includeRequester && requesterHasEmail) {
      chips.push(
        <span
          key="requester"
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${recipientChipClass(column)}`}
        >
          <span title={requester?.email}>{requesterLabel}</span>
          <button
            type="button"
            onClick={() => setIncludeRequester(false)}
            className="rounded px-0.5 text-slate-300 hover:bg-slate-800 hover:text-white"
            aria-label="SR 기안자 제거"
          >
            ×
          </button>
        </span>,
      );
    }

    for (const userIdx of idxSet) {
      const user = usersByIdx.get(userIdx);
      if (!user) {
        continue;
      }
      const label = formatRecipientLabel(user.depart, user.username, user.userid);
      chips.push(
        <span
          key={`${column}-${userIdx}`}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${recipientChipClass(column)}`}
        >
          <span title={user.email}>{label}</span>
          <button
            type="button"
            onClick={() => removeFromColumn(column, userIdx)}
            className="rounded px-0.5 text-slate-300 hover:bg-slate-800 hover:text-white"
            aria-label={`${label} 제거`}
          >
            ×
          </button>
        </span>,
      );
    }

    if (chips.length === 0) {
      return <p className="text-[10px] text-slate-500">선택된 {COLUMN_LABELS[column]}가 없습니다.</p>;
    }

    return <div className="flex flex-wrap gap-1.5">{chips}</div>;
  };

  const handleSend = async () => {
    if (toCount === 0) {
      setError("수신자를 한 명 이상 선택해 주세요.");
      return;
    }
    if (!emailSubject.trim()) {
      setError("제목을 입력해 주세요.");
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
          recipient_user_idxs: Array.from(toUserIdxs),
          cc_user_idxs: Array.from(ccUserIdxs),
          bcc_user_idxs: Array.from(bccUserIdxs),
          include_requester: Boolean(requester && includeRequester && requesterHasEmail),
          subject: emailSubject.trim(),
          forward_message: forwardMessage,
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
        className="flex max-h-[92vh] w-full max-w-2xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 id="job-report-email-dialog-title" className="text-sm font-semibold text-slate-100">
            리포트 메일 전송
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          <label className="block space-y-1 text-xs">
            <span className="text-slate-400">제목</span>
            <input
              type="text"
              value={emailSubject}
              maxLength={300}
              onChange={(event) => setEmailSubject(event.target.value)}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
            />
          </label>

          <label className="block space-y-1 text-xs">
            <span className="text-slate-400">추가 내용</span>
            <textarea
              value={forwardMessage}
              onChange={(event) => setForwardMessage(event.target.value)}
              rows={3}
              placeholder="리포트 위에 추가할 메시지를 입력하세요."
              className="w-full resize-y rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100 placeholder:text-slate-500"
            />
          </label>

          <div className="space-y-2 rounded-md border border-slate-700 bg-slate-950/60 p-3">
            <div>
              <h3 className="mb-1 text-[10px] font-semibold text-sky-300">수신자</h3>
              {renderRecipientChips("to", toUserIdxs)}
            </div>
            <div>
              <h3 className="mb-1 text-[10px] font-semibold text-amber-300">참조</h3>
              {renderRecipientChips("cc", ccUserIdxs)}
            </div>
            <div>
              <h3 className="mb-1 text-[10px] font-semibold text-violet-300">숨은참조</h3>
              {renderRecipientChips("bcc", bccUserIdxs)}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {(["to", "cc", "bcc"] as RecipientColumn[]).map((column) => (
              <button
                key={column}
                type="button"
                onClick={() => setActiveColumn(column)}
                aria-pressed={activeColumn === column}
                className={`rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${columnTabClass(activeColumn === column)}`}
              >
                {COLUMN_LABELS[column]} 선택
              </button>
            ))}
          </div>

          <label className="block space-y-1 text-xs">
            <span className="text-slate-400">
              등록된 사용자 검색 ({COLUMN_LABELS[activeColumn]}에 추가)
            </span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="조직, 이름, 아이디"
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
            />
          </label>

          <div className="rounded-md border border-slate-700 bg-slate-950/60 p-3">
            {activeColumn === "to" && requester ? (
              <section className="mb-3">
                <h3 className="mb-2 text-[11px] font-semibold text-slate-300">SR 기안자</h3>
                {requesterHasEmail ? (
                  <button
                    type="button"
                    onClick={() => setIncludeRequester((current) => !current)}
                    title={requester.email}
                    aria-pressed={includeRequester}
                    className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${userButtonClass("to", includeRequester)}`}
                  >
                    {requesterLabel}
                  </button>
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
                  const isInColumn = activeSet.has(user.idx);
                  const label = formatRecipientLabel(user.depart, user.username, user.userid);
                  return (
                    <button
                      key={user.idx}
                      type="button"
                      onClick={() => toggleUser(user.idx)}
                      title={user.email}
                      aria-pressed={isInColumn}
                      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${userButtonClass(activeColumn, isInColumn)}`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </section>
          </div>
        </div>

        <p className="mt-2 text-[11px] text-slate-500">
          선택 {totalSelected}명 (수신 {toCount}, 참조 {ccUserIdxs.size}, 숨은참조 {bccUserIdxs.size})
        </p>

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
            disabled={isSending || toCount === 0 || !emailSubject.trim()}
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
