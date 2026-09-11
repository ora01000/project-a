# 설명
kubernetes 에이전트를 사용해서 단계에서 설명하는 K8S manifest 를 생성한다.
스크립트는 kubectl 또는 자연어 프롬프트로 생성한다.

# 단계
1. {cluster_name} 클러스터의 {project} 프로젝트에 {image} 를 사용해서 deployment를 생성한다. deployment 이름은 {deployment_name}, replica 개수는 {replicas}, updateStrategy는 {update_strategy} 로 지정한다. 
2. {cluster_name} 클러스터의 {project} 프로젝트에 {deployment_name} deployment 와 연결되는 clusterip 타입의 service 를 생성한다. 이름은 {service_name} 이다.
3. {cluster_name} 클러스터의 {project} 프로젝트에 {service_name}과 연결되는 route 를 생성한다. 이름은 {route_name} 이며 hostname(도메인 명) 은 {hostname} 이다. HTTP(80)으로 통신하도록 구성한다.
4. 결재자를 추가한다. 결재자는 {userid} 이다. 인증서 파일을 업로드 받는다.

