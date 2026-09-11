import { useCallback, useEffect, useMemo, useState } from "react";

import { JobContentView } from "../jobs/JobContentView";
import { JOB_TYPE_WORKFLOW } from "../../types/job";
import { WorkflowIcon } from "./WorkflowIcon";

export interface WorkNodeResultListItem {
  uuid: string;
  name: string;
  validateDate?: string;
  lastEndDate?: string;
  lastSuccess?: boolean;
}

interface ResultFileItem {
  filename: string;
  mtime: number;
  size: number;
  is_latest: boolean;
}

interface AgentLogEntry {
  timestamp?: string;
  agent_id?: string;
  event?: string;
  status?: string;
  fail_reason?: string;
  input_message?: string;
  output_message?: string;
  workflow_uuid?: string;
  [key: string]: unknown;
}

interface WorkNodeResultsPanelProps {
  workNodes: WorkNodeResultListItem[];
  /** Canvas에서 선택된 work_node uuid. 없으면 전체 노드 목록 모드. */
  selectedWorkUuid: string | null;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function formatMtime(mtime: number): string {
  if (!Number.isFinite(mtime) || mtime <= 0) {
    return "-";
  }
  try {
    return new Date(mtime * 1000).toLocaleString();
  } catch {
    return "-";
  }
}

function formatResultFilename(filename: string, isLatest: boolean): string {
  if (isLatest || filename === "result_latest.out") {
    return "최신 결과";
  }
  const match = /^result_(\d+)\.out$/.exec(filename);
  if (!match) {
    return filename;
  }
  const digits = match[1];
  if (digits.length >= 14) {
    const y = digits.slice(0, 4);
    const mo = digits.slice(4, 6);
    const d = digits.slice(6, 8);
    const h = digits.slice(8, 10);
    const mi = digits.slice(10, 12);
    const s = digits.slice(12, 14);
    return `${y}-${mo}-${d} ${h}:${mi}:${s}`;
  }
  return filename;
}

function formatLogTimestamp(value: string | undefined): string {
  const raw = (value || "").trim();
  if (!raw) {
    return "-";
  }
  try {
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) {
      return raw;
    }
    return date.toLocaleString();
  } catch {
    return raw;
  }
}

function formatAgentLogEntry(entry: AgentLogEntry): string {
  const lines: string[] = [];
  lines.push(`[${formatLogTimestamp(entry.timestamp)}]`);
  if (entry.event) {
    lines.push(`event: ${entry.event}`);
  }
  if (entry.status) {
    lines.push(`status: ${entry.status}`);
  }
  if (entry.agent_id) {
    lines.push(`agent: ${entry.agent_id}`);
  }
  if (entry.fail_reason) {
    lines.push(`fail_reason: ${entry.fail_reason}`);
  }
  if (entry.input_message) {
    lines.push("--- input ---");
    lines.push(String(entry.input_message));
  }
  if (entry.output_message) {
    lines.push("--- output ---");
    lines.push(String(entry.output_message));
  }
  return lines.join("\n");
}

