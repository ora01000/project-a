# project-A

cursor 에사 사용할 plan 초안을 작성합니다.

1. 프로젝트 환경 구성
  1. /Users/insu/project-A 디렉토리
  2. conda 환경에서 py3_12_edu 사용
2. 프로젝트 목표
  1. lang graph 기반의 멀티 에이전트 개발
3. 주요 인프라
  1. 로컬 LLM endpoint : [http://localhost:8001/v1](http://localhost:8001/v1)
  2. 모델 종류(2개 선택 가능)
    1. ./llm_model/gpt-oss-20b
    2. ./llm_model/qwen3-4b-4bit-mlx
  3. 로컬 mcp 서버
    1. streamable http 로 연동
    2. endpoint 는 나중에 추가함
  4. mcp 서버 종류
    1. kubernetes-mcp-server
    2. kubectl-ai
4. 백엔드 - lang graph 기반
  1. 에이전트
    1. 역할 1. kubernetes 클러스터의 정보 조회 전용 에이전트
    2. 역할 2. kubevirt VM 정보조회 전용 에이전트
    3. 역할 3. vcenter 정보조회 전용 에이전트
5. 프론트엔드
  1. 로컬 9001 포트로 웹서비스
  2. 백엔드에서 정의된 에이전트를 타일 형태로 출력하고 마우스 입력을 통해 타일을 이동, 재배치, 크기 조절 가능
  3. 타일은 기본적으로 에이전트 이름 과 역할을 보여주도록



## Plan update #1

1. kubernetes-mcp-server endpoint 추가
  1. [http://k8smcp.ora01000.pe.kr:32716/mcp](http://k8smcp.ora01000.pe.kr:32716/mcp)
2. kubectl-ai endpoint 추가
  1. [http://kubectl-ai.ora01000.pe.kr:32716/mcp](http://kubectl-ai.ora01000.pe.kr:32716/mcp)



## Plan update #1-1

1. LLM 백엔드 모델 조회 오류에 따른 수정
  1. gpt-oss-20b → ./llm_model/gpt-oss-20b 로 변경
2. 모델을 ./llm_model/qewn3-4b-4bit-mlx 로 변경



## Plan update #1-2

1. 프론트엔드의 각 타일 변경
  1. 세로 크기를 현재 보다 50% 확장
  2. 응답이 출력될 때 자동으로 스크롤 다운(마지막 응답이 보이도록)
  3. 메시지 입력창에서 “위” 버튼을 누르면 이전 메시지가 출력되도록 10개 까지 기록



## Plan update #1-3

1. 프론트엔드의 각 타일 변경
  1. 타일 내 출력 창을 상/하로 분리하여 User가 입력한 메시지는 상단 출력창으로, Assistant 의 답변은 하단 출력창으로 구분
2. 출력 포맷 변경
  1. Assistant 답변에서 plain text 는 그대로 출력하되 마크업 표현이 있을 경우 형식에 맞춰 표현



## Plan update #1-4

1. 프론트엔드의 각 타일 변경
  1. update #1-3 의 1.a 에서 분리한 창의 세로 비율을 1:3 으로 조절
2. 출력 포맷 변경
  1. User 의 메시지 입력시 인덱스를 다음 포멧으로 생성하고 User 메시지 표시창에 함께 출력
    1. #{num}-YY년 MM월 DD일 HH:mm:ss
    2. {num}은 1부터 시작하나, 각 에이전트 독립적으로 각자 카운팅
    3. 인덱스 출력시 폰트 사이즈는 출력 메시지의 폰트보다 작게
  2. Assistant 메시지 출력시 위 생성된 인덱스를 동일한 형태로 표현해서 User 입력과 Assistant 결과를 매칭 가능하도록 표현



## Plan update #1-5

1. 출력 포맷 변경
  1. 인덱스 포맷 변경
    1. YY년 MM월 DD일 HH:mm:ss-#{num} 으로 변경



## Plan update #1-6

1. 에이전트 할당 MCP 변경
  1. Kubernetes Agent
    1. kubernetes-mcp-server
    2. kubectl-ai
  2. KubeVirt Agent
    1. kubernetes-mcp-server
  3. VMware Agent
    1. 나중에 추가함, 변경없음



## Plan update #1-7

1. 프론트 타일의 배치 구조
  1. 타일은 화면의 크기에 따라 능동 배치함
    1. 각 타일의 가로 크기는 250 픽셀을 보장해야 하며 화면을 넘어설 경우 다음 행에 배치
2. 전체 화면의 타이틀 바로 하단에 다음 구조의 메뉴바를 mockup 한다
  1. 메뉴바 구조
    1. 에이전트 관리 | LLM 관리 | 사용자 관리
    2. 메뉴바의 가장 오른쪽에는 현재 시각과 로그인 한 사용자를 보여주며 현재 로그인 기능이 없으므로 다음 이름으로 하드코딩한다.
      1. 윤인수 책임
    3. 로그인 사용자 옆에는 로그아웃 버튼을 배치한다



## Plan update #1-7 보완

1. 프론트 타일의 배치 구조
  1. 타일 가로 크기 변경
    1. 750 픽셀 보장으로 변경
2. 메뉴바 구조 변경
  1. 대시보드 | 에이전트 관리 | LLM 관리 | 사용자 관리 | 환경설정



## 버그 수정 #1

1. Assistant 답변 후 상단의 User 메시지 출력 창의 세로 길이가 대폭 증가합니다. fix 해주세요



## 버그 수정 #2

1. 버그 수정 #1 의 버그가 개선되지 않았습니다. 따라서 User 메시지 출력 창과 Assistant 메시지 출력 창의 세로 길이를 다음과 같이 설정하고자 합니다
  1. User 메시지 출력창 : 세로 길이 100 픽셀 고정
  2. Assistant 메시지 출력창 : 세로 길이 300 픽셀이나 마우스의 드래그를 통해 세로 길이를 최대 600 픽셀까지 늘릴 수 있도록 설정



## 기능 개선 #1

1. Assistant 응답시 어떤 MCP 툴을 사용했는지 표시



## 기능 추가 #1

1. 프론트 화면에서 가장 하단 레이어에 다음 toppology 맵을 추가
  1. 에이전트 노드 표현
  2. LLM 노드 표현
  3. MCP 서버 표현
  4. 에이전트 및 LLM, MCP 호출관계를 라인으로 연결
  5. 호출이 발생할 시 라인의 흐름을 동적으로 표현



## 버그 수정 #3 → 이건 원복함

1. MCP 호출 시 paramter 에 해당하는 부분의 제일 앞에 “ne”라는 문자가 섞여 들어가며 이로 인해 MCP 호출 결과에 오류가 발생
  1. MCP 호출이 없는 일반 User 메시지에 대해서는 해당 현상이 발견되지 않음



## 화면 개선 #1 → 원복

1. topology 맵의 스타일 수정
  1. 전체 컴포넌트의 선 굵기 : 2px
  2. 폰트의 크기 : 10px
2. 노드 스타일 수정
  1. 에이전트, MCP, LLM 노드가 구별될 수 있도록 변경된 스타일 제안
  2. 노드 타일 크기를 앞서 변경된 폰트의 크기에 적합하도록 축소



## 기능 추가 #2

1. 로깅 추가
  1. 로그 위치 : ./logs
  2. 로그 종류
    1. 프론트 로그
      1. access log
    2. 백엔드 로그
      1. 에이전트 별 로그
        1. 입력 메시지
        2. 출력 메시지
        3. 호출된 툴의 종류



## 기능 추가 #3

1. 환경 변수
  1. 각 에이전트가 사용하는 MCP 도구의 endpoint 를 환경변수로 변경
  2. 각 MCP 도구의 활성화 여부 추가



## 기능 추가 #4

1. 에이전트 추가
  1. Ansible 에이전트를 추가
    1. MCP 도구 : ansible
    2. endpoint : 환경변수로 추후 입력할 수 있도록 준비
    3. 활성화 : 환경변수로 설정 가능하도록



## 화면 개선 #2

1. 에이전트 타일의 가로 크기를 500픽셀로 보장하도록 수정



## 기능 추가 #5

1. 환경변수 추가
  1. frontend 와 backend 의 서비스 IP, 서비스 PORT 를 환경변수로 설정
  2. frontend가 backend 호출에 필요한 backend IP / PORT 정보를 환경변수로 설정



## Docker 빌드 #1

1. 빌드시 각 결과물이 다음 이름으로 생성되도록
  1. frontend : ora01000/project-a-frontend:latest
  2. backend: ora01000/project-a-backend:latest
2. 빌드 성공시 docker hub 에 push



## 기능 추가 #6

1. 에이전트 타일의 기능 추가
  1. 에이전트 타일 최상단 오른쪽에 전체화면/원복 토글 버튼을 추가
    1. 전체화면 버튼 클릭시 다른 에이전트 타일과 toppology 맵을 숨긴다
    2. 전체화면 버튼이 눌려진 에이전트 타일은 전체 영역으로 확장한다
    3. 전체화면 상태가 되면 버튼은 원복 버튼으로 변경된다.
    4. 원복 버튼을 누르면 이전 크기와 위치로 돌아가고 숨겨졌던 모든 에이전트 타일과 topology 맵이 다시 보인다



## 기능 추가 #6의 개선

1. 전체화면, 원복시 다음 창의 메시지 내용이 유지
  1. User 메시지 출력창
  2. Assistant 메시지 출력창
2. 전체화면, 원복시 User 메시지와 Assistant 메시지의 이전 출력 내용은 타일의 크기에 맞춰 렌더링을 다시함

---

---

여기까지 수행함 - 260708

## 기능 추가 #6의 개선 #2

1. 에이전트 타일이 전체 화면이 되었을 때 타일 내 컴포넌트의 비율 및 배치 조정
  1. 메시지 입력 창을 타일의 가장 하단에 배치
  2. Assistant 응답 창의 세로 길이는 메시지 입력 창 까지 확장



## UI 구성 변경 #1

1. 오른쪽 패널에 통합 채팅 창을 구현
  1. 통합 채팅 창 규격
    1. 가로 500 픽셀, 세로 : 전체 화면에 맞춰 가변 길이
  2. 통합 채팅 창 영역 및 세부 기능 정의
    1. stack 구조로 패널을 나열
    2. 통합 채팅 타이틀 바 - Assistant 답변 창 - 메시지 입력 창 순으로 배치
    3. 타이틀 바는 세로 길이 고정으로 100 픽셀
      1. 전체화면/원복 토글 버튼
        1. 전체화면 시 에이전트 노드는 숨김 처리하고 통합 채팅 창은 전체 화면으로 전환
        2. 원복 시 숨겨졌던 에이전트 노드가 다시 보이고 채팅창은 이전 크기와 위치로 원복
    4. 메시지 입력창은 세로 길이 고정으로 200 픽셀
      1. 에이전트 선택 박스 추가 - 선택 가능한 에이전트는 현재 등록된 모든 에이전트
      2. 선택한 에이전트로 메시지 전송
      3. “Up Arrow” 키를 누르면 이전에 입력한 메시지를 출력(10개까지 기억)
    5. Assistant 답변 창의 세로 길이는 화면크기에 맞춰 확장
      1. 선택한 에이전트에서 받은 답변을 출력
      2. 답변 출력시 어떤 에이전트에서 출력된 답변인지 구분할 수 있도록 표시
      3. 답변 출력시 어떤 MCP 도구를 사용했는지 표시하고 여러 MCP를 순차적으로 사용할 경우 순서대로 모두 표시
      4. 답변이 출력되는 시각 표시 : YY년 MM월 DD일 HH:mi:ss 형식
        구성 변경 #1-1
  3. 통합 채팅 창
    1. 메시지 입력시 “엔터” 는 전송, “Shift-엔터” 는 입력 창에서 다음줄 로 동작하도록 수정



## UI 구성 변경 #2

1. 에이전트 노드 레이어 변경
  1. 에이전트 노드 패널 추가
    1. 패널 명 : 에이전트 노드 목록
    2. 위치 :전체 화면의 중앙을 전체 화면 비율에 맞춰 확장
    3. 패널은 에이전트 노드의 개수에 따라서 스크롤이 가능하도록
    4. 에이전트 노드가 표시되는 영역에 바로 에이전트 노드를 렌더링 하지 않고 아래 레이어에 패널을 두고 그 위에 에이전트 노드를 표시하도록 변경
2. topology 패널 레이어 변경
  1. topology 패널을 바로 표현하지 않고 아래에 멀티탭으로 구성된 패널을 배치
    1. 패널 명 : 상세 정보
    2. 위치 : 전체 화면의 bottom, 가로는 전체 화면과 동일하며 세로는 500 픽셀이 기본이나 드래그하여 세로를 위로 확장할 수 있음
    3. 멀티탭 메뉴
      1. Topology 맵
        1. 이전의 Topology 맵을 출력
      2. 디버깅 탭
        1. empty



## UI 구성변경 #2-1

1. 상세 정보 패널의 가로 길이를 에이전트 노드 패널의 가로와 동일하게 수정
2. 통합 채팅 패널의 세로 길이를 화면 전체 세로에 맞춰 확장



## UI 구성 변경 #3

1. 에이전트 노드 패널
  1. 왼쪽 정렬
2. 에이전트 노드 타일
  1. 타일 내 다음 요소 삭제
    1. User 메시지 표시 창
    2. Assistant 응답 창
    3. 메시지 입력 창
  2. 전체화면/원복 토글 버튼 삭제
  3. 크기 조정
    1. 기존 750 픽셀 고정 → 500 픽셀 고정으로 변경



# 260709 Chanage plan



## Kubernetes Cluster 에이전트 세분화

- **dprv6-k8s**
  - 명칭 : 구 PaaS 대개체 개발기(6층)
  - 사용도구 : kubernetes, kubectl-ai
- **pcicd-k8s**
  - 명칭 : 빌드팜(6층)
  - 사용도구 : kubernetes, kubectl-ai
- **dprv-k8s**
  - 명칭 : IT공통 개발기
  - 사용도구 : kubernetes, kubectl-ai
- **dprsv-k8s**
  - 명칭 : UCube 서비스/청구/수미납 개발기
  - 사용도구 : kubernetes, kubectl-ai
- **dprmn-k8s**
  - 명칭 : UCube 공통 개발기
  - 사용도구 : kubernetes, kubectl-ai
- **dprrt-k8s**
  - 명칭 : UCube 과금 개발기
  - 사용도구 : kubernetes, kubectl-ai
- **dpvs-k8s**
  - 명칭 : Provisioning 개발기
  - 사용도구 : kubernetes, kubectl-ai
- **dtest-k8s** : 테스트기
  - 명칭 : 테스트 클러스터
  - 사용도구 : kubernetes, kubectl-ai



## 에이전트 표시 정보 추가

- 각 에이전트가 질의하고 응답받는 토큰의 양을 계산하고 에이전트 노드 타일에 표시
- 최대 토큰의 프레임을 기준으로 percentage 정보 표시



## bottom 레이어 디버깅 탭 수정

- 디버깅 탭 -> 로그 탭 으로 변경



## 로그인 기능 구현

- sqlite로 DB 구현
  - DDL 정의
    - table#1 name : users
      - column
        - idx : int, auto increment, primary key
        - userid : varchar(50), unique
        - email : varchar(50)
        - username : varchar(50)
        - password : varchar(50)
        - depart : varchar(100)
        - role : int
  - 초기 데이터
    - users 테이블에 초기 데이터 생성, 초기데이터는 최초 한번만 입력하고, 이후 백엔드 재시작시는 입력하지 안음
      - record #1
        - userid : isyun
        - email : [isyun@lguplus.co.kr](mailto:isyun@lguplus.co.kr)
        - username : 윤인수
        - password : isyun
        - depart : IT플랫폼운영팀
        - role : 0
      - record #2
        - userid : loadan
        - email : [loadan@lguplus.co.kr](mailto:loadan@lguplus.co.kr)
        - username : 안세훈
        - password : loadan
        - depart : IT플랫폼운영팀
        - role : 0
- 로그인 화면
  - 최초 접속시 표시될 로그인 화면 작성
    - 입력 : 아이디 / 패스워드
    - users 테이블에서 조회 후 인증
  - 인증 성공시 대시보드 화면으로 이동
  - Mockup 구성된 메뉴바 오른쪽 로그인 사용자 명을 실제 로그인 한 사용자의 users 테이블 내 아래 컬럼으로 조합하여 표시
    - depart/username
  - Mockup 구성된 로그아웃 버튼에 기능 부여
    - 로그아웃을 할지 확인(confirm) 창을 띄우고 "예" 버튼을 클릭하면 로그아웃 하고 로그인 화면으로 이동
- 사용자 관리 기능
  - 최초 대시보드 화면은 메뉴바의 mockup 으로 제작된 "대시보드" 메뉴와 연동
  - 메뉴바의 mockup 으로 제작된 "사용자 관리" 메뉴에 sub menu 추가
    - sub menu
      - 사용자 조회(sub menu)
        - users 테이블의 데이터를 표로 출력
        - 각 행에는 checkbox 를 두고 선택 가능
        - 조회 화면에는 다음 기능 버튼을 배치
          - 삭제 : users 테이블에서 선택된 레코드를 삭제
          - 수정 : 선택된 레코드의 정보를 수정하는 팝업 창을 로드
          - 추가 : 새로운 사용자를 추가
        - 수정시 숨겨진 레코드(사용자 정보) 수정 페이지가 활성화 된다
        - 수정 팝업창의 수정가능/불가한 정보는 다음과 같다
          - userid : 라벨 -> 아이디, 수정불가
          - email : 라벨 -> 이메일, 수정가능
          - username : 라벨 -> 이름, 수정가능
          - password : 라벨 -> 패스워드, 수정가능, 눈동자 모양의 visible/hidden 토글 버튼 표시
          - depart : 라벨 -> 조직, 수정가능
          - role : 라벨 -> 역할, 수정가능, 0:admin, 1:user
        - 수정 팝업창은 저장 / 닫기 버튼이 있다
          - 저장 : 수정된 데이터로 레코드를 업데이트 한다. 업데이트가 완료되면 수정 팝업창을 닫는다.
          - 닫기 : 수정을 취소하고 수정 팝업창을 닫는다
        - 사용자 추가 버튼 클릭시 새로운 사용자를 추가할 수 있는 팝업창 생성하며 입력값은 아래와 같다
          - userid : 라벨 -> 아이디
          - email : 라벨 -> 이메일
          - username : 라벨 -> 이름
          - password : 라벨 -> 패스워드, 수정가능, 눈동자 모양의 visible/hidden 토글 버튼 표시
          - depart : 라벨 -> 조직
          - role : 라벨 -> 역할, 수정가능, 0:admin, 1:user
        - 사용자 추가 팝업창은 저장 / 닫기 버튼이 있다
          - 저장 : 입력된 데이터로 레코드를 추가 한다. 완료되면 수정 팝업창을 닫는다.
          - 닫기 : 취소하고 사용자 추가 팝업창을 닫는다
      - 에이전트 할당(sub menu)
        - 상세한 구현은 추후 진행



## 에이전트 로그 출력 - 나중에 구현

- 각 에이전트에서 발생하는 트랜잭션의 모든 로그를 로그 탭에 출력
  - 로그 내용
    - 발생 시각
    - 호출을 요청한 에이전트
    - 에이전트 요청 수신
    - 요청 메시지
    - 응답 메시지
    - 성공 여부
    - 호출을 요청할 에이전트
    - 에이전트 호출 성공 여부
  - 로깅 탭에 기록되는 로그는 모두 로그 파일에 동일하게 출력



# 260710 Change Plan



## UI 개선

- 통합채팅 메시지 입력 영역 전송 버튼
  - 전송이 시작되고 응답이 오기 전까지 전송 버튼은 Stop 아이콘 버튼으로 변경되고 응답이 완료되면 다시 전송 버튼으로 변경
  - Stop 아이콘 버튼 클릭시 응답 수신을 cancel 하고 새로운 메시지를 보낼 수 있도록 전송 버튼으로 변경
- 대시보드 하단의 상세 정보 패널에 다음 탭을 추가한다.
  - 검토 작업
  - 보류 작업
  - 완료 작업




## MCP 도구 추가

- kubevirt 추가
  - transport: streamable_http
  - url : [http://k8smcp.ora01000.pe.kr:32716/mcp](http://k8smcp.ora01000.pe.kr:32716/mcp)
  - enabled: true
- Kubevirt 에이전트는 kubevirt mcp 를 사용하도록 변경



## 에이전트 DB

- 에이전트 정보 DB 화
  - DDL
    - 테이블 : agents
    - 컬럼
      - idx : int, auto increment, primary key
      - agent_id : varchar(50)
      - name : varchar(50)
      - role : varchar(200)
      - system_prompt : text
      - mcp_server_keys : varchar(200)
    - 초기 레코드는 현재 구현된 에이전트 정보를 기반으로 insert



## 에이전트 관리 메뉴 구현

- 에이전트 관리 메뉴 
  - agents 테이블 데이터를 기반하여 테이블 출력, 각 레코드 제일 앞에는 checkbox 를 두어 선택된 레코드를 수정할 수 있도록
  - 추가/삭제/수정 버튼
  - 추가
    - 에이전트 추가 팝업창
      - 저장/닫기 버튼
      - 입력값
        - agent_id : 라벨 -> 에이전트 ID, 텍스트
        - name : 라벨 -> Display 이름, 텍스트
        - role : 라벨 -> 에이전트 역할(간략), 텍스트
        - system_prompt : 라벨 -> 에이전트 역할(상세), 멀티라인 텍스트
        - mcp_server_keys : 라벨 -> 사용 도구, settings.yaml 에 정의된 도구를 선택(복수가능)할 수 있도록 하고 입력시 리스트로 저장되도록하며 도구는 선택하지 않을 수 있다.
  - 수정
    - 에이전트 수정 팝업창
      - 체크된 레코드를 수정하는 에이전트 수정 팝업창
      - 저장/닫기 버튼
      - 입력 포맷과 동일
  - 삭제
    - 삭제 버튼 클릭시 확인 팝업창으로 진행을 물어본 후 삭제 확인이 되면 해당 레코드 삭제



## 작업 프로세스 DB

- 작업 프로세스 저장 DB
  - DDL
    - 테이블 : jobs
    - 컬럼
      - idx : int, auto increment, primary key
      - request_date : date
      - job_title : varchar(200)
      - request_depart : varchar(50)
      - requester : varch(50)
      - requester_email : varchar(50)
      - request_date : date
      - job_description : text
      - approver : varchar(50)
      - state : int -> 0:접수, 1:계획수립완료, 2:검토중, 3:보류, 4:반려, 5:승인, 6:완료



## DB agent 테이블 정보에 의존하지 않는 시스템 에이전트 생성

- 다음 시스템 에이전트를 생성한다.
  1. "작업 분석/계획" 에이전트
    - "작업 분석/계획" 에이전트는 DB에 에이전트 정보를 저장하지 않는다.
    - "작업 분석/계획" 에이전트는 다음과 같은 역할을 수행
      - 자연어로 주어진 작업 요청서를 받는다.
        - 요청서는 API를 통해 json 형태로 받는다. 
        - json 포맷에는 다음 내용이 포함되어야 한다.
          - 기안일시
          - 작업 제목
          - 기안자 조직
          - 기안자 이름
          - 기안자 메일주소
          - 작업완료요청일시
          - 작업내용
          - 작업승인자
      - 작업을 접수하고 jobs 테이블에 insert 한다. state 값은 0
      - 작업 요청서를 분석하고 어떤 에이전트와 툴을 사용할지 계획을 수립한다.
      - 작업 계획 수립이 완료되면 state 값을 1 로 업데이트하고 작업승인자에게 전달한다.
        - 전달 방식은 1. 이메일 발송, 2. MS Teams 채널, 3. 통합 채팅창 알림 세 가지 방식을 선택할 수 있다.
          - 1, 2번 방식은 코드 정의만 하고 구현하지 않는다.
          - 3번 방식 구현
            - 로그인 한 사용자가 작업승인자인 경우 통합채팅창에 "작업검토요청" 알림을 보내고 채팅창에 텍스트 레이블 박스로 표현하고 검토/승인/보류/반려 버튼을 옆에 배치한다
            - 검토 버튼을 클릭하면 하단 "상세 정보" 패널의 "검토 작업" 탭에 다음 정보를 표로 출력한다
              - 테이블 출력
              - 컬럼
                - (blank) | 기안일시 | 작업 제목 | 작업완료요청일시 | 기안자 조직 | 기안자 이름 | (blank)
                - 첫번째 (blank) 는 checkbox, 마지막 (blank) 는 다음 버튼을 배치
                  - 상세보기
                - 상세보기 버튼 클릭시 "작업 상세보기" 팝업을 출력
              - 작업 상세보기 팝업        
                - 작업 계획을 출력하고 마지막에 에이전트 호출 계획을 도식으로 출력한다.
                ex) 작업일시 -> dprv-k8s클러스터 -> 호출도구 -> 도구 내 함수(파라메터 정보) -> 작업결과알림
            - 승인 버튼을 누르면 "작업 수행" 에이전트로 작업을 등록한다
            - 보류 버튼은 코드 구조만 만들고 기능은 구현하지 않는다
            - 반려 버튼을 누르면 요청서에 기록된 기안자로 회신한다
              - 회신 방식 : 기안자의 email, MS Teams 채널
              - 이메일, MS Teams 채널 발송은 코드 구조만 개발하고 구현하지 않는다
      - 작업승인자의 승인이 되면 아래 기술할 "작업 수행" 에이전트에 작업을 등록한다.
  2. "작업 수행" 에이전트
    - "작업 분석/설계" 에이전트가 검토하고 승인을 받은 작업을 받아 실제 계획대로 작업을 수행한다.
    - 필요한 에이전트를 호출하고 작업을 수행
    - 작업 수행 후 작업 결과를 작업 승인자와 작업 기안자의 채팅창에 출력한다(users 테이블이 등록된 사용자인 경우). 동시에 다른 알림(이메일, MS Teams 채널)로 발송을 하는 코드 구조는 개발하되 구현하지 않는다.



## 시스템 에이전트 기능 추가

- "작업 분석/계획" 에이전트의 작업 완료 후 작업승인자에게 전달하는 채널
  - MS Teams 채널 전송을 구현한다
    - Teams 전송에 필요한 연동 parameter는 모두 환경변수로 노출한다.
  - 이메일 채널 전송을 구현한다
    - 이메일 전달에 필요한 연동 parameter 모두 환경변수로 노출한다.



## 에이전트 표시 정보 추가 - 변경 #1

- 최대 토큰의 프레임을 기준으로 percentage 정보 표시는 의미가 없으므로 삭제한다.
- 그러나 현재 사용중인 토큰 정보(입/출력)는 현행 유지한다.



## 에이전트 표시 정보 추가 - 변경 #2

- 에이전트 연결 상태 "connected" 신호등 과 동일하게 에이전트 동작 상태 "working" 신호등을 생성
  - 에이전트 working 상태 : 녹색
  - 에이전트 idle 상태 : 노란색
  - 에이전트 내 로직에서 오류를 수신했거나 정상 동작이 어려운 상태 : 빨간색
    - 빨간색인 경우 에이전트 로그에 원인을 기록한다



## 에이전트 로그를 대시보드에 출력

- 에이전트의 모든 로그를 "상세정보" 패널의 "로그" 탭에 출력



## 백앤드에서 LLM, 에이전트, MCP 상태 주기적인 헬스 체크

- LLM, 에이전트, MCP 연결에 대한 헬스체크를 주기적으로 하는지 점검하고 그렇지 않으면 주기적으로 체크하도록 변경
  - 헬스 체크 주기는 기본 30초



## 시스템 에이전트 추가

- **Whatap 알람 수신**
  - 명칭 : Whatap 이벤트 수신
  - 주요기능
    - Whatap(외부시스템)이 발송하는 webhook endpoint
    - json 데이터 수신
    - 이후 처리 로직은 코드 구조만 개발
- **인벤토리**
  - 명칭 : 인벤토리
  - 주요기능 
    - chroma DB 구동
    - 시스템 인벤토리 정보를 저장하는 CSV 파일을 chroma DB 에 임베딩
    - chroma DB 의 데이터 저장 경로는 환경변수로 수정 가능
    - CSV인벤토리 파일의 위치를 환경변수로 수정 가능
    - 질의 내용을 판단하여 chroma DB의 정보를 조회, 출력



## 260714 - UI 개선

- 시스템 에이전트 중 "작업 분석/계획", "작업 수행", "Whatap 알림수신" 은 에이전트 노드 타일로 표시되지 않는데 이유를 파악하고 표시되게 변경
- 통합채팅창에 User 메시지는 출력되지 않는데, 다음과 같이 출력해줘
  - 시각 표시
  - 채팅 창에서 3줄 이상 넘어갈 경우 이후 내용은 User 메시지 블럭을 접어서 생략하여 표시
  - 채팅 내용을 클리시 접혀진 내용이 fold / unfold 되도록 UI 액션 구현
- User 메시지 창과 Assistant 메시지 창이 분리되어 있는데  "대화창" 이라는 이름의 타이틀로 하나로 합치고 User 메시지 블럭과 Assistant 메시지 블럭의 배경 색을 구분
- About 메뉴 추가
  - 상단 메뉴바의 "환경설정" 아래 sub menu "About" 를 추가
  - About 메뉴 클릭시
    - 팝업 창을 출력
    - 표시 내용은 아래와 같다
      - 프로그램 명 : AX 인프라 관리 에이전트 대시보드
      - 버전 정보 : 
      - 빌드 번호 : 
      - 작성자 : IT플랫폼운영팀 윤인수
      - 문의 : [isyun@lguplus.co.kr](mailto:isyun@lguplus.co.kr)
      - **라이선스 및 오픈소스 고지:** 사용 권한, 최종 사용자 라이선스 계약(EULA) 및 프로그램에 사용된 타사 오픈소스 라이선스 목록
    - 버전 정보는 26년 7월 14일 기준 다음 내용을 조합해서 출력
      - 메이저 버전 : 0
      - 마이너 버전 : 1
    - 빌드 번호는 날짜를 기준으로 YYYYMMDD 형식의 8자리 숫자로 조합
- "대화창"의 "작업수행완료" 메시지 에 "해제" 버튼 추가
  - 해제 버튼 클릭시 대화창에서 삭제
- 대화창의 에이전트 선택 박스 수정
  - drop-down 박스 대신 레이블 버튼으로 나열하고 버튼을 눌러 선택할 수 있도록 UI 변경
  - 하나의 에이전트만 선택
- 통합채팅창에서 "대화창" 과 "에이전트" 선택 창의 세로 크기를 마우스로 드래그하여 조절하도록 변경
- 통합채팅창의 assistant 답변이 출력될때 개행 문자가 여러개 들어가는 현상이 있음. 현상을 파악하고 수정안을 제시
- "작업승인요청" 알람 메시지의 "검토", "승인", "보류", "반려" 모든 버튼 클릭시 확인 창을 띄우고 한번 더 확인
- "작업 수행 완료" 알람 메시지의 "해제" 버튼 클릭시 "대화창" 이 자동으로 가장 아래로 스크롤 되는 것을 방지
- "작업승인요청" 알람 메시지의 "검토", "승인", "보류", "반려" 버튼 클릭시 "대화창" 이 자동으로 가장 아래로 스크롤 되는 것을 방지
- "작업승인요청" 알람 메시지의 "승인", "보류", "반려" 가 될 경우 "대화창"에서 삭제
- "테스트 작업 발송" 팝업에서 "발송" 이 성공적으로 완료되면 창을 닫는다
- "작업 수행" 에이전트 작업 실패시 작업승인자 "대화창"에 알람 메시지로 표시한다.
  - 작업 실패 알람 메시지는 "해제", "재작업" 버튼이 있으며 각 버튼 클릭시 확인을 한 후 수행한다.
  - "해제" : 작업 실패 알람 메시지는 삭제한다.
  - "재작업" : "작업 수행" 에이전트에 다시 수행을 요청하고 알람 메시지를 삭제한다.
- Topology Map 노드 배치 변경
  - 폰트의 볼드체 -> Plain 으로 통일
  - 폰트 크기를 모두 2px 씩 축소
  - 시스템 에이전트(인벤토리, Whatap 이벤트 수신, 작업 분석/계획, 작업 수행) 는 맵의 중앙 하단에 가로 1열로 배치
  - 일반 에이전트(Kubernetes, VMWare, KubeVirt) 는 맵의 왼쪽에 세로 2열로 배치
  - 에이전트 노드 타일의 크기를 가로 5px, 세로 2px 축소
  - 일반 에이전트 타일이 개수가 많아 겹쳐서 출력됨. 겹쳐지지 않도록 전체 배치를 수정
  - 중앙 LLM 타일과 왼쪽 일반 에이전트 타일의 위치를 변경
- 대시보드 제목 수정
  - LangGraph Multi-Agent Dashboard --> AX 인프라 운영 콘솔



## 260714 - 테스트 기능 추가

- "작업분석" 계획 에이전트 테스트를 위해 주기적으로 랜덤한 작업 양식을 발송하는 "작업요청자"를 구성한다.
  - "작업요청자"는 에이전트가 아니라 주기적으로 양식을 발송하는 프로그램이다.
  - 작업 양식은 샘플을 제작한다.
    - 10개
    - 모두 READ 작업(변경, 신규 구성 CUD 작업은 제외)
    - Kubernetes Agent, KubeVirt Agent, VMware Agent를 랜덤하게 호출하도록 작업 설계
    - 발송 주기 : 1개/60분
    - 기안조직 : IT플랫폼운영팀
    - 기안자 : 윤인수
    - 작업승인자 : 윤인수 / 안세훈 중 택1
    - 작업 제목에는 "테스트" 임을 명시한다.
    - 샘플은 DB에 넣지 않고 코드에서 관리한다.
  - 샘플을 먼저 제작하고 내용을 검토할 수 있게 출력 후 승인을 받고 적용
- "테스트 작업 발송" 메뉴 추가
  - 상단 메뉴바의 "환경설정" 아래 sub menu "테스트 작업 발송" 추가
  - "테스트 작업 발송" 클릭시
    - 팝업창을 출력
    - 미리 제작된 샘플 작업 요청서 10개 중 한개를 선택하도록
    - 선택된 양식 중 다음 내용은 수정해서 발송 가능하도록
      - 기안조직, 기안자, 작업승인자, 작업제목, 작업요청내용
    - 발송 버튼을 누르면 "작업 분석/계획" 에이전트로 전송한다.
  - 본 기능 추가가 완료되면 기존 "작업요청자" 데몬은 중지한다
- 환경설정 -> 테이블 조회(디버깅) 메뉴 생성
  - 테이블 조회(디버깅) 메뉴는 sqlite 의 모든 테이블을 조회해서 표로 출력한다
  - 테이블 조회(디버깅) 메뉴에서 각 레코드 별로 checkbox를 두고 삭제 버튼을 만든다. 선택된 레코드를 DB에서 삭제한다.



## 260714 - 에이전트 기능 개선

- "작업 수행" 에이전트
  - 작업 결과 내용 보완
    - 실제 에이전트의 답변 내용을 추가한다.
    - 작업 실패 시 실패의 이유를 추가한다.
- "작업 분석/계획" 에이전트
  - 작업 검토시 작업 계획을 "작업승인자"가 수정할 수 있다
    - "작업 계획" 의 각 단락을 삭제하는 (X)버튼, 그 아래 단계를 추가하는 (+) 버튼, 그리고 각 단락은 텍스트를 수정 가능하다
    - "작업 계획" 의 마지막 단락 아래에도 (+) 버튼으로 단계를 추가할 수 있다.
    - 수정된 작업 계획을 "저장", 또는 "원복" 할 수 있으며 원복시 최초 에이전트가 제안한 작업계획으로 돌린다.
    - "저장" 시 "에이전트 호출 계획" 을 새로 그린다.
  - "에이전트 호출 계획"
    - 에이전트가 사용할 도구를 수정할 수 있다. 에이전트가 사용할 도구는 drop-down 박스로 선택할 수 있게 한다
  - 작업 검토 팝업창에 "수정" 버튼을 추가한다. 수정 버튼을 클릭하면 수정 여부를 알럿 창으로 다시 확인하고 최종 확인하면 작업승인자가 수정한 내용으로 작업 계획을 저장한다.
  - job_notifications 테이블이 입력시 동일 작업에 대해 두 건의 레코드가 입력되는 것으로 보인다. target_user가 userid 와 
  - username 두 값에 의해 동일 알람이 두번 insert 되는게 아닌지 확인하고 그럴 경우 target_user는 userid 로만 저장
- 작업 승인 후 "작업 처리에 실패했습니다." 메시지에 대해
  - 위 오류를 해결하기 위해 runJobAction -> POST /api/jobs/{idx}/actions/approve 의 통신 방식을 async로 하는게 나은지 reponse timeout 을 늘리는게 나은지 검토 부탁



## 260714 - 백엔드 인증 프로바이더 추가

- 인증 프로바이더를 두 가지로 구분한다.
  - 환경변수 AUTH_PROVIDER_TYPE 을 추가한다.
    - 값은 db | madang 둘 중 하나이다.
    - 기본 값은 db 로 지정하며 AUTH_PROVIDER_TYPE = db 인 경우 기존 인증 방식을 유지한다.
  - AUTH_PROVIDER_TYPE = madang 인 경우 다음 환경변수 값이 추가로 필요하다
    - OAUTH_PROXY = http://oauth.lguplus-securities.svc.cluster.local:8080
- madang 인증 프로바이더 사용시
  - 로직만 구현한다(테스트 생략)
  - 기존 로그인 창에서 신규 시입기능을 뺀다.
  - ID/PW 를 입력하면 OAUTH_PROXY 를 기반으로 URL을 전송하고 응답 결과를 받아 로그인이 성공하면
    - 1. users 테이블에 ID가 존재하는 경우
      - 인증 성공으로 간주한다.
    - 2. users 테이블에 ID가 존재하지 않는 경우
      - 인증 성공으로 간주다고 users 테이블에 userid insert 한다.
        - role 컬럼 값은 1 이다
      - 사용자 정보 업데이트 폼을 팝업으로 출력한다.
        - userid, role : 수정불가
        - 폼을 통해 입력
        - "저장" 버튼을 누르면 업데이트하고 대시보드 초기화면으로 간다.

## 260715 - UI 개선
- 에이전트 노드 타일
  - 브라우저 화면 크기에 따라 크기가 변함 -> 고정 크기로
- Topology Map
  - 브라우저 화면 크기에 따라 노드의 크기, 텍스트, 라인 굵기 가 변함 -> 고정 크기로
  - Topology Map 캔버스는 가로 : 중앙 정렬, 세로 : 중앙 정렬
  - Topology Map 캔버스에 확대/축소 버튼을 두고 캔버스를 확대하거나 축소하는 기능 구현
- 메뉴 바
  - 환경설정 > 테스트 작업 발송, 환경설정 > 테이블 조회(디버깅) 메뉴는 admin (users 테이블 role 컬럼 : 0) 만 노출
  
- 상세 정보 패널
  - 완료 작업 탭 테이블 컬럼 수정
    - 작업 제목 | 기안 일시 | 기안 조직 | 기안자 | 상태 | 작업완료요청일 | 실제작업완료시간 | 상세보기

## 260715 - 테스트 기능 추가
- 에이전트 프롬프트 디버깅
  - 상세정보 > 디버깅 탭 추가
    - admin role(users 테이블 role 값 0) 만 표시
    - 에이전트(시스템 에이전트, 일반 에이전트 모두) 가 LLM에 질의하는 모든 프롬프트를 대화창 형식으로 표시, 각 프롬프트 질의 시각, 토큰 개수를 표시
    - 에이전트 -> LLM -> 에이전트 로 흐르는 prompt, response 모두 디버깅 탭에 출력해야 하는데 나오지 않습니다.
    - 일반 에이전트의 요청/응답 플로우는 잘 파악할 수 있어, 그런데 시스템 에이전트의 동작(작업 분석/설계, 작업 수행)은 알 수가 없는데 이를 파악할 수 있는 방안이 있을까? 실제로 "작업 분석/설계" 에이전트를 통해 수립된 작업 계획을 "작업 수행" 에이전트가 실행하면 LLM에 과도한 token이 유입되어 오류가 발생함


## 260715 - 작업 분석/계획 에이전트의 개선
- 작업 분석/계획 
  - 스텝 별로 어떤 에이전트를 사용할지만 선택하고 실제 도구의 선택은 사용할 에이전트에 문의하고 답을 받는다.
  - 요청서의 데이터 일부를 수정한다
    - 기안일시에 시분초를 추가한다. (기존 데이터에 없는 경우 00:00:00 처리)
    - 작업요청완료일시에 시분초를 추가한다. (기존 데이터에 없는 경우 00:00:00 처리)
    - 실제작업완료시간 필드를 추가한다. 시분초를 포함한다.



## 260715 - 작업 수행 에이전트 개선
- 작업 수행
  - 작업 수행 에이전트는 자신이 직접 에이전트 또는 도구를 호출하지 않고 도구를 직접 사용하지 않는다. 
  - 작업 분석/계획 에이전트부터 전달받은 계획된 에이전트의 도구만 사용하도록 에이전트를 호출한다. 
  - 호출한 에이전트의 호출 및 도구 수행이 정상이면 결과가 없더라도 다른 시도를 하지 않는다. 결과가 없어도 수행은 정상이다. 

  - 작업수행 에이전트 작업 후 작업 수행이 완료되면 jobs 테이블의 actual_completion_time 필드에 완료 시각을 업데이트한다.

## 260715 - 헬프데스크 에이전트(시스템 에이전트) 추가
- 헬프데스크 에이전트는 모든 사용자에게 노출된다.
  - 헬프데스크 역할
    - 모든 일반 에이전트를 호출 가능, 인벤토리 에이전트 호출 가능
    - 사용자는 헬프데스크를 통해 질의를 할 수 있다 - 통합채팅 -> 에이전트 창에서 선택 가능
    - 헬프데스크는 사용자의 질의에 따라 어떤 에이전트를 사용할지 선택하고, 사용할 에이전트에 질의를 그대로 전달한다(헬프데스크에서 수정/보완/재시도 하지 않는다)
    - 헬프데스크는 호출한 에이전트의 응답을 통합채팅 창을 통해 출력한다(헬프데스크는 에이전트의 답변을 수정/보완 하지 않는다. 단 표, 도식 출력 등 decoration이 필요한 경우 decoration 한다)
    - 통합채팅 -> 에이전트 창에서 최초 default 로 선택된다.

    ROUTING_SYSTEM_PROMPT = (
        "You are the Helpdesk system agent. Select exactly one agent from the provided catalog "
        "to handle the user's question. "
        "Respond with valid JSON only (no markdown) with keys: "
        "agent_id (string), agent_name (string), rationale (string). "
        "Use only agent_id values from the catalog. "
        "Do not answer the user's question yourself."
    )
    - 헬프데스크의 시스템 프롬프트를 다음과 같이 수정
      - You are a help desk system agent. You can select agents from the provided catalog to answer user questions; however, to avoid overcomplicating the thought process, you are limited to using three agents at a time.
      - Respond with valid JSON only (no markdown) with keys: agent_id (string), agent_name (string), rationale (string). 
      - Use only agent_id values from the catalog. 
      - If the inquiry does not concern infrastructure topics such as Kubernetes, VMware, KubeVirt, or Ansible, a direct, general response will be provided.


## 260716 - UI 수정
- 통합 채팅
  - 패널의 가로 비율을 지금보다 30% 정도 확장
- 환경설정 > 테이블조회(디버깅)
  - 레코드의 컬럼 데이터를 수정할 수 있도록 수정 버튼 추가
  - 수정 버튼 클릭시 각 테이블에 맞는 수정 폼을 팝업 출력
  - 업데이트 / 닫기 버튼, 업데이트 성공시 팝업창 close
- 사용자 별 에이전트 할당 기능 구현
  - users 테이블 수정
    - users 테이블에 agents 컬럼 추가 : varchar(200)
  - 사용자 관리 > 애이전트 할당 메뉴의 실제 기능을 구현
    - 에이전트 할당 팝업 출력
    - 에이전트 할당 팝업 레이아웃 구성
      - 저장, 닫기 버튼
      - 왼쪽 패널 : 일반 에이전트 목록을 텍스트 레이블 버튼 형태로 표시
      - 오른쪽 패널 : 사용자 목록 - 테이블
        - 사용자 목록에는 현재 사용자에게 할당된 에이전트가 레이블 버튼을 표시된다. 할당된 에이전트는 users 테이블 agents 컬럼에 agentid 가 sperator(,) 로 구분되어 저장된다.
        - 사용자 목록에는 다음 정보가 포함된다.
          - 조직, 이름, 역할, 할당된 에이전트
      - 왼쪽 패널의 에이전트 레이블 버튼을 마우스 드래그 앤 드랍으로 오른쪽 패널의 사용자 목록에 표시된 사용자에게 할당
      - 왼쪽 패널 에이전트 레이블 버튼 기능 개선
        - 다중 선택이 가능하도록 수정
        - Windows OS 에서는 Ctrl-A, MacOS 에서는 Cmd-A 버튼을 눌렀을 때 에이전트를 모두 선택, 모두 선택된 상태에서 ESC를 누르면 모두 선택 취소
    - 에이전트 관리 메뉴는 users > role 컬럼이 0(admin) 인 경우에만 노출
    - 인벤토리 관리 메뉴는 users > role 컬럼이 0(admin) 인 경우에만 노출
    - 에이전트 할당 메뉴는 users > role 컬럼이 0(admin) 인 경우에만 노출
    - 에이전트 할당 메뉴의 위치를 메뉴바 의 "에이전트" 메뉴의 sub menu 로 이동
- 사용자별 할당 에이전트 적용
  - 현재 통합 채팅 패널의 하단 에이전트 패널에는 모든 일반 에이전트가 표시된다. 이를 users > agents 컬럼에 지정된 에이전트만 표시한다. 따라서 로그인 한 사용자는 자신에게 할당된 에이전트만 선택해서 대화할 수 있다.
  - 현재 대시보드의 에이전트 노드 목록에는 모든 일반 에이전트가 표시된다. 이를 users > agents 컬럼에 지정된 에이전트만 표시한다. 따라서 로그인 한 사용자는 자신에게 할당된 에이전트만 에이전트 노드 목록에서 볼수 있다.
    - 수정 : 시스템 에이전트는 에이전트 노드 목록에서 모든 사용자에게 기본으로 보여준다.
- Release Note 작성
  - 현재까지 개발된 변경 이력을 RELEASE.md 마크다운으로 저장
    - 변경된 날짜, 변경된 기능 에 대한 요약 정리
    - 변경 이력은 26년 7월 8일(최초 개발) 이후부터 찾을 수 있으면 그렇게 하고, 정보가 없을 경우 찾을 수 있는 시점부터 정리
- 환경설정 > 변경이력 sub menu 추가
  - 변경이력 메뉴는 팝업을 띄우고 RELEASE.md 파일을 출력한다

# 메이저 버전 : 0, 마이너 버전 : 2 ,릴리즈 버전 : 260716 에 대한 변경 사항 기록
- 에이전트 할당 메뉴 기능 수정
  - 왼쪽 패널 에이전트 레이블 버튼 기능 개선
    - 다중 선택이 가능하도록 수정
    - Windows OS 에서는 Ctrl-A, MacOS 에서는 Cmd-A 버튼을 눌렀을 때 에이전트를 모두 선택, 모두 선택된 상태에서 ESC를 누르면 모두 선택 취소
    - 에이전트 할당 메뉴 > 왼쪽 에이전트 레이블 버튼 패널에서 ESC 버튼 클릭시 하나라도 선택된 에이전트 레이블 버튼이 있다면 모두 선택 취소 되도록 기능 개선

- 로그인 페이지
  - 로그인 페이지에서 패스워드 입력창 오른쪽에 눈동자 모양의 visible/hidden 토글 버튼 표시

- users 테이블에 최근 로그인 시각 기록, 로그인 시 welcome back 페이지
  - users > last_login : date 컬럼 추가
  - 로그인 시 마지막 로그인 시각을 기록 
  - last_login 이 null 아 아닌 경우 Welcome back 메시지를 팝업창으로 출력
  - Welcome back 팝업창에는 환영 메시지 아래 추가로 다음 내용을 출력한다.
    - 로그인 사용자가 승인자로 지정된 작업과 작업 진행 상태

- front 로그인 세션 타임아웃 구현
  - 로그인 세션 타임아웃을 구현한다.
    - 세션 유지시간 : 1시간
    - 타임아웃되면 로그아웃으로 간주하고 로그인 페이지로 돌아간다.

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push

- 인벤토리 에이전트 기능 개선
  - 실제 서버 환경에서 인벤토리 파일 업로드 시 "인벤토리 업로드에 실패했습니다" 라는 오류가 발생, 원인 분석 또는 가능성 제시
  - 1M 이하의 파일은 업로드가 잘 됩니다. 업로드 파일의 크기를 최대 100MB 까지 가능하도록 설정을 변경하고 "인벤토리 추가" 팝업창에서 100MB 까지 업로드 할 수 있음을 명시하고, 업로드 파일이 선택하였을 때 100MB 초과시 알럿 메시지를 표시하고 업로드가 되지 않도록 업로드 버튼 비활성화

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push

- 인벤토리 에이전트 기능 개선
  - 실제 서버 환경에서 업로드된 인벤토리 파일을 embedding 시 "Embedding에 실패했습니다" 라는 메시지가 발생함. 해당 오류가 발생할 수 있는 가능성을 제시하고 백엔드에서 해당 오류가 발생시 원인을 파악할 수 있도록 stdout 으로 로깅

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push
  
  - RuntimeError: ChromaDB add failed: ValueError: Batch size of 5713 is grater than max batch size of 5461

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push
  - 현재 응용 구조에서 여러 csv 파일을 chromadb 에 임베딩하면 마지막 파일만 적용되는가?
  - 백엔드 재시작시 자동으로 입력되는 "샘플 인벤토리"는 이제 백엔드 재시작시 입력되지 않도록 변경

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push

  - 인벤토리 추가에서 check overlap 값을 입력 받도록 추가, inventory 테이블에도 컬럼 추가, 기본 값은 50으로 지정
  - embedding 시 chunk overlap 값을 적용

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push

  - 인벤토리 추가에서 n_results 값을 입력 받도록 추가, inventory 테이블에도 컬럼 추가, 기본 값은 100으로 지정
  - inventory 테이블에 명시된 파일을 chromadb 에서 조회시 설정된 n_results 값으로 검색하도록 지정

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push
  - 인벤토리 추가의 기능을 다음과 같이 변경한다.
    - inventory 테이블에 db_type 을 추가한다 -> varchar(10) : 값은 table | vector
    - 값이 없는 경우(이미 존재하는 레코드의 경우)에는 null 값이므로 vector db로 간주한다.
    - 인벤토리 추가 폼에서 제일 앞에 db_type을 선택하는 입력 폼을 추가한다. table, vector 둘 중 선택한다.
    - vector 를 선택한 경우 기존 방식을 유지한다.
    - table 방식을 선택한 경우
      - chunk_type, chunk_size, n_results 는 입력받지 않는다.
      - embedding 버튼은 disable 된다.
      - 업로드 버튼을 누르면 다음과 같이 동작하고 완료한다.
        - csv 파일 정보를 토대로 sqlite DB에 동적으로 테이블을 생성한다.
          - 테이블 명은 업로드 된 파일 명의 확장자를 제외한 부분이다.
          - 헤더를 읽어 테이블 컬럼으로 사용한다.
          - 각 데이터 타입은 모두 varchar(100)으로 고정한다.
          - 이후 row 별로 insert 한다
  - 인벤토리 에이전트에서 db_type 이 table 타입의 csv를 조회하는 방안
    1. 조회를 요구하는 User 메시지를 받으면 인벤토리 에이전트는 등록된 table 타입의 csv의 테이블 스키마를 기반으로 LLM에 SQL 문 작성을 문의한다.
    2. 응답받은 SQL 문을 수행하고 쿼리 결과를 응답한다.
    3. LLM 에 쿼리 작성을 문의할 때 문자열 검색시 반드시 질의하는 parameter를 포함하여 검색하도록 질의한다.
    4. LLM 에 쿼리 작성을 문의할 때 반드시 SELECT ALL 을 하지 않고 자원의 중요 정보(ex. hostname, ip, OS 등)를 표시하는 컬럼으로 조회하고, 조건문에서 비교하는 컬럼을 추가로 조회하도록 10개의 컬럼을 선별하도록 질의하도록 쿼리 작성을 유도한다.

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push

  - 통합 채팅 이 길어지는 경우 랜더링이 느려짐
    - 현재 통합채팅에 출력되는 텍스트는 파일 로그에서 읽어와서 뿌려주는 구조인가?
    - 통합채팅의 대화내용 렌더링을 가장 최근 10개의 대화(질의/응답) 으로 제한 가능한가? 

- front, backend 모두 도커 빌드, tag : 260716-2, 성공 시 push

# 메이저 버전 : 0, 마이너 버전 : 3, 릴리즈 버전 : 260718 에 대한 변경 사항 기록
## Kubernetes 에이전트의 주기적인 정보수집
- Kubernetes 에이전트는 각 에이전트가 관리하는 클러스터의 정보를 주기적으로 수집 저장하기 위해 우선 테이블을 아래와 같이 생성한다.
  - 저장 테이블
    - 테이블#1 명 : k8s_nodes
      - 컬럼
        - idx : int, auto increment, pk
        - cluster_id : varchar(50) : 각 에이전트 관리 클러스터 명 -> int 로 변경, k8s_cluster > idx 값으로 대체
        - node_name : varchar(50)
        - node_cpu : int
        - node_mem : int
        - node_os : varchar(50)
        - node_k8s_ver : varchar(50)
    - 테이블#2 명 : k8s_namespaces
      - 컬럼
        - idx : int, auto increment, pk
        - cluster_id : varchar(50) : 각 에이전트 관리 클러스터 명 -> int 로 변경, k8s_cluster > idx 값으로 대체
        - namespace : varchar(50)
        - okd_display_name : varchar(100)
        - resource_quota_cpu_limit : float, 개 단위로 환산
        - resource_quota_mem_limit : int, Gi 단위로 환산
        - resource_quota_pod_limit : int
        - okd_egressip1 : varchar(20)
        - okd_egressip2 : varchar(20)
    - 테이블#3 명 : k8s_deployments
      - 컬럼
        - idx : int, auto increment, pk
        - cluster_id : varchar(50) : 각 에이전트 관리 클러스터 명 -> int 로 변경, k8s_cluster > idx 값으로 대체
        - namespace_id : int -> k8s_namespaces : idx 컬럼 값
        - name : varchar(50)
        - type : varchar(20), deployment | statusfulset | deploymentconfig | daemonset 중 1
        - replicas : int
        - resource_cpu_request : float, 개 단위로 환산
        - resource_mem_request : int, Gi 단위로 환산
        - resource_cpu_limit : float, 개 단위로 환산
        - resource_mem_limit : int, Gi 단위로 환산
        - containers_cnt : int
        - containers_name : varchar(300) -> json list 
        - containers_image : varchar(500) -> json list
    - 테이블#4 명 : k8s_pvcs
      - 컬럼
        - idx : int, auto increment, pk
        - cluster_id : varchar(50) : 각 에이전트 관리 클러스터 명 -> int 로 변경, k8s_cluster > idx 값으로 대체
        - namespace_id : int -> k8s_namespaces : idx 컬럼 값
        - deployment_id : int -> k8s_deployments : idx 컬럼 값
        - name : varchar(50)
        - storage_class : varchar(20)
        - capacity : int. Gi 단위로 환산
        - used : int, Gi 단위로 환산
        - access_mode : varchar(20)
    - 테이블#5 명 : k8s_pods
      - 컬럼
        - idx : int, auto increment, pk
        - cluster_id : varchar(50) : 각 에이전트 관리 클러스터 명 -> int 로 변경, k8s_cluster > idx 값으로 대체
        - namespace_id : int -> k8s_namespaces : idx 컬럼 값
        - deployment_id : int -> k8s_deployments : idx 컬럼 값
        - name : varchar(50)
        - scheduled_node : int -> k8s_nodes : idx 컬럼 값
  - Kubernetes 에이전트 동작
    - 데이터 수집은 openshift, k8s client 라이브러리를 사용하려고 한다. 사용 가능한 라이브러리를 제안
      - openshift 라이브러리로 선택하고 수집 방식은 비동기 통신은 사용하지 않는다.
      - 로컬 테스트의 경우 ocp/okd 가 아닌 일반 kubernetes(orbstack)으로 ocp/okd 용 커스텀api(ex. DeployemtnConfig, egressIPs 등) 수집하고자 하는 object가 없으므로, 값이 없는 경우 이를 무시하고 동작하도록 구성
        - authentication은 MCP 가 사용하는 kubeconfig 를 그대로 사용할 예정이므로 kubeconfig 가 제공된다고 가정한다.

      - 각 에이전트는 1분 주기로 데이터를 수집, 업데이트한다.
  - 저장 테이블 추가
    - 테이블#6 명 : k8s_cluster
      - 컬럼
        - idx : int, auto increment, pk
        - cluster_name : varchar(50)
        - last_update : date
      - 테이블#6을 추가하고 다음 테이블의 컬럼을 변경, 실제 데이터를 cluster 이름에서 k8s_cluster 테이블의 idx 값으로 변경한다.
        - k8s_nodes > cluster_id varchar -> int
        - k8s_namespaces > cluster_id varchar -> int
        - k8s_deployments > cluster_id varchar -> int
        - k8s_pvcs > cluster_id varchar -> int
        - k8s_pods > cluster_id varchar -> int

    - 각 Kubernetes 에이전트의 클러스터 정보 수집 주기 변경
      - 백엔드 기동시 최초 수집, 업데이트 하고 이후 00:10:00 부터 수집을 시작한다.
      - 모든 Kubernetes 에이전트가 한꺼번에 수집할 경우 부하가 있을 수 있으므로, 에이전트의 등록 순서대로 5분의 간격을 둔다.
        - ex. dprv6-k8s -> 00:10:00 시작, pcicd-k8s -> 00:15:00 시작
      - 수집이 완료되면 k8s_cluster > last_update (시각)을 업데이트한다.


- Release Note 작성
  - 현재까지 개발된 변경 이력을 RELEASE.md 마크다운으로 저장
    - 변경된 날짜, 변경된 기능 에 대한 요약 정리
    - 변경 이력은 26년 7월 8일(최초 개발) 이후부터 찾을 수 있으면 그렇게 하고, 정보가 없을 경우 찾을 수 있는 시점부터 정리
- About 메뉴 정보 수정
  - 메이저 버전 : 0, 마이너 버전 : 3, 릴리즈 버전 : 260718 로 about 정보 수정

## LLM 관리 메뉴 삭제 
- LLM 관리 메뉴는 삭제한다.

## 작업관리 메뉴 추가
- jobs 테이블의 입력 값 변경
  - requester, approver 에 username 이 이력되는데 userid 가 입력되도록 변경
  - jobs 테이블 컬럼 추가
    - sr_num : varchar(20) -> "SR" + {request_date 를 YYYYMMDD 포맷으로} + "_" + {idx 컬럼 값을 5자리로 masking} -> ex) SR20260717_00001
    - 이미 존재하는 레코드에 대해서는 request_date 와 idx 값을 바탕으로 작성후 update
    - SR 번호의 마지막 5자리는 고정이야, 그래서 만약 idx 가 100000(6자리) 이상인 경우는 다시 00001로 rotate 되도록 변경
  - "작업 분석/계획" 에이전트가 jobs 에 최초 입력시(작업 접수 시) 위 포맷으로 자동 입력하고, 향후 사람이 식별할 수 있는 작업의 SR(service request) 번호로 활용


- 메뉴바 에이전트, 사용자 관리 사이에 "작업관리" 메뉴를 추가한다.
  - 다음 sub menu 를 생성
    - 작업 목록
    - 작업 생성
  - "작업 목록" sub menu
    - jobs 테이블을 표로 출력한다.
      - 로그인 한 사용자 role 이 0:admin 인 경우 모두 출력한다.
      - 그 외에는 로그인 한 사용자가 기안자 이거나 승인자 인 경우에만 출력한다.
    - state(0:접수, 1:계획수립완료, 2:검토중, 3:보류, 4:반려, 5:승인, 6:완료) 상태 별로 분리하여 표를 출력한다.
    - 표 출력시 requester, approver 의 값을 users 테이블에서 userid 에 해당하는 username 으로 출력

## UI 개선
- Webcome back 팝업
  - 로그인 시 welcome back 팝업창의 가로/세로 길이를 현재 대비 2배 확대한다.
    - 출력할 작업 목록의 컬럼을 변경한다.
      - sr_num 을 제일 앞에 추가

- 에이전트 관리 화면
  - idx 컬럼은 표에 노출하지 않는다.
  - 역할(상세) 는 멀티라인으로 출력해서 모든 내용을 출력하도록 변경한다.
  - 사용도구는 텍스트 레이블 버튼 형식으로 표현한다.

- 인벤토리 CSV 화면
  - idx 컬럼은 표에 노출하지 않는다.
  - 표의 헤더를 수정한다.
    - db_type -> 문서DB 형태
    - chunk type -> 청크 형태
    - chunk size -> 청킹 크기
    - chunk overlap -> 청크 오버랩
    - n_results -> NResult 값
    - modified -> 임베딩 필요 여부

- 사용자 정보 -> users 테이블
  - users > band : int 컬럼 추가 -> 1 : 사원, 2 : 선임, 3 : 책임
  - 사용자 추가, 수정 팝업, 개인정보 수정 팝업에서 band 를 입력/수정하도록 변경
  - 대시보드 메뉴바의 오른쪽 현재 로그인 사용자 정보에서도 이름 뒤에 band 값에 따라 다음 직책명을 출력
    - 1 : 사원
    - 2 : 선임
    - 3 : 책임
  - 사용자 조회 화면에서 idx 컬럼은 노출하지 않는다.
  - 사용자 조회 화면에서 band 컬럼(헤더명 : 직책) 을 추가한다. 추가 위치는 이름 컬럼 다음이다
  - Welcome back 페이지에서 header 타이틀 부분의 문구를 다음과 같이 수정
    - "Welcom back, {username} {band} 님"
    - "이전 로그인" -> "최근 로그인", 오른쪽 정렬

- 공지사항 메뉴 추가
  - 메뉴 바 제일 끝에 공지사항 메뉴 추가
  - 테이블 추가 : 테이블명 : notice_board
    - 컬럼
      - idx int, auto increment, pk
      - writer varchar(50) : users > userid 컬럼
      - write_date : date
      - from_date : date
      - until_date : date
      - title : varchar(100)
      - notice : text
      - welcome_popup : boolean
  - 공지사항 메뉴
    - notice_board 테이블 조회 화면
      - table colume : 표 header
        - idx : 글번호
        - title : 제목
        - writer : 작성자
        - write_date : 작성일시
        - from : 공지시작
        - until : 공지기한
        - welcome_popup : 웰컴백 팝업 표시여부
      - welcome_popup 에 대한 값은 turn on/off 스위치 로 표현한다.
      - 표의 마지막 컬럼에 수정 버튼 추가 - 수정 버튼의 노출은 users > role = 0(admin) 인 사용자만 표시됨
      - 표의 처음 컬럼에 checkbox 표시 - 선택된 레코드에 대한 삭제 버튼을 표 의 우상단에 추가
  - 공지사항 추가
    - 공지사항 -> 추가 버튼 클릭시 팝업에 대한 수정
      - 작성일시는 입력(insert) 시점의 date를 백엔드에서 넣도록 하고 UI에서는 입력받지 않는다.
      - 작성자(userid) : 레이블을 "작성자" 로 변경. 작성자는 로그인한 사용자이다. 따라서 수정불가 하도록하고 users > username 으로 표시
      - 공지시작 : 시분초가 포함되어야 한다. 시분초도 입력받도록 수정, 시분초는 default "00:00:00" 
      - 공지기한 : 시분초가 포함되어야 한다. 시분초도 입력받도록 수정, 시분초는 default "00:00:00"
      - 공지 내용은 markup 텍스트를 입력/처리할 수 있도록 한다.
      - 공지기한은 공지시작일로 부터 1주일 뒤를 default로 표시
    - notice_board 테이블 조회 화면
      - 다음 컬럼을 표에 추가해 주세요
        - writer : 작성자, "제목" 헤더 다음에 위치
      - 레코드의 from_date, until_date 에 대해
        - 현재 시각이 from_date 보다 이전인 경우 -> 공지예정인 글로 "수정" 컬럼의 수정 버튼 옆에 텍스트 레이블 버튼으로 "공지예정" 이라고 표시, 버튼은 동작없음
        - 현재 시각이 until_date 보다 이후인 경우 -> 만료 글로 "수정" 컬럼의 수정 버튼 옆에 텍스트 레이블 버튼으로 "만료" 라고 표시, 버튼은 동작없음

  - Welcomeback 창에 공지사항 내용 출력
    - 다음 조건에 부합하는 notice_board 의 게시물을 표시
      - notice_board > welcome_popup 이 true
      - notice_board > from_date, untile_date 사이의 date 에 로그인 한 경우
    - welcomeback popup 에서 공지사항 패널의 위치
      - 작업 목록 상단에 패널을 위치한다
      - 표시 내용은 다음과 같다.
        - 작성자
        - 제목
        - 공지시작 ~ 공지기한
        - notice text를 markup 하여 표시
      - 제목은 폰트를 3px 키우고 텍스트 블럭 처리, 배경색을 변경
      - 제목 텍스트의 블럭은 가로 길이를 공지사항 패널의 가로길이(100%)로 설정

- 에이전트 타일 표시내용
  - 에이전트 동작 : working 일때 어떤 동작을 하는지 토큰 사용량 옆에 간략하게 표시할 수 있을까?


- 권한 수정
  - users > role 이 1 인 사용자는 "사용자 조회" 메뉴에서 사용자 정보의 수정/추가/삭제 를 할 수 없다
  

# 메이저 버전 : 0, 마이너 버전 : 3, 릴리즈 버전 : 260720 에 대한 변경 사항 기록
## 관리자 메뉴 수정
- 환경설정 > 관리자 작업 생성
  - 관리자 작업 메뉴는 users > role 이 0 인 사용자만 노출
  - 테스트 작업 발송, 테이블 조회(디버깅) -> 관리자 작업 으로 이동
  - 관리자 작업 > 인프라 정보 수집 메뉴 추가
    - 인프라 정보 수집 메뉴는 다음 팝업을 생성
      - 일반 Kubernetes 에이전트 k8s_collector 를 수동으로 수집 명령을 내릴 수 있도록 한다.
      - 일반 Kubernetes 에이전트를 표로 출력하고 마지막에 수집 버튼을 둔다.
      - 이 기능이 활성화 되면 기존 기능을 다음과 같이 수정한다.
        - 백엔드 기동시 k8s_collector 를 작동하지 않는다.
        - 스케줄 된 k8s_collector 작업은 향후 변경이 있을때 까지 중지한다.

## 인벤토리 에이전트 기본 참조 테이블 추가
- 인벤토리 에이전트는 inventory 테이블에 없는 다음 기본 테이블을 모두 참조할 수 있다.
  - k8s_cluster
  - k8s_namespaces
  - k8s_deployments
  - k8s_nodes
  - k8s_pods
  - k8s_pvcs

## k8s_collector
- 지정된 k8s 클러스터의 정보를 수집시 kubeconfig는 다음 정보를 사용한다.
  - /etc/k8s-kubeconfig/k8s-kubeconfig
  - 로컬 테스트 환경에는 이 파일이 없다. 따라서 이 파일이 없을시에는 로컬 kubernetes 접속으로 간주한다.

## 대시보드 각 컴포넌트 연결상태 표시 변경
- API, LLM, MCP Kubernetes, MCP kubectl_ai, MCP Kubevirt, MCP vcenter, MCP ansible 의 연결상태를 다음과 같이 표현을 변경한다
  - 각 컴포넌트를 텍스트 레이블 버튼으로 표현
  - 연결상태를 버튼의 색상으로 표현

## 상세정보 > 디버깅 탭
- 디버깅 탭에서 각 에이전트 별로 선택해서 디버깅 로그를 볼 수 있도록 필터링을 추가한다.
  - 필터 : 전체 | 각 에이전트... | 시스템 에이전트...
  - 텍스트 레이블 버튼으로 표시
  - 선택시 해당 에이전트의 디버깅 로그만 출력
  - default : 전체 선택

## User 메시지 입력창 세로 크기 고정
- 오른쪽 통합 채팅 창의 하단 패널을 구성하는 에이전트 목록과 User 메시지 입력창은 세로 길이를 scale 할 수 있다. 이 때 User 메시지 창은 하단에 고정된 상태로 세로 길이를 고정한다. 100px 로 고정(마우스 드래그를 통해 세로 scale이 조정되는 영역은 에이전트 목록만 해당한다)


# 메이저 버전 : 0, 마이너 버전 : 3, 릴리즈 버전 : 260722 에 대한 변경 사항 기록
## docs 정리
- backend  <->  agent 간 인터페이스를 문서로 정리 

## 에이전트 토큰 계산기
- 개선
  Phase 1 — LLM 훅 연결 + chat.py 중복 제거 (1~2파일 핵심, 효과 큼) 
  Phase 2 — tool consult 귀속 정책 결정
  Phase 3 — UI 라벨·리셋
  Phase 4 — tokenizer·영속화
- 토큰 관리 기능 추가
  - 에이전트 > 토큰관리 메뉴 추가
  - 토큰관리 메뉴는 모든 에이전트의 토큰 사용량을 표로 출력하고, 각 에이전트 별로 reset 할 수 있다

## 작업알람 발송시각 추가
- 통합채팅창에 출력되는 작업 관련 알람창에 알람이 발송된 시각을 표시한다.
  - 작업검토요청 알람 : request_date 를 표시
  - 작업수행완료 알람 : actual_completion_time 을 표시
  - jobs 테이블에 다음 컬럼 추가
    - approval_date : date
    - pending_date : date
    - reject_date : date
    - status 가 5(승인) 될 때 approval_date 업데이트
    - status 가 3(보류) 될 때 pending_date 업데이트
    - status 가 4(반려) 될 때 reject_date 업데이트

# 메이저 버전 : 0, 마이너 버전 : 3, 릴리즈 버전 : 260723 에 대한 변경 사항 기록
## 표시시각 타임존 정의
- 로컬에서는 발생하지 않으나 실제 서버에서는 타임존이 맞지 않아 타임존을 Asia/Seoul 로 고정한다. 

## commit, 도커 빌드 후 푸시
- 현재까지 수정사항을 dev 브랜치에 commit/push 한다.
- 프론트/백엔드 도커 빌드 수행후 260723-1 태깅, 푸시

## 인벤토리 에이전트 사용 전 문의
- 일반 에이전트에서 인벤토리 에이전트를 호출하기 전에 통합채팅창 알럿을 통해 인벤토리 에이전트를 호출할지 물어본다. 
- 사용자가 승인을 하면 진행, 거부할 경우는 인벤토리 호출 없이 지금까지의 결과로만 응답한다.
- 단 시스템 에이전트는 해당 없다.
- 인벤토리 호출 확인 알럿 창이 다른 알럿과 동일하게 채팅창의 상단에 표시되어 확인이 어렵다. 인벤토리 호출 확인 알럿의 경우 채팅창의 가장 아래에 붙여서 출력가능한가?
- 인벤토리 호출 확인 알럿의 승인/거부 버튼을 클릭시 한번 더 확인을 하는데 확인 절차는 삭제한다.


프론트/백엔드 모두 도커 빌드, 동일 태그로 푸시

문의) backend /api/jobs 로 팀즈 채널에서 전송시 json 포맷

## 테스트 코드 추가
- 백엔드에 teams 채널에서 power automate 를 통해 전송하는 메시지를 그대로 받아 출력하는 디버깅용 엔드포인트와 코드를 작성한다.
- POST 로 전송하며 전송받은 메시지를 그대로 출력한다.
- 메시지 출력은 Popup 으로 보여준다

## Power Automate 전송 포맷을 참고하여 수신 처리
- 전송 json : power_automate_format.json
- key mapping
  - job_title.createdDateTime -> request_date
  - job_title.subject -> job_title
  - webUrl
  - from.user.displayName
  - body.contentType
  - body.content
  - channelIdentity.teamId
  - channelIdentity.channelId
  - attachments
  - mentions






