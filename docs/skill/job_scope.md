# Interpret mail by subject and body

- Prefer the **body** over the subject when judging content.

## decision_type criteria

### 1. Criteria for decision_type = 11

- Subject/body is an out-of-office / auto-reply (e.g. AUTOREPLY)
- Sender domain is **not** one of:
  - `@lguplus.co.kr`, `@lgupluspartners.co.kr`
- Informational/newsletter mail, or body has no usable text (image-only, etc.)
- Subject/body falls **outside** these topics:
  1. Kubernetes cluster
  2. KubeVirt cluster
  3. Ansible playbook or AWX
  4. vSphere VM, NSX
  5. Infra type not named explicitly, but the mail is a request/inquiry about infra service location, architecture, or Ansible playbook creation
- Do **not** use type 11 for **simple inventory lookup** (IP / hostname / owner / operator, no CUD) — that is `decision_type = 10` (§3), for jobs + `INFRA_SEARCH_AGENT` handling



### 2. Criteria for decision_type = 5

Classify as `decision_type = 5` when any of the minimum information below is missing.

#### 2.1. Read (non-destructive inventory)

For requests for configuration info, architecture analysis, or current-state inventory, the following minimums are required per infra type.

##### 2.1.1. Kubernetes

- No additional minimums If you got a request for capabilities of tools
- cluster name is required if not



##### 2.1.2. KubeVirt

- No additional minimums If you got a request for capabilities of tools
- cluster name is required if not



##### 2.1.3. Ansible / AWX

- No additional minimums for Ansible/AWX



##### 2.1.4. vSphere VM, NSX

- No additional minimums If you got a request for capabilities of tools
- Datacenter is required if not



#### 2.2. CUD (change / create / delete)

For change, create, or delete (CUD) work on target infra, the following minimums are required.

##### 2.2.1. Kubernetes

**Allowed manifests**

RoleBinding, Group/Users (OKD only), Namespace (Project), Deployments (Deployment, StatefulSet, DaemonSet, DeploymentConfig (OKD only)), ServiceAccount, ConfigMap/Secret, PersistentVolumeClaim, Service, Route/Ingress

**Per-manifest requirements**

- **Namespace**
  - Fields to change: e.g. DisplayName, ResourceQuota, …
- **ResourceQuota**
  - CPU/MEM capacity
  - Pod count limit (optional)
- **Group/Users (OKD only)**
  - Group name and users to assign
- **RoleBinding**
  - Role assignment (OKD: `admin`, `cru-admin`, `view`, `edit` / plain K8s: `admin`, `view`, `edit`)
- **Deployments**
  - Fields to change: e.g. image path, Resources, Replicas, updateStrategy, serviceAccount, …
  - For sidecar/initContainer add: image path and container name
- **ServiceAccount SCC | rolebinding**
  - SCC type and target ServiceAccount, and/or intended rolebinding
- **ConfigMap/Secret**
  - Change content (manifest name and config/env values, etc.)
- **PersistentVolumeClaim**
  - PVC name and capacity to change
- **Service**
  - Type change (`ClusterIP`, `NodePort`)
- **Route/Ingress certificate renew** (OKD: Route only)
  - Certificate material and apply time



##### 2.2.2. KubeVirt

- Includes 2.2.1
- Target VM identity plus resource kinds and capacities to change



##### 2.2.3. vSphere

- Target VM and resources to change (CPU/MEM/DISK)
- VM identity for Power On/Off/restart (VM state/phase change)



### 3. Criteria for decision_type = 10

- Does not match 1 or 2 above (in scope **and** minimum information is present)
- **Simple inventory lookup** (inventory / `INFRA_SEARCH_AGENT` style) — classify as `decision_type = 10`:
  - Questions answerable by querying inventory tables (e.g. IP, hostname, owner, operator / 담당자·운영자)
  - Queries that do **not** include CUD (create / update / delete / change) work
  - Prefer `10` for these (not `11` or `5`); they enter the jobs pipeline for inventory-search handling
  - Differs from §2.1 Read: §2.1 is non-destructive infra **config/architecture** analysis with per-type minimum IDs; §3 inventory lookup is table-backed Q&A without CUD

