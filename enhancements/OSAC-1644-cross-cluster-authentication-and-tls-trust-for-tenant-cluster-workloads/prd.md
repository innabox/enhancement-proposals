# Cross-cluster authentication and TLS trust for tenant cluster workloads

| Field | Value |
|---|---|
| Author(s) | Daniel Erez |
| Jira | [OSAC-1644](https://redhat.atlassian.net/browse/OSAC-1644) |
| Date | 2026-09-07 |

## Problem Statement

In a multi-cluster OSAC deployment, workloads on a workload or tenant cluster cannot reliably authenticate to the fulfillment service using credentials issued by their own Kubernetes cluster. The resulting failure blocks the intended management-cluster and workload-cluster topology. Tenant-cluster workloads also cannot establish a trusted TLS connection until they trust the management cluster's certificate authority. Without this capability, consumers such as the CSI driver cannot securely make required fulfillment-service calls across cluster boundaries.

## In Scope

- Consumption of one Keycloak service-account client per tenant cluster, scoped to the tenant that owns the cluster, for cross-cluster fulfillment-service access. [Clarify: R1.Q1] [Clarify: R1.Q2]
- Secure connectivity for supported workload-cluster consumers, including `osac-operator`, the CSI driver, and future tenant-cluster workloads: server-authenticated TLS with hostname validation and a scoped trust anchor, followed by the OAuth2 `client_credentials` flow. Fulfillment service rejects tokens with a missing or mismatched issuer, audience, required scope, or tenant `organization` claim. [Clarify: R1.Q2] [Clarify: R1.Q3]
- The `ClusterOrder` post-install provisioning workflow is the sole owner of installing cert-manager, waiting for it to become ready, and injecting the management-cluster CA into the tenant-cluster trust store. [Clarify: R1.Q3] [Clarify: R1.Q4]
- Provisioning of a tenant-cluster-scoped Kubernetes Secret containing the Keycloak client ID, client secret, and issuer URL. [Clarify: R1.Q2]
- Verified end-to-end authenticated gRPC connectivity from supported workload-cluster consumers to fulfillment service. Credentials are transmitted only after successful TLS peer verification. [Clarify: R1.Q3]
- Trust setup participates in the existing `ClusterOrder` provisioning and health status model, including retry and post-provisioning recovery reporting. [Clarify: R1.Q5]

## Out of Scope

- CSI-driver deployment, StorageClass configuration, and vendor-specific volume-provisioning behavior, which are addressed by related follow-up work. [Clarify: R1.Q3]

## User Stories

### Cloud Infrastructure Admin

- As a Cloud Infrastructure Admin, I want OSAC components on separate clusters to use a trusted service identity when communicating with fulfillment service so that the supported multi-cluster deployment topology works securely.

- As a Cloud Infrastructure Admin, I want trust established automatically during tenant-cluster provisioning, with retry and failure status when setup cannot complete, so that supported workloads can connect securely without manual trust-store setup or repair. [Clarify: R1.Q4] [Clarify: R1.Q5]

### Tenant Admin / Tenant User

- As a Tenant Admin or Tenant User, I want workloads on my tenant cluster to communicate securely with fulfillment service so that tenant-cluster services such as storage can use the capabilities assigned to the tenant.

## Assumptions

- The target release contains no existing tenant clusters. Trust setup is therefore required for newly provisioned clusters; upgrade handling and backfill of pre-existing clusters are out of scope. [Clarify: R1.Q4]
- To be determined — whether dedicated CLI, UI, or additional troubleshooting indicators beyond the existing `ClusterOrder` status are in scope for this Feature. [Clarify: R1.Q5]

## Dependencies

- **Keycloak:** Provides one service-account client per tenant cluster and the access tokens needed for workload authentication.
- **Certificate-management capability on tenant clusters:** Provides the cert-manager/trust-distribution capability and interfaces consumed by the `ClusterOrder` post-install provisioning workflow; it does not own the post-install workflow or management-cluster CA injection.
- **OSAC-3291:** Deploys the tenant-cluster CSI driver and consumes the cluster-scoped credential Secret and trust/authentication model established by this Feature. [Clarify: R1.Q3]
- **OSAC-4197:** Owns creation, rotation, revocation, and synchronization of the per-tenant-cluster Keycloak clients and credential Secrets. [Clarify: R1.Q1] [Clarify: R1.Q2] [Clarify: R1.Q4]

---

## Provenance

Authored: draft @ prd 0.9.0 - 562b610, workspace main @ ad9ec2979
Final: revise @ prd 0.9.0 - 562b610, workspace prd/OSAC-1644 @ ad9ec2979

> Context changed between draft and revise.

<!-- ai-workflow-provenance:{"schema_version":1,"provenance_kind":"session","workflow":"prd","workflow_version":"0.9.0","ai_workflows":"562b610","source_repo":"ad9ec2979","source_repo_branch":"prd/OSAC-1644","commits_behind_main":0,"commits_ahead_main":0,"main_ref":"main","phases":["draft","revise","revise","revise","revise","revise"],"authoring_modes":["skill"],"context_changed":true,"origin_untracked":false} -->
