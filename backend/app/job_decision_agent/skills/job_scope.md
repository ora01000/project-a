# JOB_DECISION_AGENT — supported job skills

Target infrastructures: **Kubernetes / OKD**, **KubeVirt**, **vSphere**, **Ansible**.

## 1. Read / inventory (non-destructive)

Provide configuration, architecture analysis, or current-state inventory for the target infra.
Minimum inputs usually include: target cluster/infra identity, and what to report (scope).

## 2. Change (mutation) — TBD for execution; decide readiness only

### 2.1 Kubernetes / OKD

Allowed manifests: RoleBinding, Group/Users (OKD only), Namespace/Project, Deployments
(Deployment, StatefulSet, DaemonSet, DeploymentConfig OKD-only), ServiceAccount,
ConfigMap/Secret, PersistentVolumeClaim, Service, Route/Ingress, EgressIP
(OKD ≤4.15 ovs: netnamespace/hostsubnet; OKD ≥4.18 ovn: EgressIP).

Per-manifest minimums for a **change** request:
- **Namespace**: change fields (DisplayName, ResourceQuota, EgressIP, …); ResourceQuota CPU/MEM; optional Pod limit
- **Group/Users (OKD)**: group name and users to assign
- **RoleBinding**: role — OKD `admin|cluster-admin|view|edit`; plain K8s `admin|view|edit`
- **Deployments**: change fields (image, resources, replicas, updateStrategy, serviceAccount, …);
  for sidecar/initContainer: image path + container name
- **ServiceAccount**: SCC type and target SA, and/or rolebinding intent
- **ConfigMap/Secret**: manifest name + config/env values to change
- **PVC**: PVC name + capacity
- **Service**: type change (ClusterIP / NodePort)
- **Route/Ingress cert renew** (OKD: Route only): certificate material + apply time

### 2.2 KubeVirt

- Target VM identity
- Resource kinds and capacities to change

### 2.3 vSphere

- Target VM identity
- CPU/MEM/DISK changes and/or power On/Off/restart intent

## 3. Create (provision) — TBD for execution; decide readiness only

### 3.1 Kubernetes / OKD

Same manifest set as §2.1. Minimums for **create**:
- **Namespace**: name, DisplayName, ResourceQuota (CPU/MEM; optional Pod limit)
- **Group/Users (OKD)**: new group + users
- **RoleBinding**: role assignment as in §2.1
- **Deployments**: name, image, replicas, updateStrategy, serviceAccount, …
- **ServiceAccount**: name, SCC, rolebinding
- **ConfigMap/Secret**: name + file/content defining config/env
- **PVC**: name, capacity, storageClass
- **Service**: target deployment, port, optional targetPort
- **Route/Ingress** (OKD: Route): name, hostname, forward service/path, insecure vs secure (+ certs)

### 3.2 KubeVirt

New VM: hostname, IP, OS/base image, CPU/MEM/DISK

### 3.3 vSphere

New VM: hostname, IP, OS/base image, CPU/MEM/DISK

## 4. Ansible

Treat as in-scope when the mail clearly requests Ansible playbook/runbook style automation
against managed infra. Require enough inventory target + intended action; otherwise mark insufficient.
