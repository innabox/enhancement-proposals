# Clarification Log — OSAC-1644

## Status

- Rounds completed: 1
- Open gaps: 1
- Exit criteria met: No

## Round 1 — scope, ownership, lifecycle, and interfaces

### R1.Q1: Identity scope

Should the Keycloak service account be one per tenant cluster, scoped to the owning tenant, or one per tenant reused across that tenant's clusters?

#### Answer

The target state is one Keycloak service-account client per tenant cluster, scoped to the tenant that owns the cluster and carrying that tenant's organization claim. Workload authentication uses an OAuth2 access token obtained through the `client_credentials` flow over server-authenticated TLS; this Feature does not require mutual TLS. The temporary shared CSI client remains only a transition state while cluster-specific identities are introduced.

#### Impact

The PRD must state that each tenant cluster receives its own service identity, scoped to the owning tenant. Fulfillment service must validate the configured issuer, audience, required scope, and tenant `organization` claim, and reject a token when any value is missing or does not match the expected tenant or service.

#### Decision (D1)

Use one Keycloak service-account client per tenant cluster, scoped to the owning tenant. The access token is sent to fulfillment service only after the workload has successfully validated the fulfillment-service hostname against a scoped trust anchor.

#### Shared-client migration

The migration uses one deployment-wide cutover so fulfillment service does not
need an additional, cluster-bound request or token identity to decide whether
the shared credential is still valid:

1. OSAC-4197 creates a client and credential Secret for each tenant cluster.
2. Supported consumers in each tenant cluster adopt that cluster's client while the shared CSI client remains available for the defined transition window.
3. After all supported consumers in all tenant clusters have switched successfully, the deployment performs one cutover. The cluster-specific clients become the only accepted authorization path, and fulfillment service rejects the shared CSI credential globally; the shared credential is then removed.

If a cluster-specific client setup fails before cutover, consumers may remain on the shared client while the failure is repaired and the deployment-wide cutover is deferred. After cutover, rollback must restore the affected cluster's client and credentials; the shared credential must not be re-enabled as a fallback authorization path.

---

### R1.Q2: Ownership of client lifecycle

Does OSAC-1644 create the per-tenant-cluster Keycloak clients and credentials, or does OSAC-4197 own their lifecycle while OSAC-1644 defines how consumers use credentials?

#### Answer

OSAC-1644 establishes server-authenticated TLS trust and Keycloak access-token consumption for supported consumers. OSAC-4197 owns automated creation, rotation, revocation, and synchronization of the per-tenant-cluster Keycloak clients during tenant-cluster provisioning. Supported consumers include `osac-operator`, the CSI driver, and future tenant-cluster workloads.

#### Impact

The PRD must list OSAC-4197 as a dependency for the per-tenant-cluster identity lifecycle while retaining OSAC-1644 responsibility for supported consumers' secure connectivity and credential-consumption contract.

#### Decision (D2)

OSAC-4197 owns per-tenant-cluster Keycloak-client creation and lifecycle; OSAC-1644 owns secure consumer connectivity and credential consumption for the supported consumers.

#### Credential handoff contract

OSAC-4197 provisions one tenant-cluster-scoped Kubernetes Secret during `ClusterOrder` provisioning. The Secret contains the Keycloak `client_id`, `client_secret`, and `issuer_url`; the expected audience and required scope are platform configuration. The `issuer_url` must match an approved HTTPS Keycloak issuer and host configured by the platform; a tenant-provided or otherwise unapproved issuer is rejected. Only the intended consumer service accounts may read the Secret through tenant-scoped RBAC, and a consumer must never read a Secret belonging to another tenant or cluster.

The Secret is updated atomically for rotation. Consumers watch the Secret, reload all credential fields as one versioned update, and use the OAuth2 `client_credentials` flow to obtain a new access token before using the rotated credentials. The token request must validate the issuer hostname and trusted CA and must not follow redirects; in particular, the `client_secret` must never be forwarded to another host. If the Secret is missing, invalid, stale, or cannot be synchronized, or if the issuer or token endpoint cannot be validated, the consumer must not send a fulfillment request; it reports the appropriate provisioning or health failure and retries. A failed or expired token causes the consumer to discard its cached token and reauthenticate. Consumers must not fall back to the shared CSI credential after the migration cutover.

