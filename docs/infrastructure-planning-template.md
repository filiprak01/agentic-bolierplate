# Infrastructure Planning Template

Release 1.2 uses this template to help Architecture and DevOps/Platform agents
plan right-sized infrastructure without implementing live cloud provisioning.

## Purpose

The template captures deployment requirements early enough for project
roadmaps, architecture decisions, and context packs, while keeping paid
infrastructure creation behind separate Product Owner-approved stories.

## Intake Questions

Architecture Agent must ask or confirm:

1. Expected scale: users, traffic, data volume, concurrency, batch load, and
   growth assumptions.
2. Data sensitivity: personal data, business-sensitive records, retention,
   compliance, and access-control needs.
3. Availability needs: uptime expectations, recovery time, backup retention,
   maintenance windows, and incident response expectations.
4. Budget: monthly infrastructure ceiling, tolerance for managed services, and
   acceptable tradeoffs between cost and operations effort.
5. Deployment target: local Docker, VPS, managed container service, managed
   database, object storage, monitoring, backup, or future Kubernetes.
6. Growth path: trigger points for moving from the smallest reasonable
   footprint to managed services or orchestration.

If any field is missing or contradictory, create a Product Owner inbox
question. Do not guess cost, compliance, or production availability needs.

## Supported Deployment Profiles

| Profile | Use When | Notes |
| --- | --- | --- |
| `local_docker` | MVP, demo, internal tool, or local-only project | Default starting point when public availability is not required. |
| `vps` | Small public service with low/medium traffic and simple operations | Requires deployment, backup, monitoring, and SSH/access decisions. |
| `managed_container_service` | Service needs easier scaling or reduced server maintenance | Future story should define provider, registry, secrets, and rollout policy. |
| `managed_database` | Durable data must survive app container replacement | Requires backup, migration, access, and cost decisions. |
| `object_storage` | Files, reports, exports, or media must be durable and scalable | Requires retention, access, and data-sensitivity decisions. |
| `monitoring` | Service must detect failures, latency, or capacity issues | Should include alert routing and dashboard ownership. |
| `backup` | Data loss would block business or compliance | Should include restore-test expectations. |
| `future_kubernetes` | Multi-service scale or many projects justify orchestration overhead | Roadmap-only until PO approves the provisioning release. |

## Output Shape

Architecture Agent produces:

1. Starting footprint: smallest reasonable set of deployment profiles.
2. Upgrade path: what to add when scale, availability, or project count grows.
3. Roadmap story candidates: deployment preparation tasks only when the target
   project needs more than local Docker.
4. Provisioning boundary: explicit statement that live provisioning is not in
   scope unless Product Owner approves a separate story.
5. Jira/context references: affected project stories, architecture docs, and
   deployment profile decisions.

## Roadmap Story Rules

Generated project roadmaps should include infrastructure preparation stories
when:

1. The project requires public access.
2. The project needs a VPS, managed container service, or future Kubernetes.
3. The project needs managed database setup, backups, object storage,
   monitoring, DNS, TLS, secrets, or external provider credentials.
4. The Product Owner needs partner/client deployment documentation.

Generated roadmaps should not include live provisioning implementation when:

1. The project remains local Docker only.
2. Deployment target, budget, or access credentials are missing.
3. The Product Owner has not approved paid infrastructure or cloud account use.

## Agent Boundary

Architecture Agent owns requirements and tradeoffs.

DevOps/Platform Agent owns runtime, Docker, validation, and future deployment
handoff planning.

Security Agent owns secrets, access-control, data sensitivity, and threat-model
inputs.

Developer Agent does not provision infrastructure from this template. It only
implements code stories created after the Product Owner approves deployment
scope.
