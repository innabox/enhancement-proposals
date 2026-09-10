# CaaS Networking — Unified API with Auto External Access

| Field       | Value   |
|-------------|---------|
| Author(s)   | Dan Manor (dmanor@redhat.com) |
| Jira        | https://redhat.atlassian.net/browse/OSAC-1436 |
| Date        | 2026-07-08 |

> This PRD is an expansion of the [Unified Networking PRD](/enhancements/OSAC-1433-unified-networking/prd.md), scoped to the specific service type. The unified PRD defines the shared networking resources and operation contract; the [Unified Networking design](/enhancements/OSAC-1433-unified-networking/design.md#deployment-topology) defines the supported IPv4-only, connected single-hub boundary. This document defines the CaaS-specific requirements and user stories.

## 1. Problem Statement

Cluster provisioning has no networking configuration. Tenants cannot choose which subnet their cluster nodes use, cannot place two clusters in the same virtual network, and cannot isolate them in separate networks. All clusters are placed on a single deployment-wide networking backend with zero tenant control. Cluster networking is completely divergent from VM and bare-metal server workflows, requiring separate knowledge and tools.

## 2. Goals and Non-Goals

### 2.1 Goals

- A tenant can create a cluster with explicit network configuration, specifying which subnet and security groups to use for cluster nodes
- A cluster uses a single network attachment — one subnet for all node sets. The system automatically determines which physical interface to use for each node set from its BareMetalInstanceType network ports
- Tenants can request automatic external IP attachment for cluster API server and ingress endpoints with `--external-ip-attachment`, without pre-creating external IP resources
- When the network attachment is omitted or empty, the system applies both
  tenant defaults; when only one field is missing, only that field is defaulted
- Cluster status exposes API server and ingress endpoint addresses after provisioning completes
- The system provisions suitable bare-metal workers on demand through BMaaS; BMaaS completes the provisioning-network handoff before cluster installation proceeds
- Auto-provisioned external IPs and external IP attachments are cleaned up when the cluster is deleted
- BareMetalInstanceTypes provide structured network port information that the system uses to configure worker connectivity

### 2.2 Non-Goals

- VM-based cluster node sets (deferred — bare-metal only for initial release)
- DNS API for cluster endpoints (DNS record creation remains template-based until DNS API is implemented)
- Per-node-set subnet placement (all node sets share the cluster's single network attachment)
- Multi-NIC cluster nodes (one attachment per cluster; the system automatically determines which physical interface to use for each node set from its BareMetalInstanceType)

## 3. User Stories

### Tenant User Stories

- As a Tenant User, I want to create a cluster with explicit network configuration so that I can place it on a specific subnet with specific security group rules
- As a Tenant User, I want my cluster's node sets to automatically use the correct physical interface from their BareMetalInstanceType so that network connectivity is configured without manual interface specification
- As a Tenant User, I want to create a cluster with `--external-ip-attachment` so that the system provisions external IPs for both the API server and ingress and the cluster is externally reachable in a single API call
- As a Tenant User, I want to create a cluster without specifying network configuration and have it placed on my default subnet with my default security groups
- As a Tenant User, I want to see my cluster's API server and ingress endpoint addresses in the cluster status so that I can access the cluster
- As a Tenant User, I want auto-provisioned networking resources to be automatically cleaned up when I delete my cluster so that I do not accumulate orphaned resources

### Tenant Admin Stories

- As a Tenant Admin, I want to place multiple clusters in the same virtual network so that they can communicate privately with each other and with my VMs
- As a Tenant Admin, I want to isolate clusters in separate virtual networks so that I can enforce network boundaries between different projects or teams

### Cloud Infrastructure Admin Stories

- As a Cloud Infrastructure Admin, I want to define structured network port metadata in BareMetalInstanceTypes so that the system can automatically configure worker connectivity

### Cloud Provider Admin Stories

- As a Cloud Provider Admin, I want visibility into whether cluster hosts were successfully selected and network connectivity configured so I can troubleshoot provisioning failures

## 4. Requirements

### 4.1 Functional Requirements

#### Network Configuration

- **FR-1:** Cluster creation supports a single network attachment configuration specifying a subnet and security groups. The attachment applies to the entire cluster — all node sets share the same subnet. The system determines which physical network interface to use for each node set from its BareMetalInstanceType's `network_ports`. The complete attachment and every field, including security groups, are immutable after creation; changing them requires deleting and recreating the Cluster. [User]

#### Optional Network Configuration with Defaults

- **FR-2:** The network configuration on cluster creation is optional. When
  omitted or empty, the system applies both tenant defaults. When only one
  attachment field is missing, only that field is defaulted. The resolved
  configuration is stored so the cluster is self-describing after creation. [User]

#### Auto External IP

- **FR-3:** Cluster creation supports `--external-ip-attachment`. When enabled, the system allocates external IPs for both the API server and ingress from available IP pools before provisioning begins. External IPs and their attachments are labeled as auto-provisioned. The attachments are activated once the cluster's API server and ingress endpoints are available. [User]

#### Endpoint Discovery

- **FR-4:** Cluster status exposes API server and ingress endpoint addresses. The system discovers these addresses during cluster provisioning and makes them available in the cluster status. [User]

#### External IP Activation

- **FR-5:** When automatic external IP allocation is enabled, the system creates external IP attachments before provisioning begins. After the cluster's API server and/or ingress endpoints are available, the system configures inbound routing from the external IPs to the endpoints and activates the attachments. [User]

#### Worker Provisioning and Network Configuration

- **FR-6:** The BareMetalWorkerReconciler creates a BareMetalInstance through the BMaaS private API for each requested worker, using the node set's BareMetalInstanceType and availability constraints. BMaaS reserves the host and owns its provisioning lifecycle. [User]

#### Network Connectivity Setup

- **FR-7:** BMaaS provisions each worker on the provisioning network, then moves the selected fabric port to the tenant subnet, reboots the host, and discovers its tenant-network IP before the worker joins cluster installation. [User]

#### Cluster Provisioning

- **FR-8:** Cluster provisioning creates the HostedCluster and NodePools while the BareMetalWorkerReconciler provisions workers through BMaaS. The process allocates IP addresses for the API server and ingress endpoints, performs DNS record creation, and makes the endpoint addresses available in cluster status. [User]

#### BareMetalInstanceType Network Ports

- **FR-9:** BareMetalInstanceTypes include structured network port information (name, role, type, speed). The system automatically determines which physical interface to use for each node set from the first port with role `fabric`. [User]

#### Bare-Metal Only

- **FR-10:** Cluster node sets are bare-metal only for the initial release. VM-based cluster node sets are architecturally supported but deferred. [User]

#### Auto-Provisioned Resource Cleanup

- **FR-11:** Auto-provisioned networking resources (external IPs, external IP attachments) are labeled as auto-provisioned. When a cluster is deleted, the system cleans up auto-provisioned resources in reverse order: external IP attachments first, then external IPs. Manually created resources are not cleaned up. Default networking resources (virtual networks, subnets, security groups, NATGateways) are not cleaned up as they are tenant-scoped and shared across resources. [User]

### 4.2 Non-Functional Requirements

- **NFR-1:** Automatic external IP allocation and endpoint discovery complete synchronously within the cluster creation flow. Endpoint addresses are available in cluster status during provisioning, not minutes later.

## 5. Acceptance Criteria

- [ ] A Tenant User can create a cluster with network configuration specifying a subnet and security groups, and the cluster nodes are provisioned on the specified subnet
- [ ] A Tenant User can create a cluster with a single network attachment and multiple node sets, and all node sets are provisioned on the same subnet with the appropriate physical interface automatically selected from each node set's BareMetalInstanceType
- [ ] A Tenant User can create a cluster with `--external-ip-attachment` and no explicit network configuration — the cluster is created on the default subnet with auto-provisioned external IPs for both API and ingress
- [ ] Cluster status exposes API server and ingress endpoint addresses after provisioning completes
- [ ] Auto-created external IP attachments activate after endpoint addresses are available and inbound routing is configured
- [ ] The BareMetalWorkerReconciler creates workers through BMaaS, and BMaaS completes each provisioning-network handoff before the worker joins cluster installation
- [ ] Auto-created external IPs and external IP attachments are labeled as auto-provisioned and visible in list views
- [ ] Deleting a cluster with auto-provisioned resources causes the auto-created external IPs and external IP attachments to be cleaned up
- [ ] The system determines which physical network interface to use from the node set's BareMetalInstanceType network ports
- [ ] Updating or patching the Cluster network attachment or any of its fields is rejected under the [unified networking operation contract](/enhancements/OSAC-1433-unified-networking/prd.md#network-operation-contract)

## 6. Assumptions

- The tenant has default networking resources (virtual network, subnet, security group) pre-created. If defaults are not configured, creating a cluster without explicit network configuration fails with a clear error.
- The deployment's NetworkClass configures at least one manager that supports
  VirtualNetworks, Subnets, SecurityGroups, ExternalIPs, and
  ExternalIPAttachments. NATGateway is required only when the configured
  manager capability advertises it; K8s-only OVN deployments do not support
  NATGateway.
- BareMetalInstanceTypes have structured network port configuration. The system uses this to determine which interface to configure for each subnet.

## 7. Dependencies

- **Unified Networking EP** — this PRD builds on the unified networking resource model (virtual networks, subnets, security groups, external IPs, external IP attachments, NAT gateways) defined in the [Unified Networking EP](/enhancements/OSAC-1433-unified-networking)
- **Default Networking PRD** — default subnet and security group selection behavior defined in [Default Networking PRD](/enhancements/OSAC-1433-default-networking)

## 8. Risks

### 8.1 Worker provisioning and interface resolution complexity

- **Owner:** Platform team
- **Mitigation:** BMaaS worker creation must account for BareMetalInstanceType matching, availability, and labels; interface resolution uses the first `fabric` port. If not implemented correctly, worker provisioning cannot proceed. Thorough testing required.

### 8.2 Endpoint discovery delay or failure

- **Owner:** Platform team
- **Mitigation:** If endpoint addresses are not discovered correctly, they will not appear in cluster status, and external IP attachments will not activate. Monitor endpoint discovery reliability and address discovery mechanisms.

### 8.3 BareMetalInstanceType network ports not populated

- **Owner:** Cloud Infrastructure Admin
- **Mitigation:** If BareMetalInstanceTypes do not have a valid `fabric` port, interface determination will fail. Ensure the catalog profiles are populated before cluster networking goes live.

### 8.4 IP address pool configuration for API and ingress endpoints

- **Owner:** Platform team / Cloud Infrastructure Admin
- **Mitigation:** The cluster provisioning system needs IP address pools configured for the subnet so it can allocate addresses for API server and ingress endpoints. Clarify whether this is created when the subnet is created or during cluster provisioning.

## 9. Open Questions

### ~~9.1 How does the system select hosts?~~ — Resolved

Resolved: The BareMetalWorkerReconciler creates workers through the BMaaS private API, which selects hosts from BareMetalInstanceType and availability constraints. Agents are correlated to BMIs by MAC after provisioning.

### ~~9.2 How is host network state configuration managed?~~ — Resolved

Resolved: DHCP handles all host-side networking. The host receives IP, gateway, prefix, and DNS from the fabric's DHCP server. No static configuration or NMState needed.

### ~~9.3 How are IP address pools for cluster endpoints configured?~~ — Resolved

Resolved: The system creates IP address pools for cluster endpoint allocation at subnet creation time, reserving a sub-range of the subnet CIDR. The DHCP assignment range excludes this sub-range to prevent overlap.
