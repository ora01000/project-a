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

## 에이전트 로그 출력
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


## Staff 역할 에이전트 추가
- **Whatap**
    - 명칭 : Whatap 이벤트 수신 에이전트
    - 주요기능
        - Whatap(외부시스템)이 발송하는 webhook json 데이터를 수신하는 채널
        - json 데이터 수신 후 추가 처리 로직이 구현될 때까지 로그로 출력
- **시스템정보**
    - 명칭 : 인벤토리 에이전트
    - 주요기능 :
        - chroma DB 구동
        - 지정된 CSV 파일을 chroma DB 에 임베딩
        - 임베딩 모델은 gpt-oss-120b와 호환 가능한 모델로 추천
        - chroma DB 의 데이터 저장 경로는 환경변수로 수정 가능
        - 질의 내용을 판단하여 chroma DB의 정보를 조회, 출력

## 로그인 기능 구현
- hsql로 DB 구현
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
        - users 테이블에 초기 데이터 생성
            - record #1
                - userid : isyun
                - email : isyun@lguplus.co.kr
                - username : 윤인수
                - password : isyun
                - depart : IT플랫폼운영팀
                - role : 0
            - record #2
                - userid : loadan
                - email : loadan@lguplus.co.kr
                - username : 안세훈
                - password : loadan
                - depart : IT플랫폼운영팀
                - role : 0

- frontend 최초 접속시 로그인 프레임을 생성하고 hsql db 와 연동하여 인증
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

- 로그인 화면
    - 최초 접속시 표시될 로그인 화면 작성
        - 입력 : 아이디 / 패스워드
        - users 테이블에서 조회 후 인증
    - 인증 성공시 대시보드 화면으로 이동
    - Mockup 구성된 메뉴바 오른쪽 로그인 사용자 명을 실제 로그인 한 사용자의 users 테이블 내 아래 컬럼으로 조합하여 표시
        - depart/username
    - Mockup 구성된 로그아웃 버튼에 기능 부여
        - 로그아웃을 할지 확인(confirm) 창을 띄우고 "예" 버튼을 클릭하면 로그아웃 하고 로그인 화면으로 이동
    
    
        

