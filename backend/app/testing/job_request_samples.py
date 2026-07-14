"""Periodic job requester test samples (code-managed, not stored in DB).

These templates are used by the job-requester simulator after review/approval.
All samples are READ-only and designed to target Kubernetes / KubeVirt agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TargetAgentFamily = Literal["kubernetes", "kubevirt"]

# Planned send interval for the job-requester simulator (minutes).
JOB_REQUESTER_INTERVAL_MINUTES = 60


@dataclass(frozen=True)
class JobRequestSample:
    sample_id: str
    job_title: str
    job_description: str
    approver: str
    target_agent_family: TargetAgentFamily
    notes: str


REQUEST_DEPART = "IT플랫폼운영팀"
REQUESTER = "윤인수"
REQUESTER_EMAIL = "isyun@lguplus.co.kr"

# Approvers match usernames in seed users (윤인수 / 안세훈).
APPROVER_YUN = "윤인수"
APPROVER_AHN = "안세훈"

JOB_REQUEST_SAMPLES: list[JobRequestSample] = [
    JobRequestSample(
        sample_id="TR-001",
        job_title="[테스트] IT공통 개발기 네임스페이스 목록 조회",
        job_description=(
            "대상 클러스터: dprv-k8s (IT공통 개발기)\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) Kubernetes Agent를 통해 전체 네임스페이스 목록을 조회한다.\n"
            "2) NAME, STATUS, AGE 정보를 표 형태로 정리한다.\n"
            "3) 결과를 작업 보고용으로 요약한다.\n"
            "주의: 리소스 생성/변경/삭제 명령은 수행하지 않는다."
        ),
        approver=APPROVER_YUN,
        target_agent_family="kubernetes",
        notes="K8s 클러스터 네임스페이스 조회",
    ),
    JobRequestSample(
        sample_id="TR-002",
        job_title="[테스트] 테스트 클러스터 노드 Ready 상태 확인",
        job_description=(
            "대상 클러스터: dtest-k8s (테스트 클러스터)\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) Kubernetes Agent로 노드 목록과 Ready 조건을 조회한다.\n"
            "2) NotReady 노드가 있으면 해당 노드명과 조건을 보고한다.\n"
            "3) 전체 노드 Ready 여부를 요약한다.\n"
            "주의: cordon/drain 등 상태 변경 작업은 수행하지 않는다."
        ),
        approver=APPROVER_AHN,
        target_agent_family="kubernetes",
        notes="K8s 노드 상태 조회",
    ),
    JobRequestSample(
        sample_id="TR-003",
        job_title="[테스트] 빌드팜 default/kube-system Pod 상태 조회",
        job_description=(
            "대상 클러스터: pcicd-k8s (빌드팜)\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) Kubernetes Agent로 namespace=default, kube-system 의 Pod 목록을 조회한다.\n"
            "2) Running이 아닌 Pod(Pending/Failed/CrashLoopBackOff 등)를 별도 표로 정리한다.\n"
            "3) 이상 Pod가 없으면 '이상 없음'으로 보고한다.\n"
            "주의: Pod 재시작, 삭제, 스케일링은 수행하지 않는다."
        ),
        approver=APPROVER_YUN,
        target_agent_family="kubernetes",
        notes="K8s Pod 상태 조회",
    ),
    JobRequestSample(
        sample_id="TR-004",
        job_title="[테스트] UCube 공통 개발기 Deployment/Service 현황 조회",
        job_description=(
            "대상 클러스터: dprmn-k8s (UCube 공통 개발기)\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) Kubernetes Agent로 Deployment 목록(이름, ready replicas, 네임스페이스)을 조회한다.\n"
            "2) Service 목록(이름, type, cluster IP/ports)을 조회한다.\n"
            "3) Deployment ready 비율이 100%가 아닌 항목을 강조한다.\n"
            "주의: Deployment/Service 스펙 수정 및 롤아웃은 수행하지 않는다."
        ),
        approver=APPROVER_AHN,
        target_agent_family="kubernetes",
        notes="K8s Deployment/Service 조회",
    ),
    JobRequestSample(
        sample_id="TR-005",
        job_title="[테스트] KubeVirt VirtualMachine 목록 조회",
        job_description=(
            "대상: KubeVirt\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) KubeVirt Agent로 VirtualMachine 리소스 목록을 조회한다.\n"
            "2) 네임스페이스, 이름, Running/Stopped 상태를 표로 정리한다.\n"
            "3) Stopped 상태 VM 건수를 함께 보고한다.\n"
            "주의: VM start/stop/restart/delete 작업은 수행하지 않는다."
        ),
        approver=APPROVER_YUN,
        target_agent_family="kubevirt",
        notes="KubeVirt VM 목록 조회",
    ),
    JobRequestSample(
        sample_id="TR-006",
        job_title="[테스트] KubeVirt VirtualMachineInstance 실행 상태 확인",
        job_description=(
            "대상: KubeVirt\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) KubeVirt Agent로 VirtualMachineInstance(VMI) 목록을 조회한다.\n"
            "2) phase(Running/Scheduling/Failed 등), nodeName, age 정보를 정리한다.\n"
            "3) Failed 또는 Pending 장기 상태가 있으면 항목을 별도 보고한다.\n"
            "주의: VMI 삭제, 마이그레이션 트리거 등 변경 작업은 수행하지 않는다."
        ),
        approver=APPROVER_AHN,
        target_agent_family="kubevirt",
        notes="KubeVirt VMI 상태 조회",
    ),
    JobRequestSample(
        sample_id="TR-007",
        job_title="[테스트] KubeVirt DataVolume/디스크 리소스 조회",
        job_description=(
            "대상: KubeVirt\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) KubeVirt Agent로 DataVolume 또는 관련 PVC/디스크 리소스 현황을 조회한다.\n"
            "2) 이름, 네임스페이스, 용량, Bound/Pending 상태를 표로 정리한다.\n"
            "3) Pending 상태 디스크가 있으면 원인을 조회 가능한 범위에서 확인한다.\n"
            "주의: DataVolume/PVC 생성·삭제·리사이즈는 수행하지 않는다."
        ),
        approver=APPROVER_YUN,
        target_agent_family="kubevirt",
        notes="KubeVirt 디스크/DataVolume 조회",
    ),
    JobRequestSample(
        sample_id="TR-008",
        job_title="[테스트] Provisioning 개발기 ConfigMap/Secret 목록 조회",
        job_description=(
            "대상 클러스터: dpvs-k8s (Provisioning 개발기)\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) Kubernetes Agent로 ConfigMap/Secret 목록을 조회한다.\n"
            "2) 네임스페이스, 이름, 데이터 키 개수(또는 메타데이터)를 표로 정리한다.\n"
            "3) Secret 값은 출력하지 않고 메타데이터만 보고한다.\n"
            "주의: ConfigMap/Secret 생성·수정·삭제는 수행하지 않는다."
        ),
        approver=APPROVER_AHN,
        target_agent_family="kubernetes",
        notes="K8s ConfigMap/Secret 메타데이터 조회",
    ),
    JobRequestSample(
        sample_id="TR-009",
        job_title="[테스트] KubeVirt VirtualMachineInstanceMigration 현황 조회",
        job_description=(
            "대상: KubeVirt\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) KubeVirt Agent로 VirtualMachineInstanceMigration 리소스 목록을 조회한다.\n"
            "2) 이름, 네임스페이스, phase, 대상 VM/VMI 정보를 표로 정리한다.\n"
            "3) 진행 중(Running) 또는 Failed 상태 항목을 별도 보고한다.\n"
            "주의: 마이그레이션 생성/취소 등 변경 작업은 수행하지 않는다."
        ),
        approver=APPROVER_YUN,
        target_agent_family="kubevirt",
        notes="KubeVirt 마이그레이션 현황 조회",
    ),
    JobRequestSample(
        sample_id="TR-010",
        job_title="[테스트] UCube 과금 개발기 Event 최근 오류 이벤트 조회",
        job_description=(
            "대상 클러스터: dprrt-k8s (UCube 과금 개발기)\n"
            "작업 유형: READ (조회만, 변경/생성/삭제 없음)\n"
            "요청 내용:\n"
            "1) Kubernetes Agent로 Warning 타입 Event를 조회한다.\n"
            "2) 최근 이벤트 중심으로 involved object, reason, message를 정리한다.\n"
            "3) 동일 reason이 반복되는 항목을 요약한다.\n"
            "주의: 리소스 삭제/재시작 등 복구성 변경 작업은 수행하지 않는다."
        ),
        approver=APPROVER_AHN,
        target_agent_family="kubernetes",
        notes="K8s Warning Event 조회",
    ),
]


def list_job_request_samples() -> list[JobRequestSample]:
    return list(JOB_REQUEST_SAMPLES)


def get_job_request_sample(sample_id: str) -> JobRequestSample | None:
    for sample in JOB_REQUEST_SAMPLES:
        if sample.sample_id == sample_id:
            return sample
    return None
