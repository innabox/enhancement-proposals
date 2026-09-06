# NetBox Inventory Backend for Bare Metal as a Service

| Field       | Value   |
|-------------|---------|
| Author(s)   | Menny Aboush |
| Jira        | https://redhat.atlassian.net/browse/OSAC-1610 |
| Date        | 2026-09-06 |

## Problem Statement

A sovereign-cloud operator runs NetBox as their authoritative source of truth for physical infrastructure — devices, their capabilities, power management addresses, and availability. Today, OSAC cannot allocate bare-metal hosts directly from that NetBox inventory, forcing the operator to maintain a separate inventory system as a second source of truth. This creates data inconsistency, operational burden during host lifecycle changes (adding, decommissioning, updating capability metadata), and risk of misalignment between the operator's primary system and OSAC's view.

## In Scope

- BareMetalInstance provisioning and deprovisioning completes end-to-end against NetBox inventory, with clear status visibility at each stage.
- NetBox backend is selectable via operator configuration.
- Tenant Users can request bare-metal hosts by label selector and OSAC transparently allocates them from NetBox without exposing NetBox details to the user.
- Cloud Infrastructure Admins can configure NetBox as the inventory backend so that the system discovers available hosts and provisions them without requiring changes to tenant-facing workflows.
- Lifecycle states (provisioning, ready, deprovisioning, deleted) accurately reflect the actual state at each stage.
- E2E tests validate the full BareMetalInstance lifecycle with NetBox as the inventory source.
- Power management and host readiness are handled independently of inventory selection.

## Out of Scope

- **OS provisioning and image selection** — NetBox supplies hardware inventory only. OSAC's existing OS provisioning pipeline is orthogonal to this integration.
- **NetBox device management** — adding, removing, or editing devices in NetBox is not an OSAC responsibility. The operator manages their NetBox inventory independently.
- **UI/Enclave configuration** — inventory backend selection is tracked separately.
- **Multi-backend deployments in a single cluster** — each deployment uses one inventory backend.
- **Status reporting back to NetBox** — OSAC does not write provisioning status or lifecycle events back to NetBox. Only the assignment identifier is recorded.
- **Health checks on assigned nodes** — OSAC does not periodically verify that assigned nodes still exist in NetBox. If a node is removed from NetBox while assigned, OSAC does not immediately detect the failure.
- **Admin host-listing / inventory visibility in the OSAC API** — surfacing which hosts are available/claimed across backends is addressed separately.

## User Stories

### Cloud Infrastructure Admin

- As a Cloud Infrastructure Admin, I want to configure NetBox as the inventory backend so that OSAC discovers and provisions bare metal hosts from my NetBox infrastructure.

- As a Cloud Infrastructure Admin, I want bare metal hosts to be selected according to the capability labels I have defined in my infrastructure so that tenant requests are matched to appropriate hosts.

- As a Cloud Infrastructure Admin, I want clear error messages when the inventory backend is unreachable so that I can diagnose connectivity issues without inspecting internal logs.

### Cloud Provider Admin

- As a Cloud Provider Admin, I want BareMetalInstance requests to be fulfilled without exposing the inventory backend to other users so that the backend is an infrastructure concern, not a user concern.

### Tenant User

- As a Tenant User, I want to request a bare-metal host by specifying required capabilities and have OSAC allocate it transparently.

- As a Tenant User, I want BareMetalInstance lifecycle states to accurately reflect provisioning progress so that I can monitor host preparation.

- As a Tenant User, I want to deallocate a bare-metal host so it becomes available for future allocations.

## Assumptions

- Cloud Infrastructure Admins pre-register bare metal hosts in NetBox before OSAC operates against them (Day-0 prerequisite).
- Each deployment uses a single inventory backend.
- The operator has populated NetBox hosts with labels or attributes sufficient to distinguish host pools for allocation.
- NetBox API is reachable from the OSAC control plane.

## Dependencies

- **Pluggable backend interface (OSAC-1032)** — the NetBox backend registers against the existing inventory interface.
- **Host readiness and power management** — independent of inventory selection; existing platform mechanisms are used.
- **Label-selector contract** — consistent across all inventory backends.
- **BareMetalInstance API** — tenant-facing API remains unchanged; NetBox is transparent to users.

## Acceptance Criteria

- [ ] A Cloud Infrastructure Admin can configure the operator to use NetBox as the inventory backend and the system connects successfully.
- [ ] A Cloud Infrastructure Admin can provision a BareMetalInstance and the system selects an available host from NetBox inventory matching the requested labels.
- [ ] During host preparation, the BareMetalInstance status shows a clear message indicating the host is being readied.
- [ ] When host preparation fails, the host is released back to NetBox's available pool.
- [ ] A provisioned BareMetalInstance transitions through provisioning, ready, deprovisioning, and deleted states with accurate status messages.
- [ ] When a BareMetalInstance is deleted, the host is released back to NetBox's available pool for reuse.
- [ ] When NetBox is unreachable, the BareMetalInstance status shows a clear error identifying the inventory backend as the failing component.
- [ ] No tenant-identifying data appears in NetBox — only the assignment identifier is stored.
- [ ] NetBox is transparent to tenants — Tenant Users and Tenant Admins see no difference between NetBox-backed and other instances.
- [ ] E2E tests covering the full BareMetalInstance lifecycle with NetBox pass in CI.

## Non-Functional Requirements

- **Tenant isolation:** Only the assignment identifier is stored in NetBox. No tenant-identifying data is written to NetBox. NetBox is transparent to Tenant Admins and Tenant Users.
- **Inventory independence:** Networking and storage are independent of the inventory backend. The existing OSAC infrastructure stack handles all platform operations.
- **Documentation:** Documentation describes how to configure OSAC to use the NetBox backend, including any required prerequisites.

## Risks

- **Host removed from NetBox while assigned.** If a NetBox admin removes a host from NetBox while it is assigned to a BareMetalInstance, the BareMetalInstance does not immediately detect the failure. This is a known limitation; periodic health checks are a future enhancement.
