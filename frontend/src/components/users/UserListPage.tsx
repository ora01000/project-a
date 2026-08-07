import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog } from "../ConfirmDialog";
import { UserFormModal } from "./UserFormModal";
import type { UserFormValues, UserRecord } from "../../types/user";
import { hasAdminAccess, bandLabel, roleLabel } from "../../types/user";

interface UserListPageProps {
  currentUserIdx: number;
  currentUserRole: number;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? fallback;
}

export function UserListPage({ currentUserIdx, currentUserRole }: UserListPageProps) {
  const canManageUsers = hasAdminAccess(currentUserRole);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [formMode, setFormMode] = useState<"create" | "edit" | null>(null);
  const [editingUser, setEditingUser] = useState<UserRecord | null>(null);
  const [deletingUser, setDeletingUser] = useState<UserRecord | null>(null);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "사용자 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [currentUserRole]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  const closeForm = () => {
    setFormMode(null);
    setEditingUser(null);
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
    if (!editingUser) {
      throw new Error("수정할 사용자를 선택해 주세요.");
    }

    const response = await fetch(`/api/users/${editingUser.idx}`, {
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
      setDeletingUser(null);
      return;
    }
    if (!deletingUser) {
      return;
    }
    if (deletingUser.idx === currentUserIdx) {
      setError("현재 로그인한 사용자는 삭제할 수 없습니다.");
      setDeletingUser(null);
      return;
    }

    const response = await fetch("/api/users", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idx_list: [deletingUser.idx], viewer_role: currentUserRole }),
    });
    if (!response.ok) {
      setError(await parseError(response, "사용자 삭제에 실패했습니다."));
      setDeletingUser(null);
      return;
    }

    setDeletingUser(null);
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
          <button
            type="button"
            onClick={() => {
              setError(null);
              setEditingUser(null);
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
          <p className="text-sm text-slate-500">사용자 목록을 불러오는 중...</p>
        ) : (
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                <th className="px-3 py-2">아이디</th>
                <th className="px-3 py-2">이메일</th>
                <th className="px-3 py-2">이름</th>
                <th className="px-3 py-2">직책</th>
                <th className="px-3 py-2">조직</th>
                <th className="px-3 py-2">역할</th>
                <th className="px-3 py-2">최근 로그인 시각</th>
                {canManageUsers ? <th className="px-3 py-2">작업</th> : null}
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.idx} className="border-b border-slate-800 text-slate-200">
                  <td className="px-3 py-2">{user.userid}</td>
                  <td className="px-3 py-2">{user.email}</td>
                  <td className="px-3 py-2">{user.username}</td>
                  <td className="px-3 py-2">{bandLabel(user.band)}</td>
                  <td className="px-3 py-2">{user.depart}</td>
                  <td className="px-3 py-2">
                    {user.role}: {roleLabel(user.role)}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-300">
                    {user.last_login?.trim() || "-"}
                  </td>
                  {canManageUsers ? (
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setEditingUser(user);
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
                            setDeletingUser(user);
                          }}
                          disabled={user.idx === currentUserIdx}
                          className="rounded-md border border-rose-800 px-2 py-1 text-xs text-rose-200 hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:border-slate-700 disabled:text-slate-500"
                        >
                          삭제
                        </button>
                      </div>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canManageUsers && formMode ? (
        <UserFormModal
          mode={formMode}
          user={formMode === "edit" ? editingUser ?? undefined : undefined}
          onClose={closeForm}
          onSave={formMode === "create" ? handleCreate : handleUpdate}
        />
      ) : null}

      {canManageUsers && deletingUser ? (
        <ConfirmDialog
          title="사용자 삭제"
          message={`'${deletingUser.userid}' 사용자를 삭제하시겠습니까?`}
          confirmLabel="예"
          cancelLabel="아니오"
          onCancel={() => setDeletingUser(null)}
          onConfirm={() => void handleDelete()}
        />
      ) : null}
    </div>
  );
}
