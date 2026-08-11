import { useCallback, useEffect, useMemo, useState } from "react";

import type { UserRecord } from "../../types/user";
import { ROLE_PENDING, hasAdminAccess } from "../../types/user";

interface EventReportSubscriptionModalProps {
  viewerRole: number;
  onClose: () => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function formatUserLabel(user: UserRecord): string {
  const depart = user.depart.trim() || "-";
  const name = user.username.trim() || "-";
  return `${depart}/${name}(${user.userid})`;
}

function subscriberButtonClass(isSelected: boolean): string {
  return isSelected
    ? "border-sky-600 bg-sky-950/60 text-sky-100"
    : "border-slate-600 bg-slate-900/80 text-slate-200 hover:border-slate-500 hover:bg-slate-800";
}

export function EventReportSubscriptionModal({
  viewerRole,
  onClose,
}: EventReportSubscriptionModalProps) {
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [selectedUserids, setSelectedUserids] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const loadData = useCallback(async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 열람할 수 있습니다.");
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [usersResponse, subsResponse] = await Promise.all([
        fetch("/api/users"),
        fetch("/api/admin/whatap-event-subscriptions"),
      ]);
      if (!usersResponse.ok) {
        throw new Error(await parseError(usersResponse, "사용자 목록을 불러오지 못했습니다."));
      }
      if (!subsResponse.ok) {
        throw new Error(await parseError(subsResponse, "구독 정보를 불러오지 못했습니다."));
      }
      const userData = (await usersResponse.json()) as UserRecord[];
      const subData = (await subsResponse.json()) as { userids: string[] };
      setUsers(userData.filter((user) => user.role !== ROLE_PENDING));
      setSelectedUserids(new Set(subData.userids ?? []));
    } catch (err) {
      setUsers([]);
      setSelectedUserids(new Set());
      setError(err instanceof Error ? err.message : "구독 정보를 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [viewerRole]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const sortedUsers = useMemo(
    () =>
      [...users].sort((left, right) => {
        const leftKey = `${left.depart}/${left.username}/${left.userid}`;
        const rightKey = `${right.depart}/${right.username}/${right.userid}`;
        return leftKey.localeCompare(rightKey, "ko");
      }),
    [users],
  );

  const toggleUser = (userid: string) => {
    setSelectedUserids((current) => {
      const next = new Set(current);
      if (next.has(userid)) {
        next.delete(userid);
      } else {
        next.add(userid);
      }
      return next;
    });
    setInfo(null);
  };

  const handleSave = async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 저장할 수 있습니다.");
      return;
    }
    setIsSaving(true);
    setError(null);
    setInfo(null);
    try {
      const response = await fetch("/api/admin/whatap-event-subscriptions", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userids: Array.from(selectedUserids) }),
      });
      if (!response.ok) {
        throw new Error(await parseError(response, "구독 정보 저장에 실패했습니다."));
      }
      const data = (await response.json()) as { userids: string[] };
      setSelectedUserids(new Set(data.userids ?? []));
      setInfo("구독자 설정을 저장했습니다.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "구독 정보 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-report-sub-title"
        className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="event-report-sub-title" className="text-lg font-semibold text-slate-100">
              이벤트 리포트 구독
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Whatap 이벤트 리포트 메일 수신 대상을 지정합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
          >
            닫기
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain pr-1">
          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-slate-400">이벤트 타입</span>
            <select
              value="whatap"
              disabled
              className="w-full cursor-not-allowed rounded-md border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-300 opacity-80"
            >
              <option value="whatap">Whatap Event</option>
            </select>
          </label>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-slate-400">구독자 지정</span>
              <span className="text-[10px] text-slate-500">{selectedUserids.size}명 선택</span>
            </div>
            {isLoading ? <p className="text-xs text-slate-500">불러오는 중...</p> : null}
            {!isLoading && sortedUsers.length === 0 ? (
              <p className="text-xs text-slate-500">지정 가능한 사용자가 없습니다.</p>
            ) : null}
            <div className="flex flex-wrap gap-1.5">
              {sortedUsers.map((user) => {
                const isSelected = selectedUserids.has(user.userid);
                return (
                  <button
                    key={user.idx}
                    type="button"
                    onClick={() => toggleUser(user.userid)}
                    className={`rounded-md border px-2.5 py-1 text-left text-[11px] font-medium transition-colors ${subscriberButtonClass(isSelected)}`}
                    title={formatUserLabel(user)}
                  >
                    {formatUserLabel(user)}
                  </button>
                );
              })}
            </div>
          </div>

          {error ? (
            <div className="rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
              {error}
            </div>
          ) : null}
          {info ? (
            <div className="rounded-md border border-emerald-800 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-200">
              {info}
            </div>
          ) : null}
        </div>

        <div className="mt-4 flex justify-end gap-2 border-t border-slate-700/80 pt-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            닫기
          </button>
          <button
            type="button"
            disabled={isLoading || isSaving || !hasAdminAccess(viewerRole)}
            onClick={() => void handleSave()}
            className="rounded-md border border-sky-700 bg-sky-950/60 px-3 py-1.5 text-sm font-medium text-sky-100 hover:bg-sky-900/70 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isSaving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
