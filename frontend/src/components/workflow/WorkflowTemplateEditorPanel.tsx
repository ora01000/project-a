import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ScriptCodeEditor } from "./ScriptCodeEditor";
import { WorkflowIcon } from "./WorkflowIcon";

export interface WorkflowTemplateListItem {
  idx: number;
  template_name: string;
  template_filename: string;
  name?: string;
}

interface WorkflowTemplateEditorPanelProps {
  mode?: "create" | "edit";
  onClose: () => void;
  onSaved?: (item: WorkflowTemplateListItem) => void;
}

async function parseError(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return typeof payload?.detail === "string" ? payload.detail : fallback;
}

function suggestFilenameFromName(name: string): string {
  const stem = name.trim().replace(/[<>:"/\\|?*\x00-\x1f]+/g, "_").replace(/\s+/g, "_");
  if (!stem) {
    return "";
  }
  return stem.toLowerCase().endsWith(".md") ? stem : `${stem}.md`;
}

export function WorkflowTemplateEditorPanel({
  mode = "create",
  onClose,
  onSaved,
}: WorkflowTemplateEditorPanelProps) {
  const isEdit = mode === "edit";
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [templateName, setTemplateName] = useState("");
  const [templateFilename, setTemplateFilename] = useState("");
  const [filenameTouched, setFilenameTouched] = useState(false);
  const [content, setContent] = useState("");
  const [existingTemplates, setExistingTemplates] = useState<WorkflowTemplateListItem[]>([]);
  const [selectedExisting, setSelectedExisting] = useState("");
  const [nameError, setNameError] = useState("");
  const [filenameError, setFilenameError] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const localFileRef = useRef<HTMLInputElement>(null);
  const checkTimerRef = useRef<number | null>(null);

  const loadExisting = useCallback(async () => {
    const response = await fetch("/api/workflow-templates");
    if (!response.ok) {
      throw new Error(await parseError(response, "양식 목록을 불러오지 못했습니다."));
    }
    const data = (await response.json()) as WorkflowTemplateListItem[];
    setExistingTemplates(Array.isArray(data) ? data : []);
  }, []);

  useEffect(() => {
    void loadExisting().catch((err) => {
      setError(err instanceof Error ? err.message : "양식 목록을 불러오지 못했습니다.");
    });
  }, [loadExisting]);

  useEffect(() => {
    return () => {
      if (checkTimerRef.current != null) {
        window.clearTimeout(checkTimerRef.current);
      }
    };
  }, []);

  const scheduleUniquenessCheck = useCallback(
    (name: string, filename: string, excludeIdx: number | null) => {
      if (checkTimerRef.current != null) {
        window.clearTimeout(checkTimerRef.current);
      }
      checkTimerRef.current = window.setTimeout(() => {
        void (async () => {
          const params = new URLSearchParams();
          if (name.trim()) {
            params.set("template_name", name.trim());
          }
          if (filename.trim()) {
            params.set("template_filename", filename.trim());
          }
          if (excludeIdx != null && excludeIdx > 0) {
            params.set("exclude_idx", String(excludeIdx));
          }
          if (![...params.keys()].length) {
            setNameError("");
            setFilenameError("");
            return;
          }
          setIsChecking(true);
          try {
            const response = await fetch(`/api/workflow-templates/check?${params.toString()}`);
            if (!response.ok) {
              throw new Error(await parseError(response, "중복 검사에 실패했습니다."));
            }
            const payload = (await response.json()) as {
              name_available?: boolean;
              filename_available?: boolean;
              name_error?: string;
              filename_error?: string;
              template_filename?: string;
            };
            setNameError(payload.name_available === false ? payload.name_error || "이름 중복" : "");
            setFilenameError(
              payload.filename_available === false ? payload.filename_error || "파일명 중복" : "",
            );
            if (payload.template_filename && payload.template_filename !== filename.trim()) {
              setTemplateFilename(payload.template_filename);
            }
          } catch (err) {
            setError(err instanceof Error ? err.message : "중복 검사에 실패했습니다.");
          } finally {
            setIsChecking(false);
          }
        })();
      }, 280);
    },
    [],
  );

  const handleNameChange = (value: string) => {
    setTemplateName(value);
    if (isEdit) {
      scheduleUniquenessCheck(value, templateFilename, editingIdx);
      return;
    }
    const nextFilename = filenameTouched ? templateFilename : suggestFilenameFromName(value);
    if (!filenameTouched) {
      setTemplateFilename(nextFilename);
    }
    scheduleUniquenessCheck(value, nextFilename, null);
  };

  const handleFilenameChange = (value: string) => {
    setFilenameTouched(true);
    setTemplateFilename(value);
    scheduleUniquenessCheck(templateName, value, isEdit ? editingIdx : null);
  };

  const handleLocalFile = async (file: File | null) => {
    if (!file || isEdit) {
      return;
    }
    setError(null);
    try {
      const text = await file.text();
      setContent(text);
      if (!filenameTouched || !templateFilename.trim()) {
        const next = suggestFilenameFromName(file.name);
        setTemplateFilename(next);
        setFilenameTouched(true);
        scheduleUniquenessCheck(templateName, next, null);
      }
      if (!templateName.trim()) {
        const stem = file.name.replace(/\.md$/i, "");
        setTemplateName(stem);
        scheduleUniquenessCheck(stem, templateFilename || suggestFilenameFromName(file.name), null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "로컬 파일을 읽지 못했습니다.");
    }
  };

  const loadTemplateForEdit = async (filename: string) => {
    setSelectedExisting(filename);
    if (!filename) {
      setEditingIdx(null);
      setTemplateName("");
      setTemplateFilename("");
      setContent("");
      setNameError("");
      setFilenameError("");
      return;
    }
    setError(null);
    try {
      const response = await fetch(`/api/workflow-templates/${encodeURIComponent(filename)}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "기존 양식을 불러오지 못했습니다."));
      }
      const payload = (await response.json()) as {
        idx?: number;
        content?: string;
        template_name?: string;
        template_filename?: string;
      };
      const idx = Number(payload.idx || 0) || null;
      const name = (payload.template_name || "").trim();
      const file = (payload.template_filename || filename).trim();
      setEditingIdx(idx);
      setTemplateName(name);
      setTemplateFilename(file);
      setFilenameTouched(true);
      setContent(payload.content || "");
      setNameError("");
      setFilenameError("");
      scheduleUniquenessCheck(name, file, idx);
    } catch (err) {
      setError(err instanceof Error ? err.message : "기존 양식을 불러오지 못했습니다.");
    }
  };

  const handleExistingSelect = async (filename: string) => {
    if (isEdit) {
      await loadTemplateForEdit(filename);
      return;
    }
    setSelectedExisting(filename);
    if (!filename) {
      return;
    }
    setError(null);
    try {
      const response = await fetch(`/api/workflow-templates/${encodeURIComponent(filename)}`);
      if (!response.ok) {
        throw new Error(await parseError(response, "기존 양식을 불러오지 못했습니다."));
      }
      const payload = (await response.json()) as {
        content?: string;
        template_name?: string;
        template_filename?: string;
      };
      setContent(payload.content || "");
      if (!templateName.trim() && payload.template_name) {
        setTemplateName(`${payload.template_name}_복사`);
      }
      if (!filenameTouched) {
        const next = payload.template_filename || filename;
        setTemplateFilename(next.replace(/\.md$/i, "_copy.md"));
        setFilenameTouched(true);
      }
      scheduleUniquenessCheck(
        templateName.trim() || `${payload.template_name || "template"}_복사`,
        templateFilename || (payload.template_filename || filename).replace(/\.md$/i, "_copy.md"),
        null,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "기존 양식을 불러오지 못했습니다.");
    }
  };

  const canSave = useMemo(() => {
    if (isEdit && (editingIdx == null || editingIdx <= 0 || !selectedExisting)) {
      return false;
    }
    return (
      Boolean(templateName.trim()) &&
      Boolean(templateFilename.trim()) &&
      !nameError &&
      !filenameError &&
      !isSaving &&
      !isChecking
    );
  }, [
    isEdit,
    editingIdx,
    selectedExisting,
    templateName,
    templateFilename,
    nameError,
    filenameError,
    isSaving,
    isChecking,
  ]);

  const handleSave = async () => {
    const confirmMessage = isEdit
      ? `"${templateName.trim()}" 템플릿을 수정해 저장하시겠습니까?\n기존 파일 내용이 변경됩니다.`
      : `"${templateName.trim()}" 템플릿을 새로 저장하시겠습니까?`;
    if (!window.confirm(confirmMessage)) {
      return;
    }
    setError(null);
    setIsSaving(true);
    try {
      const response = await fetch(
        isEdit ? `/api/workflow-templates/${editingIdx}` : "/api/workflow-templates",
        {
          method: isEdit ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            template_name: templateName.trim(),
            template_filename: templateFilename.trim(),
            content,
          }),
        },
      );
      if (!response.ok) {
        throw new Error(
          await parseError(response, isEdit ? "템플릿 수정에 실패했습니다." : "템플릿 저장에 실패했습니다."),
        );
      }
      const saved = (await response.json()) as WorkflowTemplateListItem & {
        template_name: string;
        template_filename: string;
        idx: number;
      };
      onSaved?.({
        idx: saved.idx,
        template_name: saved.template_name,
        template_filename: saved.template_filename,
        name: saved.template_filename,
      });
      onClose();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : isEdit
            ? "템플릿 수정에 실패했습니다."
            : "템플릿 저장에 실패했습니다.",
      );
    } finally {
      setIsSaving(false);
    }
  };

  const title = isEdit ? "템플릿 수정" : "새로운 템플릿";
  const subtitle = isEdit
    ? "등록된 양식을 선택해 이름·파일명·내용을 수정합니다."
    : "Markdown 양식을 작성해 다이어그램 생성 프롬프트에서 사용합니다.";

  return (
    <section className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-700 bg-slate-900/50 shadow-inner">
      <header className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-700/80 px-4 py-3">
        <div className="min-w-0">
          <h2 className="inline-flex items-center gap-1.5 text-sm font-semibold text-slate-100">
            <WorkflowIcon name="template" size="sm" label={title} />
            {title}
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-600 bg-slate-900 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
          >
            <WorkflowIcon name="close" size="xs" label="닫기" />
            닫기
          </button>
          <button
            type="button"
            disabled={!canSave}
            onClick={() => void handleSave()}
            className="inline-flex items-center gap-1.5 rounded-md border border-sky-700 bg-sky-950/50 px-3 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-900/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <WorkflowIcon name="save" size="xs" label="저장" />
            {isSaving ? "저장 중…" : "저장"}
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-4">
        {error ? <p className="shrink-0 text-xs text-rose-300">{error}</p> : null}

        <label className="grid shrink-0 gap-1 text-xs text-slate-400">
          기존 양식파일 {isEdit ? "선택" : "참조"}
          <select
            value={selectedExisting}
            onChange={(event) => {
              void handleExistingSelect(event.target.value);
            }}
            className="rounded-md border border-slate-700 bg-slate-950 px-2 py-2 text-sm text-slate-100"
          >
            <option value="">{isEdit ? "수정할 양식 선택" : "선택"}</option>
            {existingTemplates.map((item) => (
              <option key={item.idx || item.template_filename} value={item.template_filename}>
                {item.template_name} ({item.template_filename})
              </option>
            ))}
          </select>
        </label>

        <div className="grid shrink-0 gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-xs text-slate-400">
            양식 이름
            <input
              value={templateName}
              onChange={(event) => handleNameChange(event.target.value)}
              maxLength={70}
              disabled={isEdit && !selectedExisting}
              className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-50"
              placeholder="예: 일일 점검"
            />
            {nameError ? <span className="text-[11px] text-rose-300">{nameError}</span> : null}
          </label>
          <label className="grid gap-1 text-xs text-slate-400">
            저장될 파일이름
            <input
              value={templateFilename}
              onChange={(event) => handleFilenameChange(event.target.value)}
              maxLength={200}
              disabled={isEdit && !selectedExisting}
              className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 disabled:opacity-50"
              placeholder="example.md"
            />
            {filenameError ? (
              <span className="text-[11px] text-rose-300">{filenameError}</span>
            ) : (
              <span className="text-[11px] text-slate-500">Markdown(.md) 파일로 저장됩니다.</span>
            )}
          </label>
        </div>

        {!isEdit ? (
          <div className="grid shrink-0 gap-1 text-xs text-slate-400">
            로컬 양식파일 참조
            <input
              ref={localFileRef}
              type="file"
              accept=".md,text/markdown,text/plain"
              className="block w-full text-xs text-slate-300 file:mr-2 file:rounded file:border-0 file:bg-slate-800 file:px-2 file:py-1 file:text-xs file:text-slate-100"
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                void handleLocalFile(file);
                event.target.value = "";
              }}
            />
          </div>
        ) : null}

        <div className="flex min-h-0 flex-1 flex-col gap-1">
          <div className="flex shrink-0 items-center justify-between text-xs text-slate-400">
            <span>양식 편집 (Markdown)</span>
            {isChecking ? <span className="text-[11px] text-slate-500">중복 검사 중…</span> : null}
          </div>
          <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border border-slate-700">
            <div className="absolute inset-0">
              <ScriptCodeEditor
                value={content}
                disabled={isEdit && !selectedExisting}
                onChange={setContent}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
