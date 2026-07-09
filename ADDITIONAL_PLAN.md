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

## 메뉴바 기능 구현
- Mockup 된 메뉴바에 실제 기능 추가
    - 에이전트 관리
    

