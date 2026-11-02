import type { InventoryKeyValueParam } from "../../types/inventory";

interface InventoryKeyValueParamsEditorProps {
  label: string;
  items: InventoryKeyValueParam[];
  disabled?: boolean;
  onChange: (items: InventoryKeyValueParam[]) => void;
}

export function InventoryKeyValueParamsEditor({
  label,
  items,
  disabled = false,
  onChange,
}: InventoryKeyValueParamsEditorProps) {
  const updateAt = (index: number, patch: Partial<InventoryKeyValueParam>) => {
    onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-slate-300">{label}</span>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange([...items, { key: "", value: "" }])}
          className="rounded border border-slate-600 px-2 py-0.5 text-[11px] text-slate-200 hover:bg-slate-800 disabled:opacity-50"
        >
          추가
        </button>
      </div>
      {items.length === 0 ? (
        <p className="text-[11px] text-slate-500">파라미터가 없습니다.</p>
      ) : (
        <div className="space-y-1.5">
          {items.map((item, index) => (
            <div key={`param-${index}`} className="flex items-center gap-1.5">
              <input
                type="text"
                value={item.key}
                disabled={disabled}
                onChange={(event) => updateAt(index, { key: event.target.value })}
                placeholder="key"
                className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950/80 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
              />
              <span className="text-slate-500">=</span>
              <input
                type="text"
                value={item.value}
                disabled={disabled}
                onChange={(event) => updateAt(index, { value: event.target.value })}
                placeholder="value"
                className="min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950/80 px-2 py-1.5 font-mono text-xs text-slate-100 outline-none focus:border-sky-600 disabled:opacity-70"
              />
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(items.filter((_, i) => i !== index))}
                className="shrink-0 rounded border border-slate-600 px-2 py-1 text-[11px] text-rose-200 hover:bg-rose-950/40 disabled:opacity-50"
              >
                삭제
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
