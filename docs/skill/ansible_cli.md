# ansible-cli

mcp-ansible의 `run_cli`에서 Ansible 2.9 플레이북을 검사하고 실행할 때 쓴다.
`playbook` CLI로 ansible-lint 5.4 검사, check/run, 인벤토리 관리를 한다.

여러 MCP가 묶인 에이전트에서는 도구 이름이 `ansible__run_cli`로 네임스페이스된다. 단독 바인딩이면 `run_cli`일 수 있다.

# playbook: Ansible 2.9 플레이북 검사·실행 CLI

`mcp-ansible` 서버의 `run_cli` 도구 안에서 `playbook` 명령으로 Ansible 플레이북을 검사하고 실행한다. 이 문서는 `playbook guide`로도 볼 수 있다.

## 먼저 알아 둘 것

- **Ansible 2.9.27이다.** 짧은 모듈 이름(`copy`, `yum`, `service`)과 `yes`/`no`를 쓴다. FQCN(`ansible.builtin.copy`)과 collections는 쓰지 않는다. lint는 ansible-lint 5.4이고 자동 수정(`--fix`)은 없다.
- **순서는 lint → check → run이다.**
  - `lint`: 문법·보안·기타 규칙을 검사한다. 대상 호스트에 접속하지 않는다.
  - `check`: `--check --diff`로 실행해 바뀔 내용만 보인다. 대상 호스트를 바꾸지 않는다. 단, 플레이북에 `check_mode: no`인 태스크가 있으면 그 태스크는 실제로 실행된다(결과의 `warnings`에 나온다).
  - `run`: 실제로 적용한다. **사용자가 적용을 요청했을 때만** 하고, 같은 플레이북·인벤토리·`--limit`으로 check한 결과(바뀔 호스트와 내용)를 먼저 보여 준다.
- **SSH 계정과 개인키는 이미 설정되어 있다.** Secret에서 주입된다. 계정, 비밀번호, 키, `become` 비밀번호를 명령, 플레이북, 인벤토리에 넣지 않는다. 비밀번호가 필요한 작업이면 할 수 없다고 알린다.
- **`ansible-playbook`을 직접 부르지 않는다.** `playbook`이 연결 방식, 결과 저장, 시간 제한을 맞춘다.
- **저장되는 것:** 플레이북(`-`로 받은 내용), 작업 결과, 인벤토리는 `/data`에 남는다. 파드가 다시 떠도 유지된다.
- **시간 제한:** check 기본 300초, run 기본 600초(`--timeout`으로 바꾼다). `run_cli`의 `timeout_seconds`는 이보다 길게 준다(예: check는 330, run은 660). `run_cli`가 먼저 끊으면 작업은 결과 없이 `running`으로 남는다.

## 플레이북 넘기기

플레이북은 세 가지로 준다.

| 형식 | 예 |
|---|---|
| 표준 입력(heredoc). 받은 내용은 `/data/playbooks/YYYYMMDD_HHMMSS_<ms>.yml`로 저장된다 | `playbook lint - <<'EOF'` ... `EOF` |
| 저장된 플레이북 이름(`playbook list`) | `playbook check 20261003_101500_1759454100000.yml` |
| 파일 경로 | `playbook check /work/site.yml` |

heredoc 구분자는 `<<'EOF'`처럼 따옴표로 감싸 `{{ }}`와 `$`가 셸에서 바뀌지 않게 한다. 한 번 넘긴 내용은 결과의 `playbook` 경로나 저장 이름으로 check, run에 다시 쓴다(같은 내용을 다시 붙이지 않는다).

## 명령

| 하고 싶은 것 | 명령 |
|---|---|
| 문법·보안 검사 | `playbook lint <플레이북>` |
| 바뀔 내용 보기(변경 없음) | `playbook check <플레이북> [--inventory <이름>] [--limit <호스트·그룹>]` |
| 실제 적용 | `playbook run <플레이북> [--inventory <이름>] [--limit <호스트·그룹>]` |
| 작업 결과 다시 보기 | `playbook result <job_id> [--tail 0]` |
| 최근 작업 목록 | `playbook jobs [--limit 20]` |
| 저장된 플레이북 목록(플레이 이름 포함) | `playbook list` |
| 인벤토리 저장(IP만) | `playbook inventory save <이름> --hosts 10.0.0.1,10.0.0.2 [--hosts web=10.0.1.1,10.0.1.2] [--var ansible_port=2222] [--replace]` |
| 인벤토리 저장(호스트명과 IP) | `playbook inventory save <이름> --host web/web01=10.0.1.11,web/web02=10.0.1.12` 또는 `--host-table <파일\|->` |
| 인벤토리에 호스트 더하기 / 빼기 | `playbook inventory add <이름> --hosts ...` / `playbook inventory remove <이름> --hosts 10.0.0.1` |
| 인벤토리 목록 / 내용 / 삭제 | `playbook inventory list` / `playbook inventory show <이름>` / `playbook inventory delete <이름>` |
| SSH 접속 확인(ping 모듈, 변경 없음) | `playbook inventory ping <이름> [--limit <호스트·그룹>]` |

`--inventory`를 빼면 이 파드 자신(localhost, 연결 local)에서 실행된다. 대상 서버를 다룰 때는 항상 인벤토리를 준다.

## 인벤토리

- `--hosts` 값은 쉼표나 공백으로 구분한 호스트 목록이다. 앞에 `그룹=`을 붙이면 그 그룹에 넣는다. 여러 번 줄 수 있다.
  - 호스트: IPv4(`10.0.0.1`), IPv6(`fd00::1`), 호스트 이름(`web01.example.com`). 포트는 `10.0.0.1:2222`, IPv6은 `[fd00::1]:2222`.
  - 그룹 이름: 영문·숫자·`_`(첫 글자 영문이나 `_`). `all`, `ungrouped`는 쓸 수 없다.
