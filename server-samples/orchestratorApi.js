import apiClient from './apiClient';
 
const ORCHESTRATOR_URL = import.meta.env.VITE_URL_ORCHESTRATOR;
 
// Orchestrator 리스트 가져오기 (GET /orchestrators)
export async function getOrchestratorList(queryString) {
  return await apiClient.get(`${ORCHESTRATOR_URL}?${queryString}`);
}
 
// Orchestrator 상세 조회 (GET /orchestrators/{orchestratorId})
export async function getOrchestratorInfo(orchestratorId) {
  return await apiClient.get(`${ORCHESTRATOR_URL}/${orchestratorId}`);
}
 
// Orchestrator 등록 (POST /orchestrators)
export async function createOrchestrator(data) {
  return await apiClient.post(ORCHESTRATOR_URL, data);
}
 
// Orchestrator 수정 (PUT /orchestrators/{orchestratorId})
export async function updateOrchestrator(orchestratorId, data) {
  return await apiClient.put(`${ORCHESTRATOR_URL}/${orchestratorId}`, data);
}
 
// Orchestrator 삭제 (DELETE /orchestrators/{orchestratorId})
export async function deleteOrchestrator(orchestratorId) {
  return await apiClient.delete(`${ORCHESTRATOR_URL}/${orchestratorId}`);
}
 
// Orchestrator 실행 (PUT /orchestrators/{orchestratorId}/invoke)
export async function invokeOrchestrator(orchestratorId, data) {
  return await apiClient.post(`${ORCHESTRATOR_URL}/${orchestratorId}/invoke`, data);
}
 
// 실행 내역 리스트 조회 (GET /orchestrators/{orchestratorId})/invocations)
export async function getInvocationList(orchestratorId, queryString) {
  return await apiClient.get(`${ORCHESTRATOR_URL}/${orchestratorId}/invocations?${queryString}`);
}
 
// 최신 실행 내역 조회 (GET /orchestrators/{orchestratorId}/invocations?session_id={sessionId}&latest=true)
export async function getInvocationLatest(orchestratorId, sessionId) {
  return await apiClient.get(`${ORCHESTRATOR_URL}/${orchestratorId}/invocations?session_id=${sessionId}&latest=true`);
}
 
// 실행 내역 상세 조회 (GET /orchestrators/{orchestratorId})/invocations/{orchestratorInvocationId})
export async function getInvocationInfo(orchestratorId, orchestratorInvocationId) {
  return await apiClient.get(`${ORCHESTRATOR_URL}/${orchestratorId}/invocations/${orchestratorInvocationId}`);
}
 
 
