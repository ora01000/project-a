#!/bin/bash

# URL
TOKEN_URL="https://test.nudp.lguplus.co.kr/portal/auths/v1/token"
AGENT_URL="https://test.nudp.lguplus.co.kr/aihub/agents/v1"

# Å½ºƮ¿ëEYS
CLIENT_ID="cfab04d9-68ed-44e6-878b-4f9928b97f8c" # °í°ª
CLIENT_SECRET="c9uPxk4Ow2zgvzPfCP2jJznf472wdw3e2Wg-7gijHd4" # °í°ª

# BODY JSON
SESSION_ID="8a456292-d3db-429c-ad71-af6dd26be800" # ¼¼¼Çä¹øVICE_ID="test" # °í°ª
AGENT_ID="c9b7ddbf-3cc8-4257-b54c-675c3229b430" # °í°ª
SESSION_ATTRIBUTES='{"user_id":"test"}' #SSO or SITE¿¡¼­ ¹Þº °ª
PROMPT_SESSION_ATTRIBUTES='{"user_id":"test"}' # PROMPT¿¡ ³Ö» °ª
ENABLE_TRACE="false" # °í°ª
TEXT="¾ȳç # »çÀ À·Â°ª

# === 1. Access Token ¹߱Þ===
# ACCESS Åū /ȿ±Ⱓ: 1½ð£
echo "¢º¿ä: access_token ¹߱Þ

RESPONSE=$(curl -s -k -v -X POST "$TOKEN_URL" \
  -H "Authorization: Basic $(echo -n $CLIENT_ID:$CLIENT_SECRET | base64)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials")

echo "¼­¹ö´äø
echo "$RESPONSE"

ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo "Åū ¹߱Þ½ÇÐ
  exit 1
fi

echo "¢ºAccess Token: $ACCESS_TOKEN"

# === 2. Agent API ȣÃ ===
echo -e "\n¢º¿ä: Agent API ȣÃ"

curl -i -k -v -X POST "$AGENT_URL/$AGENT_ID/invoke" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg service_id "$SERVICE_ID" \
    --arg session_id "$SESSION_ID" \
    --arg text "$TEXT" \
    --argjson session_attributes "$SESSION_ATTRIBUTES" \
    --argjson prompt_session_attributes "$PROMPT_SESSION_ATTRIBUTES" \
    --argjson enable_trace "$ENABLE_TRACE" \
    '{service_id: $service_id, session_id: $session_id, session_attributes: $session_attributes, prompt_session_attributes: $prompt_session_attributes, enable_trace: $enable_trace, text: $text}')"

# À´䰪
# {
# "text": "\uc548\ub155?", -> Agent À´䰪
# "retrieval_results": [], -> °˻öútrace": [] -> °á ÃÀ
# }

