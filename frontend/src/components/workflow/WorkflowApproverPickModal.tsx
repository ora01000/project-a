import { useMemo, useState } from "react";

import type { WorkflowApprover } from "../../types/workflow";
import { WorkflowIcon } from "./WorkflowIcon";

interface WorkflowApproverPickModalProps {
  approvers: WorkflowApprover[];
  initialUserid?: string;
  onClose: () => void;
  onConfirm: (approver: { userid: string; username: string }) => void;
}

function formatApproverLabel(item: WorkflowApprover): string {
  const name = (item.username || "").trim() || item.userid;
  return `${name}(${item.userid})`;
}

function userButtonClass(isSelected: boolean): string {
  return isSelected
    ? "border-sky-600 bg-sky-950/60 text-sky-100"
    : "border-slate-600 bg-slate-900/80 text-slate-200 hover:border-slate-500 hover:bg-slate-800";
}

export function WorkflowApproverPickModal({
  approvers,
  initialUserid = "",
  onClose,
  onConfirm,
}: WorkflowApproverPickModalProps) {
  const [selectedUserid, setSelectedUserid] = useState((initialUserid || "").trim());
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) {
      return approvers;
    }
    return approvers.filter((item) => {
      const haystack = `${item.username} ${item.userid}`.toLowerCase();
      return haystack.includes(keyword);
    });
  }, [approvers, search]);

  const selected = useMemo(
    () => approvers.find((item) => item.userid === selectedUserid) ?? null,
    [approvers, selectedUserid],
  );

  const handleConfirm = () => {
    if (!selected) {
      setError("결재자를 한 명 선택해 주세요.");
      return;
    }
    onConfirm({
      userid: selected.userid,
      username: (selected.username || "").trim() || selected.userid,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="workflow-approver-pick-title"
        className="flex max-h-[92vh] w-full max-w-2xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 id="workflow-approver-pick-title" className="text-sm font-semibold text-slate-100">
            결재자 선택
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
          <div className="space-y-2 rounded-md border border-slate-700 bg-slate-950/60 p-3">
            <h3 className="text-[10px] font-semibold text-sky-300">선택된 결재자</h3>
            {selected ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-sky-700/80 bg-sky-950/50 px-2 py-0.5 text-[10px] text-sky-100">
                <span>{formatApproverLabel(selected)}</span>
                <button
                  type="button"
                  onClick={() => setSelectedUserid("")}
                  className="rounded px-0.5 text-slate-300 hover:bg-slate-800 hover:text-white"
                  aria-label="결재자 선택 해제"
                >
                  <WorkflowIcon name="delete" size="xs" label="선택 해제" />
                </button>
              </span>
            ) : (
              <p className="text-[11px] text-slate-500">아직 선택되지 않았습니다.</p>
            )}
          </div>

          <label className="block space-y-1 text-xs">
            <span className="text-slate-400">등록된 사용자 검색</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="이름, 아이디"
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-2 py-1.5 text-slate-100"
            />
          </label>

          <div className="rounded-md border border-slate-700 bg-slate-950/60 p-3">
            <h3 className="mb-2 text-[11px] font-semibold text-slate-300">등록된 사용자</h3>
            {filtered.length === 0 ? (
              <p className="text-xs text-slate-500">선택 가능한 사용자가 없습니다.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {filtered.map((item) => {
                  const isSelected = item.userid === selectedUserid;
                  return (
                    <button
                      key={item.userid}
                      type="button"
                      title={item.userid}
                      aria-pressed={isSelected}
                      onClick={() => {
                        setSelectedUserid(item.userid);
                        setError(null);
                      }}
                      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${userButtonClass(isSelected)}`}
                    >
                      {formatApproverLabel(item)}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <p className="mt-2 text-[11px] text-slate-500">결재자는 1명만 선택할 수 있습니다.</p>

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
            onClick={handleConfirm}
            className="rounded-md bg-sky-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-600"
          >
            적용
          </button>
        </div>
      </div>
    </div>
  );
}