export function WorkNodeResultsPanel({
  workNodes,
  selectedWorkUuid,
}: WorkNodeResultsPanelProps) {
  const filteredNodes = useMemo(() => {
    const uuid = (selectedWorkUuid || "").trim();
    if (!uuid) {
      return workNodes.filter((node) => Boolean(node.uuid.trim()));
    }
    return workNodes.filter((node) => node.uuid === uuid);
  }, [workNodes, selectedWorkUuid]);

  const isNodeListMode = !selectedWorkUuid;

  const [selectedNodeUuid, setSelectedNodeUuid] = useState<string | null>(null);
  const [resultFiles, setResultFiles] = useState<ResultFileItem[]>([]);
  const [selectedFilename, setSelectedFilename] = useState<string | null>(null);
  const [resultContent, setResultContent] = useState("");
  const [agentLogText, setAgentLogText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [logError, setLogError] = useState<string | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingResult, setIsLoadingResult] = useState(false);
  const [isLoadingLog, setIsLoadingLog] = useState(false);

  useEffect(() => {
    if (isNodeListMode) {
      setSelectedNodeUuid((current) => {
        if (current && filteredNodes.some((node) => node.uuid === current)) {
          return current;
        }
        return filteredNodes[0]?.uuid ?? null;
      });
      return;
    }
    setSelectedNodeUuid(filteredNodes[0]?.uuid ?? null);
  }, [filteredNodes, isNodeListMode]);

  const loadResultFiles = useCallback(async (nodeUuid: string) => {
    setIsLoadingList(true);
    setError(null);
    try {
      const response = await fetch(`/api/work-nodes/${nodeUuid}/results`);
      if (!response.ok) {
        throw new Error(await parseError(response, "결과 목록을 불러오지 못했습니다."));
      }
      const data = (await response.json()) as { items?: ResultFileItem[] };
      const items = Array.isArray(data.items) ? data.items : [];
      setResultFiles(items);
      setSelectedFilename((current) => {
        if (current && items.some((item) => item.filename === current)) {
          return current;
        }
        return items[0]?.filename ?? null;
      });
    } catch (err) {
      setResultFiles([]);
      setSelectedFilename(null);
      setResultContent("");
      setError(err instanceof Error ? err.message : "결과 목록을 불러오지 못했습니다.");
    } finally {
      setIsLoadingList(false);
    }
  }, []);

  const loadAgentLog = useCallback(async (nodeUuid: string) => {
    setIsLoadingLog(true);
    setLogError(null);
    try {
      const response = await fetch(`/api/work-nodes/${nodeUuid}/agent-log?limit=200`);
      if (!response.ok) {
        throw new Error(await parseError(response, "에이전트 로그를 불러오지 못했습니다."));
      }
      const data = (await response.json()) as {
        items?: AgentLogEntry[];
        last_fail_reason?: string;
      };
      const items = Array.isArray(data.items) ? data.items : [];
      const blocks = items.map((entry) => formatAgentLogEntry(entry));
      const failReason = (data.last_fail_reason || "").trim();
      if (failReason && !items.some((entry) => entry.fail_reason === failReason)) {
        blocks.push(`[DB] fail_reason: ${failReason}`);
      }
      setAgentLogText(blocks.join("\n\n"));
    } catch (err) {
      setAgentLogText("");
      setLogError(err instanceof Error ? err.message : "에이전트 로그를 불러오지 못했습니다.");
    } finally {
      setIsLoadingLog(false);
    }
  }, []);

  useEffect(() => {
    if (!isNodeListMode && selectedNodeUuid) {
      void loadResultFiles(selectedNodeUuid);
      return;
    }
    setResultFiles([]);
    setSelectedFilename(null);
  }, [isNodeListMode, selectedNodeUuid, loadResultFiles]);

  useEffect(() => {
    if (!selectedNodeUuid) {
      setAgentLogText("");
      setLogError(null);
      return;
    }
    void loadAgentLog(selectedNodeUuid);
  }, [selectedNodeUuid, loadAgentLog]);

  useEffect(() => {
    const nodeUuid = selectedNodeUuid;
    if (!nodeUuid) {
      setResultContent("");
      return;
    }

    let cancelled = false;
    const load = async () => {
      setIsLoadingResult(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        if (!isNodeListMode && selectedFilename) {
          params.set("filename", selectedFilename);
        }
        const query = params.toString();
        const url = `/api/work-nodes/${nodeUuid}/validation-result${query ? `?${query}` : ""}`;
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(await parseError(response, "결과 파일을 불러오지 못했습니다."));
        }
        const payload = (await response.json()) as { content?: string };
        if (!cancelled) {
          setResultContent(payload.content || "");
        }
      } catch (err) {
        if (!cancelled) {
          setResultContent("");
          setError(err instanceof Error ? err.message : "결과 파일을 불러오지 못했습니다.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingResult(false);
        }
      }
    };

    if (isNodeListMode) {
      void load();
    } else if (selectedFilename) {
      void load();
    } else {
      setResultContent("");
      setIsLoadingResult(false);
    }

    return () => {
      cancelled = true;
    };
  }, [selectedNodeUuid, selectedFilename, isNodeListMode]);

  const listTitle = isNodeListMode ? "작업 노드" : "작업 결과";
  const selectedNode = filteredNodes.find((node) => node.uuid === selectedNodeUuid);

  const refreshSelected = () => {
    if (!selectedNodeUuid) {
      return;
    }
    if (!isNodeListMode) {
      void loadResultFiles(selectedNodeUuid);
    }
    void loadAgentLog(selectedNodeUuid);
  };

  return (
    <div className="flex min-h-0 flex-1 gap-3 overflow-hidden p-3">
      <aside className="flex w-[260px] shrink-0 flex-col border-r border-slate-700/80 pr-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-slate-300">
            <WorkflowIcon name={isNodeListMode ? "work-node" : "result"} size="sm" />
            {listTitle}
          </h4>
          {selectedNodeUuid ? (
            <button
              type="button"
              onClick={refreshSelected}
              className="inline-flex items-center gap-1 rounded border border-slate-600 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-slate-800"
            >
              <WorkflowIcon name="refresh" size="xs" label="새로고침" />
              새로고침
            </button>
          ) : null}
        </div>
        {!isNodeListMode && selectedNode ? (
          <p className="mb-2 truncate text-[10px] text-slate-500" title={selectedNode.name}>
            {selectedNode.name || selectedNode.uuid}
          </p>
        ) : null}
        <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto">
          {isNodeListMode ? (
            <>
              {filteredNodes.length === 0 ? (
                <p className="text-[11px] text-slate-500">워크플로우에 작업 노드가 없습니다.</p>
              ) : null}
              {filteredNodes.map((node) => {
                const selected = node.uuid === selectedNodeUuid;
                const dateLabel = node.validateDate || node.lastEndDate || "-";
                return (
                  <button
                    key={node.uuid}
                    type="button"
                    onClick={() => setSelectedNodeUuid(node.uuid)}
                    className={`block w-full rounded-md border px-2 py-1.5 text-left text-[11px] ${
                      selected
                        ? "border-sky-600 bg-sky-950/50 text-sky-100"
                        : "border-slate-700 bg-slate-900/70 text-slate-200 hover:border-slate-500"
                    }`}
                  >
                    <div className="truncate font-medium" title={node.name}>
                      {node.name || node.uuid}
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-2 text-[10px] text-slate-400">
                      <span className="min-w-0 truncate" title={dateLabel}>
                        {dateLabel}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        {node.lastSuccess == null ? (
                          "-"
                        ) : (
                          <>
                            <WorkflowIcon
                              name={node.lastSuccess ? "approve" : "fail-branch"}
                              size="xs"
                            />
                            {node.lastSuccess ? "성공" : "실패"}
                          </>
                        )}
                      </span>
                    </div>
                  </button>
                );
              })}
            </>
          ) : (
            <>
              {isLoadingList ? <p className="text-[11px] text-slate-500">불러오는 중…</p> : null}
              {!isLoadingList && resultFiles.length === 0 ? (
                <p className="text-[11px] text-slate-500">저장된 작업 결과가 없습니다.</p>
              ) : null}
              {resultFiles.map((item) => {
                const selected = item.filename === selectedFilename;
                const label = formatResultFilename(item.filename, item.is_latest);
                const mtimeLabel = formatMtime(item.mtime);
                return (
                  <button
                    key={item.filename}
                    type="button"
                    onClick={() => setSelectedFilename(item.filename)}
                    className={`block w-full rounded-md border px-2 py-1.5 text-left text-[11px] ${
                      selected
                        ? "border-sky-600 bg-sky-950/50 text-sky-100"
                        : "border-slate-700 bg-slate-900/70 text-slate-200 hover:border-slate-500"
                    }`}
                  >
                    <div className="truncate font-medium" title={label}>
                      {label}
                    </div>
                    <div className="mt-0.5 truncate text-[10px] text-slate-400" title={mtimeLabel}>
                      {mtimeLabel}
                    </div>
                  </button>
                );
              })}
            </>
          )}
        </div>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 gap-3 overflow-hidden">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-700/70 bg-slate-950/40 p-2">
          <h4 className="mb-2 inline-flex shrink-0 items-center gap-1.5 text-[11px] font-semibold text-slate-300">
            <WorkflowIcon name="result" size="sm" label="결과 내용" />
            결과 내용
          </h4>
          {error ? <p className="mb-2 shrink-0 text-[11px] text-rose-300">{error}</p> : null}
          {isLoadingResult ? (
            <p className="text-[11px] text-slate-500">결과 불러오는 중…</p>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto">
              {resultContent ? (
                <JobContentView content={resultContent} jobType={JOB_TYPE_WORKFLOW} />
              ) : (
                <p className="text-[11px] text-slate-500">
                  {isNodeListMode
                    ? "작업 노드를 선택하면 결과가 표시됩니다."
                    : "결과를 선택하면 내용이 표시됩니다."}
                </p>
              )}
            </div>
          )}
        </section>
        <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-700/70 bg-slate-950/40 p-2">
          <h4 className="mb-2 inline-flex shrink-0 items-center gap-1.5 text-[11px] font-semibold text-slate-300">
            <WorkflowIcon name="log" size="sm" label="에이전트 로그" />
            에이전트 로그
          </h4>
          {logError ? <p className="mb-2 shrink-0 text-[11px] text-rose-300">{logError}</p> : null}
          {isLoadingLog ? (
            <p className="text-[11px] text-slate-500">로그 불러오는 중…</p>
          ) : (
            <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-300">
              {agentLogText ||
                (selectedNodeUuid
                  ? "기록된 에이전트 로그가 없습니다."
                  : "작업 노드를 선택하면 로그가 표시됩니다.")}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}
