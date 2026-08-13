# OKD / Kubernetes manifests for multi-pod AX Platform.
#
# Prerequisites:
#   - PostgreSQL reachable via DATABASE_URL
#   - Redis reachable via REDIS_URL
#   - Optional Secret ax-k8s-kubeconfig with key `kubeconfig` mounted at /etc/k8s/kubeconfig
#
# Apply order:
#   1. kubectl apply -f secrets.example.yaml  # after editing → secrets.yaml
#   2. kubectl apply -f backend-api-deployment.yaml
#   3. kubectl apply -f backend-worker-deployment.yaml
#   4. kubectl apply -f frontend-deployment.yaml
#   5. Route/Ingress to ax-frontend (and webhook paths to ax-backend-api as needed)
#
# Roles:
#   BACKEND_ROLE=api    → FastAPI only (no scrape/job/mynote/mail-receive loops)
#   BACKEND_ROLE=worker → background loops only (replicas must stay 1)
#   BACKEND_ROLE=all    → single-process (local / legacy)
#
# Received mail attachments (api+worker share the same path via PVC):
#   RECEIVED_MAIL_ATTACHMENT_HOME=/var/lib/ax-platform/received-mail
#
# See docs/ARCHITECTURE_MULTIPOD.md
