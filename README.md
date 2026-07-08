# LangGraph Multi-Agent Platform

LangGraph 기반 멀티 에이전트 플랫폼입니다. Kubernetes, KubeVirt, vCenter 정보 조회 전용 에이전트를 타일 대시보드에서 독립적으로 사용할 수 있습니다.

## 아키텍처

- **Backend (8080)**: FastAPI + LangGraph ReAct agents
- **Frontend (9001)**: React + react-grid-layout 타일 대시보드
- **LLM**: OpenAI 호환 API (`http://localhost:8001/v1`)
- **MCP**: streamable HTTP transport

## 사전 요구사항

- conda 환경 `py3_12_edu` (Python 3.12)
- [uv](https://docs.astral.sh/uv/)
- Node.js 18+
- 로컬 LLM 서버 (OpenAI 호환)
- (선택) MCP 서버: kubernetes-mcp-server, kubectl-ai

## 설치

```bash
conda activate py3_12_edu
cd /Users/insu/project-A
uv sync

cd frontend
npm install
```

## 설정

### LLM / 서버 설정

[`config/settings.yaml`](config/settings.yaml) 또는 `.env`:

```yaml
llm:
  base_url: "http://localhost:8001/v1"
  model: "./llm_model/qwen3-4b-4bit-mlx"   # 또는 ./llm_model/gpt-oss-20b
```

모델 경로 참조:

- `./llm_model/gpt-oss-20b`
- `./llm_model/qwen3-4b-4bit-mlx`

### MCP 서버 설정

[`config/mcp_servers.yaml`](config/mcp_servers.yaml):

```yaml
servers:
  kubernetes:
    url: "http://k8smcp.ora01000.pe.kr:32716/mcp"
    enabled: true
  kubectl_ai:
    url: "http://kubectl-ai.ora01000.pe.kr:32716/mcp"
    enabled: true
  vcenter:
    url: "http://localhost:9090/mcp"
    enabled: false   # endpoint 추가 후 true로 변경
```

## 실행

```bash
# 1. 로컬 LLM (별도 터미널)
# http://localhost:8001/v1

# 2. MCP 서버 (원격 endpoint 사용 중)
# kubernetes: http://k8smcp.ora01000.pe.kr:32716/mcp
# kubectl-ai: http://kubectl-ai.ora01000.pe.kr:32716/mcp

# 3. 백엔드
conda activate py3_12_edu
cd /Users/insu/project-A
uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 --reload

# 4. 프론트엔드
cd /Users/insu/project-A/frontend
npm run dev
```

브라우저: http://localhost:9001

## API

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/agents` | 에이전트 목록 |
| GET | `/api/health` | LLM/MCP 연결 상태 |
| POST | `/api/agents/{id}/chat` | 에이전트 채팅 (SSE) |

에이전트 ID: `k8s`, `kubevirt`, `vcenter`

## 에이전트 역할

| 에이전트 | MCP | 역할 |
|---------|-----|------|
| Kubernetes Cluster Agent | kubernetes-mcp-server, kubectl-ai | K8s 클러스터 리소스 조회 |
| KubeVirt VM Agent | kubernetes-mcp-server | KubeVirt VM/VMI 조회 |
| VMware Agent | vcenter (placeholder) | VMware vCenter 인벤토리 조회 |

VMware MCP가 비활성화(`enabled: false`)일 때는 안내 메시지를 반환합니다.

## 프론트엔드 기능

- 에이전트 타일 드래그 이동 / 크기 조절
- 타일 레이아웃 localStorage 저장
- 타일별 독립 채팅
- LLM/MCP 연결 상태 표시

## 모델 요구사항

ReAct agent는 tool calling을 지원하는 모델을 권장합니다. tool calling 미지원 모델은 제한적으로 동작할 수 있습니다.
