# 이름
만료 임박 인증서 추출 및 갱신

# 설명
OKD {cluster_name} 클러스터의 {project_name} 프로젝트의 Route 에서 인증서를 추출하고 만료일이 {expire_day}일 이내인 인증서 정보를 추출한다. Kubernetes 에이전트를 사용하고 모든 스크립트는 자연어 프롬프트로 구성한다.

# 단계
1. 만료 SSL 인증서 추출한다. {cluster_name} 클러스터의 ingress 또는 route 에서 SSL 인증서 정보를 찾는다. 만료일이 {expire_day}일 이내로 남은 인증서와 route/ingress 를 리포팅한다. {email} 에게 메일로 중간보고를 발송한다. 
2. 이전 작업 결과를 받아서 갱신이 필요한 인증서의 인증서를 갱신한다. 갱신할 인증서는 {certs_location} 이다

