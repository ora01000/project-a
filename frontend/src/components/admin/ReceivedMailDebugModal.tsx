import { useCallback, useEffect, useState } from "react";

import { hasAdminAccess } from "../../types/user";

interface ReceivedMailDebugModalProps {
  viewerRole: number;
  onClose: () => void;
}

interface ReceivedMailItem {
  idx: number;
  uuid: string;
  decision_type: number;
  message_id: string;
  imap_uid: number | null;
  pop3_uidl: string;
  mailbox: string;
  subject: string;
  from_address: string;
  to_addresses: string;
  cc_addresses: string;
  body_text: string;
  received_at: string;
  fetched_at: string;
  attachment_count: number;
  attachment_names: string[];
  unreadable_attachment_names?: string[];
}

const DECISION_LABELS: Record<number, string> = {
  0: "대기(0)",
  5: "자료부족(5)",
  10: "작업(10)",
  11: "비작업(11)",
};

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

export function ReceivedMailDebugModal({ viewerRole, onClose }: ReceivedMailDebugModalProps) {
  const [items, setItems] = useState<ReceivedMailItem[]>([]);
  const [selected, setSelected] = useState<ReceivedMailItem | null>(null);
  const [decisionFilter, setDecisionFilter] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const loadList = useCallback(async () => {
    if (!hasAdminAccess(viewerRole)) {
      setError("관리자만 열람할 수 있습니다.");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "100", offset: "0" });
      if (decisionFilter !== "") {
        params.set("decision_type", decisionFilter);
      }
      const response = await fetch(`/api/received-mail?${params.toString()}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "수신 메일 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as ReceivedMailItem[];
      setItems(data);
      setSelected((current) => {
        if (!current) {
          return data[0] ?? null;
        }
        return data.find((item) => item.uuid === current.uuid) ?? data[0] ?? null;
      });
    } catch (err) {
      setItems([]);
      setSelected(null);
      setError(err instanceof Error ? err.message : "수신 메일 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [decisionFilter, viewerRole]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const downloadAttachment = async (mailUuid: string, filename: string) => {
    setError(null);
    try {
      const response = await fetch(
        `/api/received-mail/${encodeURIComponent(mailUuid)}/attachments/${encodeURIComponent(filename)}`,
      );
      if (!response.ok) {
        throw new Error(await parseError(response, "첨부 다운로드에 실패했습니다."));
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "첨부 다운로드에 실패했습니다.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="received-mail-debug-title"
        className="flex max-h-[92vh] w-full max-w-5xl flex-col rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-xl"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 id="received-mail-debug-title" className="text-sm font-semibold text-slate-100">
              수신메일 목록 (디버깅)
            </h2>
            <p className="mt-1 text-[11px] text-slate-400">
              IMAP/POP3 폴링으로 저장된 `received_mail` 레코드입니다. role=0|100만 접근 가능합니다.
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

        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-2 text-slate-300">
            <span>decision_type</span>
            <select
              value={decisionFilter}
              onChange={(event) => setDecisionFilter(event.target.value)}
              className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-100"
            >
              <option value="">전체</option>
              <option value="0">0 대기</option>
              <option value="5">5 자료부족</option>
              <option value="10">10 작업</option>
              <option value="11">11 비작업</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => void loadList()}
            disabled={isLoading}
            className="rounded-md border border-slate-600 px-2.5 py-1 text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            {isLoading ? "불러오는 중..." : "새로고침"}
          </button>
          <span className="text-slate-500">{items.length}건</span>
        </div>

        {error ? (
          <p className="mb-3 rounded-md border border-rose-800 bg-rose-950/40 px-2 py-1.5 text-[11px] text-rose-200">
            {error}
          </p>
        ) : null}

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden md:grid-cols-2">
          <div className="min-h-0 overflow-y-auto rounded-md border border-slate-700 bg-slate-950/50">
            {items.length === 0 && !isLoading ? (
              <p className="p-3 text-xs text-slate-500">수신 메일이 없습니다.</p>
            ) : null}
            <ul className="divide-y divide-slate-800 text-xs">
              {items.map((item) => {
                const isActive = selected?.uuid === item.uuid;
                return (
                  <li key={item.uuid}>
                    <button
                      type="button"
                      onClick={() => setSelected(item)}
                      className={`block w-full px-3 py-2 text-left hover:bg-slate-800/80 ${
                        isActive ? "bg-sky-950/40" : ""
                      }`}
                    >
                      <div className="truncate font-medium text-slate-100">
                        {item.subject || "(제목 없음)"}
                      </div>
                      <div className="mt-0.5 truncate text-[10px] text-slate-400">
                        {item.from_address || "-"} · {item.fetched_at || item.received_at || "-"}
                      </div>
                      <div className="mt-0.5 text-[10px] text-slate-500">
                        {DECISION_LABELS[item.decision_type] ?? `type=${item.decision_type}`} · 첨부{" "}
                        {item.attachment_count}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="min-h-0 overflow-y-auto rounded-md border border-slate-700 bg-slate-950/50 p-3 text-xs text-slate-200">
            {!selected ? (
              <p className="text-slate-500">메일을 선택하면 상세가 표시됩니다.</p>
            ) : (
              <div className="space-y-2">
                <div>
                  <span className="text-slate-500">uuid</span>
                  <p className="font-mono text-[11px] break-all">{selected.uuid}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-slate-500">idx</span>
                    <p>{selected.idx}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">decision_type</span>
                    <p>{DECISION_LABELS[selected.decision_type] ?? selected.decision_type}</p>
                  </div>
                </div>
                <div>
                  <span className="text-slate-500">subject</span>
                  <p>{selected.subject || "-"}</p>
                </div>
                <div>
                  <span className="text-slate-500">from</span>
                  <p className="break-all">{selected.from_address || "-"}</p>
                </div>
                <div>
                  <span className="text-slate-500">to</span>
                  <p className="break-all">{selected.to_addresses || "-"}</p>
                </div>
                <div>
                  <span className="text-slate-500">cc</span>
                  <p className="break-all">{selected.cc_addresses || "-"}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-slate-500">received_at</span>
                    <p>{selected.received_at || "-"}</p>
                  </div>
                  <div>
                    <span className="text-slate-500">fetched_at</span>
                    <p>{selected.fetched_at || "-"}</p>
                  </div>
                </div>
                <div>
                  <span className="text-slate-500">message_id / imap_uid / pop3_uidl</span>
                  <p className="break-all font-mono text-[10px] text-slate-400">
                    {selected.message_id || "-"} / {selected.imap_uid ?? "-"} / {selected.pop3_uidl || "-"}
                  </p>
                </div>
                <div>
                  <span className="text-slate-500">attachments</span>
                  {selected.attachment_names.length === 0 ? (
                    <p className="text-slate-500">없음</p>
                  ) : (
                    <ul className="mt-1 space-y-1">
                      {selected.attachment_names.map((name) => (
                        <li key={name}>
                          <button
                            type="button"
                            onClick={() => void downloadAttachment(selected.uuid, name)}
                            className="text-sky-300 underline hover:text-sky-200"
                          >
                            {name}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <span className="text-slate-500">unreadable attachments</span>
                  {(selected.unreadable_attachment_names ?? []).length === 0 ? (
                    <p className="text-slate-500">없음</p>
                  ) : (
                    <p>{(selected.unreadable_attachment_names ?? []).join(", ")}</p>
                  )}
                </div>
                <div>
                  <span className="text-slate-500">body_text</span>
                  <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-slate-800 bg-slate-950 p-2 text-[11px] text-slate-300">
                    {selected.body_text || "(empty)"}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
