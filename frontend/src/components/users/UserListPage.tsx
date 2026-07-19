import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog } from "../ConfirmDialog";
import { UserFormModal } from "./UserFormModal";
import type { UserFormValues, UserRecord } from "../../types/user";
import { ROLE_ADMIN, bandLabel, roleLabel } from "../../types/user";

interface UserListPageProps {
  currentUserIdx: number;
  currentUserRole: number;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function UserListPage({ currentUserIdx, currentUserRole }: UserListPageProps) {
  const canManageUsers = currentUserRole === ROLE_ADMIN;
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [selectedIdxSet, setSelectedIdxSet] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const selectedUsers = useMemo(
    () => users.filter((user) => selectedIdxSet.has(user.idx)),
    [users, selectedIdxSet],
  );

  const loadUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/users?viewer_role=${currentUserRole}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "사용자 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as UserRecord[];
      setUsers(data);
      setSelectedIdxSet((current) => {
        const valid = new Set(data.map((user) => user.idx));
        return new Set([...current].filter((idx) => valid.has(idx)));
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "사용자 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [currentUserRole]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  const toggleRow = (idx: number) => {
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

  const toggleAll = () => {
    if (selectedIdxSet.size === users.length) {
      setSelectedIdxSet(new Set());
      return;
    }
    setSelectedIdxSet(new Set(users.map((user) => user.idx)));
  };

  const handleCreate = async (values: UserFormValues) => {
    if (!canManageUsers) {
      throw new Error("관리자만 사용자를 추가할 수 있습니다.");
    }
    const response = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...values, viewer_role: currentUserRole }),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "사용자 추가에 실패했습니다."));
    }
    await loadUsers();
  };

  const handleUpdate = async (values: UserFormValues) => {
    if (!canManageUsers) {
      throw new Error("관리자만 사용자를 수정할 수 있습니다.");
    }
    const target = selectedUsers[0];
    if (!target) {
      throw new Error("수정할 사용자를 선택해 주세요.");
    }

    const response = await fetch(`/api/users/${target.idx}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: values.email,
        username: values.username,
        password: values.password.trim() ? values.password : null,
        depart: values.depart,
        role: values.role,
        band: values.band,
        viewer_role: currentUserRole,
      }),
    });
    if (!response.ok) {
      throw new Error(await parseError(response, "사용자 수정에 실패했습니다."));
    }
    await loadUsers();
  };

  const handleDelete = async () => {
    if (!canManageUsers) {
      setError("관리자만 사용자를 삭제할 수 있습니다.");
      setShowDeleteConfirm(false);
      return;
    }
    if (selectedIdxSet.size === 0) {
      return;
    }
    if (selectedIdxSet.has(currentUserIdx)) {
      setError("현재 로그인한 사용자는 삭제할 수 없습니다.");
      setShowDeleteConfirm(false);
      return;
    }

    const response = await fetch("/api/users", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idx_list: [...selectedIdxSet], viewer_role: currentUserRole }),
    });
    if (!response.ok) {
      setError(await parseError(response, "사용자 삭제에 실패했습니다."));
      setShowDeleteConfirm(false);
      return;
    }

    setShowDeleteConfirm(false);
    setSelectedIdxSet(new Set());
    await loadUsers();
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200">사용자 조회</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            {canManageUsers
              ? "users 테이블 데이터를 조회하고 관리합니다."
              : "users 테이블 데이터를 조회합니다."}
          </p>
        </div>
        {canManageUsers ? (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowDeleteConfirm(true)}
              disabled={selectedIdxSet.size === 0}
              className="rounded-md border border-rose-800 px-3 py-1.5 text-sm text-rose-200 hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:text-slate-500"
            >
              삭제
            </button>
            <button
              type="button"
              onClick={() => {
                if (selectedUsers.length !== 1) {
                  setError("수정할 사용자 1명을 선택해 주세요.");
                  return;
                }
                setError(null);
                setFormMode("edit");
              }}
              disabled={selectedUsers.length !== 1}
              className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:text-slate-500"
            >
              수정
            </button>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setFormMode("create");
              }}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
            >
              추가
            </button>
          </div>
        ) : null}
      </header>

      {error ? (
        <div className="mx-4 mt-4 rounded-md border border-rose-800 bg-rose-950/40 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">사용자 목록을 불러오는 중...</p>
        ) : (
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                {canManageUsers ? (
                  <th className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={users.length > 0 && selectedIdxSet.size === users.length}
                      onChange={toggleAll}
                      aria-label="전체 선택"
                    />
                  </th>
                ) : null}
                <th className="px-3 py-2">아이디</th>
                <th className="px-3 py-2">이메일</th>
                <th className="px-3 py-2">이름</th>
                <th className="px-3 py-2">직책</th>
                <th className="px-3 py-2">조직</th>
                <th className="px-3 py-2">역할</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.idx} className="border-b border-slate-800 text-slate-200">
                  {canManageUsers ? (
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={selectedIdxSet.has(user.idx)}
                        onChange={() => toggleRow(user.idx)}
                        aria-label={`${user.userid} 선택`}
                      />
                    </td>
                  ) : null}
                  <td className="px-3 py-2">{user.userid}</td>
                  <td className="px-3 py-2">{user.email}</td>
                  <td className="px-3 py-2">{user.username}</td>
                  <td className="px-3 py-2">{bandLabel(user.band)}</td>
                  <td className="px-3 py-2">{user.depart}</td>
                  <td className="px-3 py-2">
                    {user.role}: {roleLabel(user.role)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canManageUsers && formMode ? (
        <UserFormModal
          mode={formMode}
          user={formMode === "edit" ? selectedUsers[0] : undefined}
          onClose={() => setFormMode(null)}
          onSave={formMode === "create" ? handleCreate : handleUpdate}
        />
      ) : null}

      {canManageUsers && showDeleteConfirm ? (
        <ConfirmDialog
          title="사용자 삭제"
          message={`선택한 ${selectedIdxSet.size}명의 사용자를 삭제하시겠습니까?`}
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setShowDeleteConfirm(false)}
          onConfirm={() => void handleDelete()}
        />
      ) : null}
    </div>
  );
}