---

### R1.Q3: CSI delivery boundary

Does OSAC-1644 need to deliver CSI connectivity end-to-end, or establish the trust and credential prerequisites that OSAC-3291 and other workload-cluster consumers use?

#### Answer

OSAC-1644 establishes cross-cluster trust and authentication for `osac-operator`, the CSI driver, and future tenant-cluster workloads. Success is a supported consumer using its tenant-cluster-scoped Keycloak client credentials to obtain an access token through the OAuth2 `client_credentials` flow and establish an authenticated gRPC connection to fulfillment service. The client validates the fulfillment-service hostname and scoped trust anchor before transmitting the token. CSI-driver deployment and vendor-specific volume provisioning are follow-up responsibilities.

#### Impact

The PRD must require cert-manager availability, management-CA injection during `ClusterOrder` post-install, a provisioned cluster-scoped credential Secret, and a verified secure workload-to-fulfillment-service connection without assigning CSI deployment or vendor-storage functionality to this Feature.

#### Decision (D3)

Success requires `osac-operator`, the CSI driver, or another supported tenant-cluster workload to use its cluster-scoped Keycloak credentials over validated server-authenticated TLS to complete an authenticated gRPC call to fulfillment service. The CSI driver remains a dependent validation consumer, not a delivered workload.

---

### R1.Q4: Existing clusters and rotation

For existing tenant clusters and credential rotation or revocation, what user-visible outcome is required?

#### Answer

There are no existing tenant clusters in the target release. OSAC-1644 requires automatic trust setup and cluster-scoped credential provisioning only for newly provisioned tenant clusters; upgrade, backward-compatibility, and backfill handling are not required. OSAC-4197 owns lifecycle and synchronization of rotated per-tenant-cluster Keycloak credentials so supported consumers receive updates without administrator intervention.

#### Impact

The PRD must cover cert-manager availability, management-CA injection, automatic trust setup, and cluster-scoped credential provisioning for newly provisioned tenant clusters, and identify rotated credential synchronization as an OSAC-4197 dependency, without adding upgrade or backward-compatibility requirements for nonexistent clusters.

#### Decision (D4)

OSAC-1644 automatically establishes trust and provisions cluster-scoped credentials for newly provisioned tenant clusters. OSAC-4197 owns rotated credential lifecycle and synchronization for the supported consumers. Upgrade, backward-compatibility, and backfill handling are not required because the target release has no existing tenant clusters.

---

### R1.Q5: Interfaces and status

Is this administrator-managed installation/provisioning behavior only, or must dedicated UI, CLI, and troubleshooting support be delivered beyond the existing Kubernetes status model?

#### Answer

A trust-specific status signal is needed during provisioning and recovery, but a new trust-only condition is not required by this Feature. The owning resource is `ClusterOrder`, using the existing status model defined by OSAC-1604: initial trust setup is part of the provisioning readiness gate, and later trust loss is reported as an independent health problem.

#### Impact

The PRD must define the existing `ClusterOrder` status behavior. During initial provisioning, `PROGRESSING=True` uses reasons such as `TrustSetupPending` or `TrustSetupRetrying`; a terminal trust failure sets `FAILED=True` with reason `TrustSetupFailed`, while successful trust setup allows the normal readiness transition. After a cluster is usable, lost or stale trust sets `DEGRADED=True` with a trust-specific reason and makes `AVAILABLE=False` while leaving lifecycle state `READY`; recovery clears `DEGRADED` and restores `AVAILABLE` when the other health requirements are satisfied. Each condition records the evaluated `observedGeneration`. The remaining scope decision covers only dedicated CLI, UI, and additional troubleshooting indicators beyond the existing `ClusterOrder` status.

## Remaining Gaps

- Whether dedicated CLI, UI, or additional troubleshooting indicators beyond the existing `ClusterOrder` status are in scope for this Feature.
