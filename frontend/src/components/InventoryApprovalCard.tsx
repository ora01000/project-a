export interface InventoryApprovalRequest {
  approvalId: string;
  callerAgentId: string;
  callerAgentName: string;
  query: string;
}

interface InventoryApprovalCardProps {
  request: InventoryApprovalRequest;
  isProcessing: boolean;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
}

export function InventoryApprovalCard({
  request,
  isProcessing,
  onApprove,
  onReject,
}: InventoryApprovalCardProps) {
  return (
    <div className="rounded-md border border-amber-700/50 bg-amber-950/30 px-3 py-2 text-sm text-amber-50">
      <p className="mb-1 text-xs font-medium text-amber-200">인벤토리 조회 승인 요청</p>
      <p className="mb-2 text-xs text-amber-100/90">
        <span className="font-medium">{request.callerAgentName}</span> 에이전트가 인벤토리 에이전트를
        호출하려 합니다.
      </p>
      <p className="mb-3 rounded border border-amber-800/40 bg-amber-950/40 px-2 py-1.5 text-xs text-amber-50/90">
        {request.query}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={isProcessing}
          onClick={() => onApprove(request.approvalId)}
          className="rounded-md bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          승인
        </button>
        <button
          type="button"
          disabled={isProcessing}
          onClick={() => onReject(request.approvalId)}
          className="rounded-md border border-amber-700 px-3 py-1 text-xs text-amber-100 hover:bg-amber-900/50 disabled:opacity-50"
        >
          거부
        </button>
      </div>
    </div>
  );
}
