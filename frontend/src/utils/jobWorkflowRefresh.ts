export const JOB_WORKFLOW_REFRESH_EVENT = "project-a:job-workflow-refresh";

/** Align with job notes tab polling interval. */
export const JOB_WORKFLOW_POLL_INTERVAL_MS = 10000;

export function requestJobWorkflowRefresh(): void {
  window.dispatchEvent(new CustomEvent(JOB_WORKFLOW_REFRESH_EVENT));
}
