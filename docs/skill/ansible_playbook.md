# Ansible Playbook 작성 스킬

에이전트가 **Ansible 2.9.18**용 Playbook을 **작성**할 때 따르는 스킬이다.  
대상은 완성된, 운영에 쓸 수 있는, 문법적으로 올바른 YAML Playbook이다.

이 스킬은 **작성 규칙만** 다룬다. ansible-lint MCP 호출, `valid`/`message`/`work_script` JSON 검증 계약, lint 재시도 루프는 **포함하지 않는다**.  
실검증이 필요하면 플랫폼의 **ansible-lint 에이전트**(또는 워크플로 검증 UI)에 맡긴다.

---

## 적용 조건

다음일 때 이 스킬을 적용한다.

- 사용자가 Ansible Playbook 작성·수정을 요청한 경우
- 워크플로 설계에서 `script_type`이 **`ansible`** 인 `work_script`를 생성·보완하는 경우
- Private Cloud 등 통합 에이전트가 자동화 Playbook 초안을 제시하는 경우

Playbook이 아닌 인프라 조회·CLI 실행·인벤토리 SQL 등은 이 스킬을 쓰지 않는다.

---

## 대상 버전 (MUST)

- 런타임은 **Ansible 2.9.18**만 가정한다.
- 2.9.18 이후에 도입된 문법·모듈·키워드·컬렉션 관례를 사용하지 않는다.

---

## 핵심 제약 (MUST)

1. **클래식 모듈명 (FQCN 금지)**  
   - 사용 금지 예: `ansible.builtin.copy`, `community.general.docker_container`  
   - 사용 예: `copy`, `template`, `yum`, `apt`, `service`, `file`, `lineinfile`, `command`, `shell`, `docker_container`

2. **레거시 변수·fact**  
   - 전통 fact를 사용한다. 예: `ansible_os_family`, `ansible_distribution`, `ansible_distribution_major_version`  
   - 컬렉션 범위의 최신 fact 관례에 의존하지 않는다.

3. **2.9.18 이후 키워드·패턴 금지**  
   - 해당 버전에서 지원되지 않는 키워드·모듈을 넣지 않는다.  
   - `import_role`, `include_tasks`, `loop`, `with_items` 등은 **2.9.18에서 허용되는 형태만** 사용한다.

---

## 작성 기준 (MUST)

### YAML·구조

- 결과는 **유효한 YAML**이어야 한다. 들여쓰기는 **스페이스 2칸**.
- 플레이북은 반드시 `---`로 시작한다.
- play 정의에 필요한 키를 둔다. 예: `hosts`, `become`, `vars`, `tasks`, 필요 시 `handlers`.
- **모든 play와 모든 task**에 명확한 `name:`을 붙인다.

### 멱등성·상태

- task는 멱등하게 작성한다.
- 모듈이 지원하면 `state:`를 명시한다. 예: `state: present`, `state: started`, `state: absent`.

### 권한·변수·핸들러

- root가 필요할 때만 `become: yes`(또는 play/task 수준 become)를 사용한다.
- 변수는 `vars:` 아래에 모으거나, 참조가 분명하게 쓰는다.
- 설정 변경 후 서비스 재시작이 필요하면 `handlers` + `notify`를 사용한다.

### command / shell

- `command` / `shell`을 쓸 때는 꼭 필요할 때만 사용한다.
- 필요 시 `failed_when`, `changed_when`, `ignore_errors`를 의도에 맞게 지정한다.
- 가능하면 전용 모듈(`yum`, `apt`, `service`, `copy` 등)을 우선한다.

---

## 작업 순서 (MUST)

1. **요구 정리**  
   - 대상 호스트/그룹, 목적(설치·설정·재시작 등), OS/패키지 제약이 요청에 있는지 확인한다.  
   - 필수 정보가 없으면 추측으로 채우지 말고, 호출 맥락이 허용하면 확인한다.  
   - 워크플로 JSON 생성처럼 질문 없이 한 번에 내야 하는 맥락이면, 요청에 있는 범위만으로 최소 완전 playbook을 만든다.

2. **Playbook 작성**  
   - 위 버전·제약·작성 기준을 모두 지킨다.  
   - 불완전한 조각이 아니라 **실행 가능한 전체 playbook**을 만든다.

3. **자체 점검 (작성 품질만)**  
   - FQCN·신규 키워드·이름 없는 task·깨진 YAML이 없는지 확인한다.  
   - **ansible-lint 도구 호출은 이 스킬의 범위가 아니다.**

4. **출력**  
   - 아래 「출력 형식」을 따른다.

---

## 출력 형식

### 대화·일반 작성 (PRIVATE_CLOUD 등)

- 완전한 playbook YAML을 **하나의** 마크다운 코드 블록으로 제공한다.
- 이어서 짧은 기술 설명(무엇을 하는지, 전제·주의)을 한국어로 덧붙일 수 있다.
- 불필요한 잡담은 하지 않는다.

### 워크플로 `work_script` (WORKFLOW_AGENT)

- `script_type`은 **`ansible`** 이다.
- `work_script`에는 마크다운 펜스 없이 **순수 YAML playbook 본문**만 넣는 것을 기본으로 한다(호출 측 JSON 스키마가 요구하는 형태를 우선).
- playbook은 이 스킬의 2.9.18·클래식 모듈·구조 규칙을 만족해야 한다.

---

## 범위 밖 (하지 않음)

- ansible-lint MCP 또는 기타 lint 도구 호출
- 검증 전용 JSON만 반환 (`valid` / `message` / `work_script` 계약)
- lint 실패 → 수정 → 재검증 루프 수행
- Ansible이 아닌 인프라 CLI(`kubectl`/`oc`/`govc` 등)나 인벤토리 SQL 작성

검증이 필요하면 작성 결과를 넘기고, **ansible-lint 에이전트** 경로를 사용한다.
