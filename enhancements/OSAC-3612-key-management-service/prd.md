# Key Management Service - Key Lifecycle and Vault KMS Integration

| Field       | Value   |
|-------------|---------|
| Author(s)   | Dakota Crowder |
| Jira        | [OSAC-3612](https://redhat.atlassian.net/browse/OSAC-3612) |
| Date        | 2026-09-10 |

## Problem Statement

OSAC can store secrets with envelope encryption, but Tenant Admins cannot manage encryption keys as tenant-scoped resources with distinct lifecycle states. They therefore lack a consistent way to create, rotate, revoke, destroy, and inspect keys for resources consumed across OSAC services. Cloud Provider Admins and Cloud Infrastructure Admins also lack a common product experience for configuring key-management policy and observing the health and audit history of key operations. Without a consumer-neutral key-management backbone, each consuming service must provide its own key handling and Vault integration, leading to duplicated behavior and inconsistent tenant controls.

## In Scope

- A consumer-neutral key-management capability for tenant-owned keys, exposed through the OSAC API and CLI, with create, view, rotate, revoke, and destroy lifecycle operations. [Clarify: R1.Q1, R1.Q5]
- Tenant isolation that restricts Tenant Admins to keys and usage information belonging to their tenant. [Clarify: R1.Q2]
- Cloud Provider Admin configuration of platform key backends and policies, applied transparently so tenants do not configure or select KMS infrastructure. [Clarify: R2.Q1, R3.Q1]
- Key versions and visible lifecycle states, including transparent interim rotation states and retention of prior versions needed by existing consumers. [Clarify: R1.Q4]
- Consumer-neutral key associations, lifecycle safeguards, usage visibility, and audit history that can support storage, CaaS, and other downstream consumers. [Clarify: R1.Q3, R1.Q5, R2.Q3, R2.Q4, R3.Q2]
- End-to-end coverage of the supported API and CLI key-management journeys.

## Out of Scope

- A key-management UI. [Clarify: R1.Q1]
- Storage-specific Vault KMIP integration and key binding to volumes, file shares, or object buckets; these belong to OSAC-2389. [Jira: OSAC-2389] [Clarify: R1.Q5]
- Automated key-rotation policies.
- Hardware Security Module integration beyond Vault capabilities.
- Tenant configuration or selection of KMS infrastructure, including tenant-specific backend defaults. [Clarify: R3.Q1]
- Client-side encryption, cross-site key replication, and multi-region key management. [Jira: OSAC-2389]

## User Stories

### Cloud Provider Admin

- As a Cloud Provider Admin, I want to configure platform key backends so that tenants can manage keys without needing to understand the supporting infrastructure. [Clarify: R2.Q1, R3.Q1]
- As a Cloud Provider Admin, I want to configure platform key policies so that tenant key management follows provider requirements across consuming services. [Clarify: R2.Q1]

### Cloud Infrastructure Admin

- As a Cloud Infrastructure Admin, I want read-only visibility into key health so that I can maintain the availability of the platform KMS without managing tenant key lifecycles. [Clarify: R2.Q2]
- As a Cloud Infrastructure Admin, I want read-only access to key-operation audit history so that I can support operational and compliance review without changing tenant-owned keys. [Clarify: R2.Q2]
- As a Cloud Infrastructure Admin, I want to manage platform KMS availability so that tenant key lifecycle operations remain usable without granting me control over tenant-owned keys. [Clarify: R2.Q2]

### Tenant Admin

- As a Tenant Admin, I want to create tenant-scoped encryption keys through the API or CLI so that my tenant's resources can use centrally managed keys without requiring KMS infrastructure configuration. [Clarify: R1.Q1, R1.Q2, R3.Q1]
- As a Tenant Admin, I want to view each key's versions, lifecycle state, associated consumer names and types, and last-used time so that I can understand how keys in my tenant are being used. [Clarify: R2.Q4]
- As a Tenant Admin, I want to rotate a key and see its interim and resulting states so that I know when a new version is active while versions needed by existing consumers remain available. [Clarify: R1.Q4]
- As a Tenant Admin, I want to revoke a key from new use without permanently removing it so that recovery and existing-consumer needs can be addressed. [Clarify: R2.Q3]
- As a Tenant Admin, I want to destroy an unattached key permanently so that obsolete key material can be removed without breaking an attached consumer. [Clarify: R1.Q3, R2.Q3]
- As a Tenant Admin, I want destruction of an attached key to be rejected with an actionable explanation so that I can remove its associations before retrying. [Clarify: R1.Q3, R3.Q2]
- As a Tenant Admin, I want a consumer-neutral way to associate keys with downstream services so that each service can use the same tenant-controlled key lifecycle. [Clarify: R1.Q5]
- As a Tenant Admin, I want each lifecycle operation to report success or an actionable failure and leave the key in an unambiguous reported state so that I can safely decide what to do next. [Clarify: R3.Q2]
- As a Tenant Admin, I want create, rotate, revoke, and destroy operations to appear in audit history so that I can review changes to my tenant's keys. [Clarify: R3.Q2]

## Dependencies

- **Secret Management (OSAC-1567):** Provides the Vault-based secret-management foundation on which key lifecycle management builds.
- **Vault:** Provides key storage and lifecycle capabilities used by the platform KMS.
- **Per-Project Encryption Key Management (OSAC-2389):** Depends on this feature's consumer-neutral lifecycle and association capabilities before adding storage-specific KMIP integration and resource binding.
- **Downstream OSAC services:** Storage, CaaS, and other consumers depend on a consistent way to associate their resources with tenant-managed keys.

---

## Provenance

Authored: draft @ prd 0.10.1 - a7f4aa1, workspace main @ b9575896d
Phases: draft, draft

<!-- ai-workflow-provenance:{"schema_version":1,"provenance_kind":"session","workflow":"prd","workflow_version":"0.10.1","ai_workflows":"a7f4aa1","source_repo":"b9575896d","source_repo_branch":"main","commits_behind_main":0,"commits_ahead_main":0,"main_ref":"main","phases":["draft","draft"],"authoring_modes":["skill"],"context_changed":false,"origin_untracked":false} -->
