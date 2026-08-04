import apiClient from './apiClient';
 
const AGENT_URL = import.meta.env.VITE_URL_AGENT;
 
// Agent 리스트 가져오기 (GET /agents)
export async function getAgentList(queryString) {
  return await apiClient.get(`${AGENT_URL}?${queryString}`);
}
 
// Agent 상세 조회 (GET /agents/{agentId})
export async function getAgentInfo(agentId) {
  return await apiClient.get(`${AGENT_URL}/${agentId}`);
}
 
// Agent 등록 (POST /agents)
export async function createAgent(data) {
  return await apiClient.post(AGENT_URL, data);
}
 
// Agent 수정 (PUT /agents/{agentId})
export async function updateAgent(agentId, data) {
  return await apiClient.put(`${AGENT_URL}/${agentId}`, data);
}
 
// Agent 삭제 (DELETE /agents/{agentId})
export async function deleteAgent(agentId) {
  return await apiClient.delete(`${AGENT_URL}/${agentId}`);
}
 
// Agent 실행 (PUT /agents/{agentId}/invoke)
export async function invokeAgent(agentId, data) {
  return await apiClient.post(`${AGENT_URL}/${agentId}/invoke`, data);
}
 
// 실행 내역 리스트 조회 (GET /agents/{agentId})/invocations)
export async function getInvocationList(agentId, queryString) {
  return await apiClient.get(`${AGENT_URL}/${agentId}/invocations?${queryString}`);
}
 
// 최신 실행 내역 조회 (GET /agents/{agentId}/invocations?session_id={sessionId}&latest=true)
export async function getInvocationLatest(agentId, sessionId) {
  return await apiClient.get(`${AGENT_URL}/${agentId}/invocations?session_id=${sessionId}&latest=true`);
}
 
// 실행 내역 상세 조회 (GET /agents/{agentId})/invocations/{agentInvocationId})
export async function getInvocationInfo(agentId, agentInvocationId) {
  return await apiClient.get(`${AGENT_URL}/${agentId}/invocations/${agentInvocationId}`);
}
 
