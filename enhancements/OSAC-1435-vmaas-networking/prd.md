# VMaaS Networking — Single-Interface VMs and Auto External Access

| Field       | Value   |
|-------------|---------|
| Author(s)   | Dan Manor (dmanor@redhat.com) |
| Jira        | https://redhat.atlassian.net/browse/OSAC-1435 |
| Date        | 2026-09-10 |

> This PRD is an expansion of the [Unified Networking PRD](/enhancements/OSAC-1433-unified-networking/prd.md), scoped to the specific service type. The unified PRD defines the shared networking resources and operation contract; the [Unified Networking design](/enhancements/OSAC-1433-unified-networking/design.md#deployment-topology) defines the supported IPv4-only, connected single-hub boundary. This document defines the VMaaS-specific requirements and user stories.

## 1. Problem Statement

VMaaS needs a stable list-shaped attachment API for future growth, but the
currently supported VM contract is one interface or none at request time.
Creating a VM with external access requires manual IP allocation and NAT
configuration, forcing tenants to understand inbound and outbound routing
before provisioning their first reachable VM. The default networking
experience varies across resource types — some resources have simplified
creation flows while VMs require explicit networking details on every create.

## 2. Goals and Non-Goals

### 2.1 Goals

- A tenant can create a VM with zero or one list-shaped network attachment; a single attachment is implicitly primary
- A tenant can create a VM with `--external-ip-attachment` and have the system allocate an external IP and attach it automatically for inbound access
- A tenant can create a VM without specifying networking details — the system uses the tenant's default subnet and security group
- The platform prevents VM creation in deployments that do not support virtualization

### 2.2 Non-Goals

- Cluster or bare-metal server networking (this PRD covers VMs only; clusters and bare-metal servers are addressed in separate enhancements)
- Multi-interface VMs and multiple network interfaces for bare-metal servers are unsupported in the current contracts

## 3. User Stories

### Tenant User Stories

- As a Tenant User, I want to create a VM with one network attachment using a list-shaped field, so that the API remains list-shaped for compatibility
- As a Tenant User, I want the single network interface to be implicitly primary, so that it provides the VM's default gateway and DNS configuration
- As a Tenant User, I want to create a VM with `--external-ip-attachment`, so that the VM is externally reachable without manually allocating an IP
- As a Tenant User, I want to create a VM without specifying network details, so that the system uses my default subnet and security group and I can get started quickly
- As a Tenant User, I want clear error messages when I try to create a VM in a deployment that only supports bare-metal servers, so that I understand the limitation and can choose a different deployment

### Tenant Admin Stories

- As a Tenant Admin, I want to inspect the default networking resources (subnet, security group) used when VMs are created without explicit network configuration
- As a Tenant Admin, I want to see which subnet and security groups each VM is attached to, and the IP address allocated to its network attachment, so I can audit my organization's network topology

### Cloud Infrastructure Admin Stories

- As a Cloud Infrastructure Admin, I want to configure which deployments support VM provisioning, so that VM creation is rejected with a clear error in BM-only deployments

### Cloud Provider Admin Stories

- As a Cloud Provider Admin, I want visibility into auto-provisioned networking resources (external IPs), so I can monitor capacity and troubleshoot connectivity issues

## 4. Requirements

### 4.1 Functional Requirements

#### Single-Interface VMs

- **FR-1:** The `compute_network_attachments` list accepts zero or one entry. A request with more than one entry is rejected. [User]
- **FR-2:** When the list contains one attachment, omission or `primary: true` makes it primary; explicit `primary: false` is rejected. Multi-interface primary selection is unsupported. [User]

#### Optional Network Configuration with Defaults

- **FR-3:** Network configuration is optional when creating a VM. When the
  attachment list is omitted or empty, the system uses both tenant defaults.
  When an attachment omits only its subnet or SecurityGroup list, only that
  field is defaulted; supplied fields are preserved. The resolved
  configuration is stored with the VM so the VM is self-describing after
  creation. [User]

#### Auto External IP

- **FR-4:** VMs support `--external-ip-attachment`. When specified, the
  system auto-selects the IPv4 ExternalIPPool with the most available
  capacity, reserves capacity, and creates a Pending ExternalIP and
  ExternalIPAttachment for the VM's single network attachment. Fabric
  allocation, VM IP discovery, DNAT programming, and activation are
  asynchronous; the ExternalIP and attachment are cleaned up when the VM is
  deleted. Default networking resources (virtual networks, subnets, security
  groups, NATGateway) are not cleaned up as they are tenant-scoped and shared
  across resources. [User]

#### IP Address Discovery

- **FR-5:** The allocated IP address for the single network attachment is visible in the VM status after provisioning completes. When an external IP is attached to a VM, inbound traffic to the external IP is routed to that attachment's IP. [User]

#### Deployment Validation

- **FR-6:** When a VM is created, the platform validates that the target deployment supports virtualization. If the deployment only supports bare-metal servers, the create request fails with a clear error message explaining the limitation. [User]

#### Backward Compatibility

- **FR-7:** Existing VMs continue to work without changes. The platform accepts both old and new network configuration formats during a transition period. If both formats are provided, the create request fails with an error. If the old format is provided alone, it is converted to the new format automatically. [User]

- **FR-8:** The complete resolved network attachment list on a ComputeInstance,
  including every Subnet, SecurityGroup, and `primary` value, is immutable
  after creation. Update and patch requests for these fields are rejected;
  changing network configuration requires deleting and recreating the VM.
  Standard metadata and non-network VM fields remain governed by their own
  contracts. [User]

### 4.2 Non-Functional Requirements

- **NFR-1:** Pool capacity validation and creation of Pending ExternalIP and
  ExternalIPAttachment records complete synchronously within the create request.
  Fabric allocation,
  VM IP discovery, DNAT programming, and the transition to Ready are
  asynchronous. The ExternalIP transitions `Pending -> Allocated`; the
  ExternalIPAttachment transitions `Pending -> Ready` only after the VM
  attachment IP is available and DNAT succeeds. If no pool has available
  capacity, the create request fails atomically with a clear error. [User]

## 5. Acceptance Criteria

- [ ] A Tenant User can create a VM with zero or one `--network-attachment` value while the API field remains list-shaped
- [ ] Creating a VM with more than one network attachment returns a single-interface validation error
- [ ] A Tenant User can create a VM with `--external-ip-attachment` and no explicit network configuration — the VM is created on the default subnet with an auto-provisioned external IP for inbound access
- [ ] Creating a VM in a bare-metal-only deployment returns an error with a clear message
- [ ] A single-interface VM is provisioned with its attachment operational and providing the default gateway
- [ ] VM status shows the allocated IP address for the single network attachment after provisioning completes
- [ ] External IP attachment with a VM target routes inbound traffic to the VM's attachment IP
- [ ] Auto-created external IPs and attachments are visible in list views with a `osac.openshift.io/auto-created: "true"` label
- [ ] Deleting a VM with auto-provisioned external IP causes the auto-created IP and attachment to be cleaned up automatically
- [ ] Creating a VM using the old network configuration format succeeds and is internally converted to the new format
- [ ] Creating a VM with both old and new configuration formats returns an error
- [ ] Creating a VM with `primary: false` on its sole attachment returns a single-interface validation error
- [ ] Updating or patching a VM's network attachment list or any attachment field is rejected; changing it requires delete and recreate under the [unified networking operation contract](/enhancements/OSAC-1433-unified-networking/prd.md#network-operation-contract)

## 6. Assumptions

- The tenant has default networking resources (virtual network, subnet, security group) pre-created by the platform (see Default Networking PRD). If defaults are not configured, creating a VM without explicit network configuration fails with a clear error.
- The target deployment supports virtualization. Bare-metal-only deployments do not support VMs.

## 7. Dependencies

- **Unified Networking EP** — this PRD builds on the unified networking resource model (virtual networks, subnets, security groups, external IPs, NAT gateways) defined in the [Unified Networking EP](/enhancements/OSAC-1433-unified-networking)
- **Default Networking PRD** — default subnet and security group selection behavior defined in [Default Networking PRD](/enhancements/OSAC-1433-default-networking)
- **OSAC-1712 (automatic pool selection)** — the auto external IP pool selection reuses the identical algorithm: pick the IPv4 pool with the most available capacity
- **OSAC-1511 or OSAC-1717** — a virtualization platform integration must exist for the platform to provision overlay networks on hosting clusters
- **OSAC-1457, OSAC-1458, OSAC-1460** — core provisioning infrastructure (in progress)
- **OSAC-1459** — multi-job tracking (new, required for subnet provisioning to trigger multiple backend jobs)

## 8. Risks

### 8.1 Virtualization platform integration blocked or delayed

- **Owner:** Engineering / Product
- **Mitigation:** OSAC-1511 and OSAC-1717 are both in spike/blocked state. If neither lands, VM networking cannot function. Prioritize unblocking one of these dependencies or accept that VMs remain unavailable until a virtualization platform integration exists.

### 8.2 Multi-job tracking not implemented

- **Owner:** Platform team
- **Mitigation:** OSAC-1459 is a prerequisite for subnet provisioning to trigger multiple backend jobs. If not implemented, subnet provisioning can only call one backend system — defer multi-backend support or accept single-backend-only subnet provisioning.

### 8.3 External IP pool exhaustion

- **Owner:** Cloud Provider Admin
- **Mitigation:** Pool capacity visible in status; clear error directs tenant to explicit allocation from another pool

## 9. Open Questions

### ~~9.1 Should capacity exhaustion return an API error or create a failed resource?~~ — Resolved

Resolved: Return error, no resource persisted.
