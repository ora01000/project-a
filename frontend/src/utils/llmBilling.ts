export interface LlmBillingStatus {
  requires_confirmation: boolean;
  provider: string;
  model: string | null;
}

export async function fetchLlmBillingStatus(): Promise<LlmBillingStatus> {
  const response = await fetch("/api/llm/billing-status");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return (await response.json()) as LlmBillingStatus;
}
