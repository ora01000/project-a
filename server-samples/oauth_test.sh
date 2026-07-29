#!/bin/bash
# 에이전트 런타임 API 직접 검증 스크립트
# 사용법:
#   ./scripts/oauth_test.sh local    # mockup (127.0.0.1:9000)
#   ./scripts/oauth_test.sh server   # 실서버 (기본값)

set -euo pipefail

MODE="${1:-server}"

if [ "$MODE" = "local" ]; then
  TOKEN_URL="http://127.0.0.1:9000/portal/auths/v1/token"
  AGENT_URL="http://127.0.0.1:9000/aihub/agents/v1"
  CLIENT_ID="mock-client-id"
  CLIENT_SECRET="mock-client-secret"
  AGENT_ID="00000000-0000-4000-8000-000000000001"
else
  TOKEN_URL="https://test.nudp.lguplus.co.kr/portal/auths/v1/token"
  AGENT_URL="https://test.nudp.lguplus.co.kr/aihub/agents/v1"
  CLIENT_ID="cfab04d9-68ed-44e6-878b-4f9928b97f8c"
  CLIENT_SECRET="c9uPxk4Ow2zgvzPfCP2jJznf472wdw3e2Wg-7gijHd4"
  AGENT_ID="c9b7ddbf-3cc8-4257-b54c-675c3229b430"
fi

SESSION_ID="8a456292-d3db-429c-ad71-af6dd26be800"
SERVICE_ID="test"
SESSION_ATTRIBUTES='{"user_id":"test"}'
PROMPT_SESSION_ATTRIBUTES='{"user_id":"test"}'
ENABLE_TRACE="false"
TEXT="안녕"

echo "▶ 모드: $MODE"
echo "▶ 요청: access_token 발급"

RESPONSE=$(curl -s -X POST "$TOKEN_URL" \
  -H "Authorization: Basic $(echo -n "$CLIENT_ID:$CLIENT_SECRET" | base64)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials")

echo "서버응답:"
echo "$RESPONSE"

ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo "토큰 발급실패"
  exit 1
fi

echo "▶ Access Token: $ACCESS_TOKEN"
echo -e "\n▶ 요청: Agent API 호출"

curl -s -X POST "$AGENT_URL/$AGENT_ID/invoke" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg service_id "$SERVICE_ID" \
    --arg session_id "$SESSION_ID" \
    --arg text "$TEXT" \
    --argjson session_attributes "$SESSION_ATTRIBUTES" \
    --argjson prompt_session_attributes "$PROMPT_SESSION_ATTRIBUTES" \
    --argjson enable_trace "$ENABLE_TRACE" \
    '{service_id: $service_id, session_id: $session_id, session_attributes: $session_attributes, prompt_session_attributes: $prompt_session_attributes, enable_trace: $enable_trace, text: $text}')" | jq .
