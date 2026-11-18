# DEV REQUEST — inventory-api ServiceNow dual token (auth_type=4)

대상: **project-e** (`inventory-mcp` / inventory-api)  
요청자: project-A  
관련 PLAN: `PLAN_AXIT_PLATFORM.md` (서비스나우 Token / 이중 토큰)

## 배경

서비스나우(ITOM) origin API는 단일 token이 아니라 **두 개의 발급 API**가 필요하다.

1. 서비스나우 Token 발급
2. APIM 포탈 Token 발급
3. origin 호출 시 두 헤더를 동시에 부착

기존 `auth_type=3`(Token)은 유지한다. project-A는 UI·프록시·카탈로그 필드 패스스루만 하며, **발급·캐시·401/403 재시도는 project-e가 담당**한다.

## 확정 규약

### 발급·호출 순서

1. 서비스나우 토큰 발급
2. APIM 포탈 토큰 발급
3. origin API 호출

### origin 요청 헤더 (고정, Bearer 접두사 없음)

```http
X-Partners-Token: {snow_access_token}
Authorization: {apim_access_token}
```

- 헤더명 `Authorization`을 사용한다 (Bearer 접두사 없음 — 토큰 값만).
- 값에 `Bearer ` 접두사를 붙이지 않는다.

### auth_type

| 값 | 의미 |
|----|------|
| 1 | Bearer (기존) |
| 2 | Header (기존) |
| 3 | Token — APIM 단일 토큰 → `Authorization: Bearer {token}` (기존) |
| **4** | **ServiceNow Token — 이중 토큰 (신규)** |

## 필드 계약

### 런타임 요청 (`POST /retrieve`, `POST /testAPI`)

auth=4일 때 **둘 다 필수**:

| 역할 | 필드 |
|------|------|
| APIM 발급 | 기존 `token_api`, `token_api_method?`(기본 POST), `token_api_params?`, `token_api_headers?` |
| 서비스나우 발급 | **신규** `snow_token_api`, `snow_token_api_method?`(기본 POST), `snow_token_api_params?`, `snow_token_api_headers?` |

params/headers 문자열 형식은 auth=3과 동일 (`Name=value&Name=value`, 값의 `&`/`=`/`+`는 `%26`/`%3D`/`%2B`).

### 카탈로그 (`POST /addInventory`, `GET /getInventoryList`)

| 역할 | 저장 컬럼/필드 |
|------|----------------|
| APIM | 기존 `origin_token_api`, `origin_token_api_method`, `origin_token_api_params`, `origin_token_api_headers` |
| 서비스나우 | **신규** `origin_snow_token_api`, `origin_snow_token_api_method`, `origin_snow_token_api_params`, `origin_snow_token_api_headers` |
| auth | `origin_api_auth_type=4` |

목록 응답:

- APIM params/headers: 기존처럼 `has_token_api_params` / `has_token_api_headers`만 (원문 비노출)
- SNOW params/headers: **신규** `has_snow_token_api_params` / `has_snow_token_api_headers`만 (원문 비노출)
- URL·method는 노출 (`origin_token_api`, `origin_snow_token_api`, 각 method)
- 빈 문자열로 params/headers 재저장 시 **기존 비밀값 유지** (auth=3과 동일)

### 토큰 응답 파서

양쪽 발급 API 모두 기존과 동일:

- JSON에서 `access_token` (top-level 또는 1-depth wrapper)
- optional `expires_in`, `token_type`

형식이 다르면 e에서 파서를 확장하되, A 계약은 `access_token` 기준으로 둔다.

## 동작 요구

### `request_origin` (auth=4)

1. snow token issue (캐시 가능)
2. APIM token issue (캐시 가능)
3. origin에 고정 헤더 2개 + custom headers 병합
4. status ∈ {401, 403}이면 **두 토큰 모두 force 재발급** 후 origin **1회만** 재시도
5. 재시도도 실패하면 그 응답/에러를 그대로 반환 (무한 재발급 금지)

### 캐시 키

snow·APIM 각각 별도 캐시 엔트리. 키 재료에 각 URL·method·params·headers 포함 (auth=3과 동일하게 해시 권장).

### custom header 충돌

origin `api_headers` / `headers`에 다음 이름이 있으면 `invalid_api_headers`:

- `X-Partners-Token`
- `Authorization`

(기존 금지 헤더 규칙도 유지)

### `POST /testTokenIssue`

신규 엔드포인트 불필요. APIM·SNOW 각각 기존 필드로 단독 테스트한다.

요청: `token_api`, `token_api_method?`, `token_api_params?`, `token_api_headers?`  
(서비스나우 테스트 시에도 동일 스키마 — URL만 snow 발급 URL)

## 응답 플래그 (권장)

`POST /testAPI` (및 필요 시 retrieve 메타):

| 필드 | 의미 |
|------|------|
| `snow_token_issued` | 서비스나우 토큰을 이번 호출에서 새로 발급했는지 |
| `apim_token_issued` | APIM 토큰을 이번 호출에서 새로 발급했는지 |
| `token_retried` | 401/403 후 이중 재발급·origin 재시도 여부 |

기존 `token_issued`만 쓸 경우 auth=4에서 의미가 모호하므로 **구분 필드 권장**. 하위 호환을 위해 `token_issued = snow_token_issued or apim_token_issued`로 채워도 된다.

## 에러

권장 (구분 가능):

- `snow_token_failed` — 서비스나우 발급 실패
- `apim_token_failed` — APIM 발급 실패

또는 공통 `token_failed` + detail 메시지에 `snow`/`apim` 구분.

그 외 기존: `invalid_api_auth`, `invalid_api_url`, `invalid_api_method`, `invalid_api_params`, `invalid_api_headers`, `retrieve_failed`.

auth=4에서 `token_api` 또는 `snow_token_api` 누락 → `invalid_api_auth` (또는 400).

## project-A 경계

- A는 위 필드를 UI에서 입력·검증·e로 전달·목록 표시만 한다.
- A는 토큰 캐시·재발급·헤더 부착을 **구현하지 않는다**.
- e 미반영 시 auth=4 retrieve/test는 e가 거부하거나 무시할 수 있다. A UI/프록시는 먼저 맞춰 둔다.

## 변경 대상 엔드포인트 요약

| Method | Path | 변경 |
|--------|------|------|
| POST | `/retrieve` | auth=4, `snow_token_api*` |
| POST | `/testAPI` | 동일 + 응답 플래그 |
| POST | `/testTokenIssue` | 변경 없음 (재사용) |
| POST | `/addInventory` | `origin_snow_token_api*`, auth=4 |
| GET | `/getInventoryList` | snow URL/method + `has_snow_token_api_*` |

## 수락 기준

1. auth=3 회귀 없음 (단일 Bearer 토큰 경로 동일)
2. auth=4로 등록·목록·testAPI·retrieve 시 snow→APIM→origin 헤더 부착
3. params/headers 비밀 비노출·빈 값 유지
4. 401/403 시 이중 재발급 1회만
5. custom header가 `X-Partners-Token`/`Authorization`와 겹치면 400