- 호스트명과 IP를 함께 받았으면 `--host 이름=IP`로 저장한다. ansible은 호스트명으로 부르고(`--limit web01`, 결과의 host) IP(`ansible_host`)로 접속한다.
  - 그룹은 앞에 `그룹/`: `--host web/web01=10.0.1.11`. 포트는 `web01=10.0.1.11:2222`, IPv6은 `db01=[fd00::21]:2200`.
  - 주소는 IP만 받는다. 같은 호스트명에 다른 IP를 주면 거부된다. 호스트명: 영문·숫자·`.`·`_`·`-`(첫 글자 영문이나 숫자).
- 호스트명·IP 표(사용자가 붙여 준 목록, CSV)는 `--host-table`로 넘긴다. 한 줄에 `호스트명 IP[:포트] [그룹 ...]`, 칸은 공백·탭·쉼표로 나눈다. 첫 줄 머리글(`hostname,ip,group`)과 `#` 주석은 건너뛴다. 그룹이 여럿이면 칸을 더 쓴다.

  ```bash
  playbook inventory save prod --host-table - <<'EOF'
  hostname,ip,group
  web01,10.0.1.11,web
  web02,10.0.1.12,web
  db01,10.0.2.21,db
  EOF
  ```

- `--hosts`, `--host`, `--host-table`은 함께 쓸 수 있다.
- IP만 많으면 파일로 넘긴다. 한 줄에 `--hosts` 값 하나다.

  ```bash
  cat > /tmp/hosts.txt <<'EOF'
  web=10.0.1.11,10.0.1.12
  db=10.0.2.21
  EOF
  playbook inventory save prod --hosts-file /tmp/hosts.txt
  ```

- `--var`로 전체 변수를 줄 수 있다: `ansible_port`, `ansible_python_interpreter`, `ansible_become`, `ansible_become_method`, `ansible_become_user`. 계정(`ansible_user`), 비밀번호, 키 경로는 넣을 수 없다.
- 인벤토리 이름: 영문 소문자·숫자·`_`·`-`. 같은 이름으로 다시 `save`하면 거부된다. 덮어쓰려면 `--replace`, 호스트만 더하려면 `add`.
- `--limit`에 그룹 이름이나 호스트(호스트명으로 저장했으면 호스트명)를 주어 일부만 대상으로 한다: `--limit web`, `--limit web01`, `--limit 10.0.1.11`.
- `inventory remove --hosts`에는 저장한 이름(IP 또는 호스트명)을 준다: `--hosts web01,10.0.0.5`.
- 처음 쓰는 인벤토리는 `inventory ping`으로 접속부터 확인한다. `unreachable`이면 메시지(인증 실패, 시간 초과, 호스트 키)를 사용자에게 전한다.

## 결과 읽기

check, run의 기본 출력:

| 필드 | 뜻 |
|---|---|
| `job_id` | 작업 ID. `playbook result <job_id>`로 다시 본다. |
| `status` | `succeeded`, `failed`, `timed_out` |
| `exit_code` | ansible-playbook 종료 코드. 2는 실패한 호스트, 4는 연결 실패 |
| `recap` | 호스트별 ok, changed, unreachable, failed, skipped |
| `failures` | `fatal:`, `failed:`, `ERROR!` 줄 |
| `warnings` | `check_mode: no` 같은 주의 사항 |
| `stdout` | ansible-playbook 출력의 끝 150줄(`--tail`로 바꾼다, 0이면 전체) |

- check의 `changed`는 "적용하면 바뀔" 항목이다. run을 권하기 전에 `changed`가 있는 호스트와 diff를 요약해 보인다.
- `-o json`으로 받아 jq로 줄인다: `playbook check site.yml -i web -o json | jq '{status, recap, failures}'`.
- `status`가 `timed_out`인 run은 일부 호스트에만 적용되었을 수 있다. 다시 run하지 말고 check로 현재 상태를 먼저 본다.

lint 출력: `passed`, `issue_count`, `issues`(rule, category, severity, line, message). `category`는 `syntax`, `security`, `other`다. `security`(예: `risky-file-permissions`, `command-instead-of-module`, `risky-shell-pipe`)는 고칠 방법과 함께 먼저 알린다.

## 예

```bash
playbook lint - <<'EOF'
- name: nginx 설치
  hosts: web
  become: yes
  tasks:
    - name: 패키지
      yum:
        name: nginx
        state: present
    - name: 서비스
      service:
        name: nginx
        state: started
        enabled: yes
EOF
playbook inventory save web --hosts web=10.0.1.11,10.0.1.12
playbook inventory ping web
playbook check <lint 결과의 playbook 경로> --inventory web -o json | jq '{job_id, status, recap, failures}'
# 사용자가 적용을 요청한 뒤
playbook run <같은 경로> --inventory web -o json | jq '{job_id, status, recap, failures}'
```

## 종료 코드

| 코드 | 뜻 | 할 일 |
|---|---|---|
| 0 | 성공(lint 통과, 플레이북 성공) | |
| 1 | lint 위반, 플레이북 실패, 연결 실패 | 결과의 `issues`, `failures`, `recap`을 본다. |
| 2 | 사용법 오류(플레이북·인벤토리 없음, 잘못된 호스트·변수) | 메시지대로 고친다. |
| 3 | SSH 계정·키 설정 없음 | 사람에게 Secret `mcp-ansible-ssh` 설정을 요청한다. |
| 124 | 시간 초과 | `--timeout`과 `run_cli`의 `timeout_seconds`를 늘리거나 `--limit`으로 대상을 나눈다. |
