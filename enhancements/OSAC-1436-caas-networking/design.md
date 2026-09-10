---
title: caas-networking
authors:
  - dmanor@redhat.com
creation-date: 2026-07-08
last-updated: 2026-09-10
tracking-link:
  - https://redhat.atlassian.net/browse/OSAC-1436
prd: "prd.md"
see-also:
  - "Unified Networking: /enhancements/OSAC-1433-unified-networking"
  - "Default Networking: /enhancements/OSAC-1433-default-networking"
  - "CaaS BM Worker Provisioning: /enhancements/OSAC-2135-caas-bare-metal-worker-provisioning"
replaces:
  - N/A
superseded-by:
  - N/A
---

# CaaS Networking — Cluster Networking via OSAC Networking API

CaaS networking provides tenant-controlled cluster node networking via VirtualNetwork + Subnet attachments, BM-based node sets with fabric interface resolution from BareMetalInstanceType, MetalLB VIP provisioning, and auto-provisioned external access (ExternalIP + ExternalIPAttachment) for cluster API and ingress endpoints.

## Summary

This document is a per-service expansion of the [Unified Networking EP](/enhancements/OSAC-1433-unified-networking/design.md). The unified EP defines the shared architecture (NetworkClass, dispatcher, infrastructure-agnostic subnets, resource hierarchy); this document defines how CaaS consumes that architecture.

Shared field types, formats, presence rules, allowed values, and validation
are defined by the [Unified Networking field contract](/enhancements/OSAC-1433-unified-networking/design.md#field-types-formats-and-validation).

The shared networking resource model, IPv4-only scope, and connected
single-hub deployment boundary are defined by the [Unified Networking
design](/enhancements/OSAC-1433-unified-networking/design.md#deployment-topology).
The shared operation contract is defined by [Supported Operations and
Immutability](/enhancements/OSAC-1433-unified-networking/design.md#supported-operations-and-immutability).

Cluster provisioning uses the OSAC Networking API for all networking lifecycle — tenants place clusters on their VirtualNetworks via `network_attachment`, the `BareMetalWorkerReconciler` creates on-demand `BareMetalInstance` objects via the BMaaS private gRPC API (BMaaS owns the fabric port move and IP assignment as part of BMI provisioning), and a VIP feedback loop enables auto-provisioned external access for cluster API and ingress endpoints. See [PRD](prd.md) for detailed requirements and [OSAC-2135](/enhancements/OSAC-2135-caas-bare-metal-worker-provisioning/design.md) for the full provisioning design.

## Motivation

Clusters require tenant-controlled networking to enable:
- Placing clusters on shared or isolated VirtualNetworks
- Automatic agent port configuration (provisioning network → tenant network) during cluster creation
- VIP feedback loop for cluster API/ingress endpoints to enable DNAT via ExternalIPAttachment
- Auto external access (ExternalIP + ExternalIPAttachment) for single-call cluster provisioning with inbound connectivity

### Goals

- Move cluster networking lifecycle to the OSAC Networking API (VirtualNetwork, Subnet, SecurityGroup)
- Tenant-controlled cluster node subnet placement via `network_attachment` field on ClusterSpec
- BM-based node sets with fabric interface resolution from BareMetalInstanceType (OSAC-1201)
- On-demand BareMetalInstance creation via BMaaS private gRPC API; BMaaS owns the fabric port move and IP assignment as part of BMI provisioning (OSAC-2135)
- VIP feedback loop: template provisions MetalLB VIPs → ClusterOrder status → fulfillment-service → Cluster → ExternalIPAttachment controller
- Auto ExternalIP attachment (`auto_external_ip_attachment`) for single-call API/ingress external access
- Remove step collections (`netris.steps`, `agentless_net.steps`) from CaaS networking

### On-Demand BMI Provisioning Model (OSAC-2135)

Per [OSAC-2135](/enhancements/OSAC-2135-caas-bare-metal-worker-provisioning/design.md), CaaS provisions bare-metal worker nodes **on demand** via the BMaaS private gRPC API — the static pre-boot agent pool is removed. A dedicated `BareMetalWorkerReconciler` in osac-operator creates `BareMetalInstance` objects for each requested worker. Each BMI references a RHCOS DiskImage and carries discovery ignition inline from a cluster-specific InfraEnv.

**BMaaS owns the full provisioning lifecycle** including networking:
1. BMaaS provisions the host on the **provisioning network** (inventory → OS provisioning via DiskImage + ignition)
2. BMaaS moves the host's fabric port **provisioning network → tenant network** (`reconcileNetworking` dispatches `move_network_attachment` after provisioning completes)
3. BMaaS reboots the host so the OS re-DHCPs on the tenant network (`reconcileReboot`)
4. BMaaS discovers the tenant-network IP via DHCP lease query (`reconcileIPDiscovery`)
5. The full assisted-installer cluster installation begins on the tenant network: the host registers as an Agent with assisted-service, performs hardware discovery, runs the OpenShift installation, and reports progress — all from scratch on the tenant network

The `BareMetalWorkerReconciler` reads the first entry in `ClusterOrder.spec.networkAttachments` (a `ClusterNetworkAttachment` carrying `subnetRef` + `securityGroupRefs`) and enriches it into a per-BMI `BareMetalNetworkAttachment` using the immutable `fabric_interface` stored on the node set by the fulfillment-service. CaaS never dispatches `move_network_attachment` directly — that is BMaaS's responsibility as part of BMI provisioning. On cluster deletion, the controller calls `BareMetalInstances.Delete`; BMaaS handles full host cleanup including returning the fabric port to the provisioning network.

### Non-Goals

- VMaaS or BMaaS networking (this EP covers CaaS only)
- VM-based cluster node sets (v0.2 supports BM node sets only; VM worker nodes require HyperShift ↔ CUDN integration not in scope)
- DNS API (DNS record creation stays inline in the template until DNS API is implemented)
- Multi-NIC cluster nodes (v0.2: one attachment per cluster → one subnet; each node set resolves its own fabric interface from its BareMetalInstanceType)
- Dispatcher infrastructure implementation (deferred to Unified Networking EP implementation)

## Proposal

### Workflow Description

#### Phase 1: Tenant Creates Networking Resources

These steps are identical to VMaaS/BMaaS — the networking API is uniform.

1. **Create VirtualNetwork:**
   ```bash
   osac create virtualnetwork --cidr 10.0.0.0/16 --name my-net
   ```
   Dispatcher → the configured network manager's `create_virtual_network` operation

2. **Create Subnet:**
   ```bash
   osac create subnet --virtual-network my-net --cidr 10.0.1.0/24 --name my-subnet
   ```
   Dispatcher → the configured manager(s) create the subnet backend(s); when both managers are configured, the Fabric Manager creates the fabric segment and the K8s Manager creates the overlay

3. **Create SecurityGroup:**
   ```bash
   osac create security-group --virtual-network my-net --name my-sg \
     --rule "action:allow,direction:ingress,protocol:tcp,port:443,source-cidr:0.0.0.0/0"
   ```
   Dispatcher → the configured network manager's `create_security_group` operation

#### Phase 2: Tenant Creates Cluster

4. **Create Cluster:**
    ```bash
    # Explicit networking:
    osac create cluster --template ocp_4_17_small \
      --network-attachment subnet=my-subnet,security-groups=my-sg \
      --node-set compute=large,size=3 --name my-cluster

    # Or with defaults + auto external access:
    osac create cluster --template ocp_4_17_small \
      --external-ip-attachment \
      --node-set compute=large,size=3 --name my-cluster
    ```

5. **fulfillment-service:**
    - If `network_attachment` is omitted or an empty message: populates both tenant defaults. If present with only one field, defaults only the missing subnet or SecurityGroup list (see Default Networking PRD)
    - Validates network_attachment:
      - Subnet exists, is Ready
      - SecurityGroups exist, are Ready, belong to same VN
    - For each node_set: resolves `baremetal_instance_type` → BareMetalInstanceType → picks first port with `role=fabric` from `network_ports[]` and stores as `fabric_interface` on the node set definition in the ClusterOrder spec
    - If `auto_external_ip_attachment == true`: auto-selects ExternalIPPool, creates two ExternalIPs (API + ingress, each labeled `osac.openshift.io/auto-created: "true"` and `osac.openshift.io/auto-created-for: <cluster-id>`) and two ExternalIPAttachments (labeled `osac.openshift.io/auto-created: "true"`) — all in the same DB transaction, all starting in **Pending** state. Pool capacity is decremented atomically; if the pool is exhausted, the API call fails and no resources are persisted. The ExternalIPAttachments transition to Ready once VIPs are populated (see Phase 3). See [Unified Networking — Auto-provisioning lifecycle](/enhancements/OSAC-1433-unified-networking/design.md#external-access-same-for-all-resource-types) for the shared two-phase flow and phased requeue cleanup pattern.
    - Creates Cluster record with empty `api_endpoint` / `ingress_endpoint`
    - Creates ClusterOrder CR with the resolved attachment in `networkAttachments[0]` in spec

6. **osac-operator ClusterOrder controller:**
    - Creates namespace, ServiceAccount, RoleBindings (same as today)

    **a. Triggers AAP workflow** to create the HostedCluster and NodePool CRs.

    **b. `BareMetalWorkerReconciler`** (runs after the ClusterDeployment exists, per OSAC-2135):
    - Creates a cluster-specific `InfraEnv` CR for discovery ignition
    - For each bare-metal worker requested, creates a `BareMetalInstance` via the BMaaS private gRPC API, passing `network_attachments` enriched from `ClusterOrder.spec.networkAttachments[0]` with the immutable `fabric_interface` already stored on the node set by the fulfillment-service (step 5) — the controller does not re-resolve from BareMetalInstanceType to avoid divergence if the profile changes after cluster creation
    - BMaaS provisions each host (DiskImage + ignition), moves its fabric port from provisioning network → tenant network, reboots, and discovers the tenant-network IP via DHCP lease query — all as part of BMI provisioning (inventory → provisioning → networking → reboot → IP discovery)
    - The controller correlates registered Agents to BMIs via MAC address and labels them for NodePool selection
    - If an Agent does not register within a configurable timeout (default: 30 minutes), the controller sets the worker phase to `Failed` with reason `AgentRegistrationTimeout` and retries with escalating backoff (see OSAC-2135 for full retry logic)

    > **Tenant-network reachability prerequisites.** After the port move, cluster installation runs entirely on the tenant network. The tenant V-Net and the management cluster are in separate VPCs with no direct network path — all communication between them traverses the external network: outbound via NATGateway/SNAT from the tenant V-Net, inbound to the management cluster's external ingress. This applies to assisted-service registration, container image pulls, and post-installation kubelet-to-kube-apiserver heartbeats. All dependencies (container images, RHCOS, OCP release payload) must be pullable from the tenant network via the same egress path. SecurityGroup egress rules must allow outbound `:443`. `AgentRegistrationTimeout` catches tenant-to-assisted-service egress failures (the agent cannot register if it cannot reach assisted-service). A future disconnected installation flow would pre-stage dependencies locally, removing the egress requirement.

7. **CaaS template creates the HostedCluster + NodePool; BareMetalWorkerReconciler provisions workers.**

    The template's `install.yaml` changes:

    **a. Create HostedCluster + NodePools:**
    - AAP creates HyperShift HostedCluster + NodePool CRs
    - No agent selection or switch port configuration — the `BareMetalWorkerReconciler` handles worker provisioning on-demand via BMaaS (step 6b)
    - Host-side networking handled by DHCP — no NMState or static config needed

    **b. MetalLB VIP provisioning (REPLACES `external_access` step):**

    The VN and Subnet already exist (tenant created them in steps 1-3). External access (ExternalIP, ExternalIPAttachment) is auto-provisioned or managed separately by the tenant. NATGateway is expected to exist on the VN as a default from tenant onboarding, not auto-created per cluster. The template:
    - Creates MetalLB LoadBalancer Services for API server + ingress VIPs
    - MetalLB allocates VIPs from its IPAddressPool (created by k8s_manager at subnet creation)
    - Discovers the allocated VIPs and writes them to ClusterOrder CR status:
      ```yaml
      status:
        apiEndpoint: 10.0.1.200     # MetalLB-allocated API VIP
        ingressEndpoint: 10.0.1.201 # MetalLB-allocated ingress VIP
      ```
    - DNS record creation (stays inline — DNS API is a separate EP)

    **c. Retrieve kubeconfig, wait for nodes + operators (same as today)**

#### Phase 3: VIP Feedback Loop

8. **osac-operator feedback controller** watches ClusterOrder status:
    - Sees `apiEndpoint` and `ingressEndpoint` populated
    - Fires Signal RPC to fulfillment-service

9. **fulfillment-service** re-reads ClusterOrder CR:
    - Syncs `api_endpoint` and `ingress_endpoint` from ClusterOrder status to the Cluster object

10. **ExternalIPAttachment controller** reconciles the API attachment:
    - Checks two preconditions before dispatching (requeues if either is not met):
      1. ExternalIP must be Allocated (have an allocated address from the fabric manager)
      2. ClusterOrder must have `status.apiEndpoint` populated (VIP allocated by MetalLB, discovered by template in step 7b)
    - Once both are met: reads ClusterOrder's `apiEndpoint` → 10.0.1.200
    - Calls the configured network manager's external-IP attachment operation
    - The configured network manager creates DNAT: api-ip (203.0.113.10) → 10.0.1.200
    - ExternalIPAttachment transitions from **Pending** to **Ready**

11. Same for ingress ExternalIPAttachment:
    - Requeues until ExternalIP is Allocated AND ClusterOrder's `status.ingressEndpoint` is populated
    - Reads ClusterOrder's `ingressEndpoint` → 10.0.1.201
    - Creates DNAT: ingress-ip (203.0.113.11) → 10.0.1.201
    - Transitions to **Ready**

#### Deletion (reverse order)

12. **Delete Cluster:**
    - **Auto-provisioned cleanup (osac-operator ClusterOrder controller):** Phased requeue: deletes ExternalIPAttachments first (by target reference), waits, then deletes ExternalIPs (by `auto-created-for` label), waits, then proceeds. See [Unified Networking — Auto-provisioned resource cleanup](/enhancements/OSAC-1433-unified-networking/design.md#external-access-same-for-all-resource-types).
    - **Manually created resources are NOT cleaned up** — tenant manages their lifecycle. Manually created ExternalIPAttachments transition back to detached / Pending.
    - **Default networking resources (VN, Subnet, SG, NATGateway) are NOT cleaned up** — tenant-scoped and shared.
    - ClusterOrder controller triggers AAP delete workflow
    - CaaS delete template:
      - Deletes MetalLB LoadBalancer Services
      - Deletes HyperShift HostedCluster + NodePools
      - DNS cleanup
    - ClusterOrder finalizer actively deletes every BMI listed in `status.workers[]` via `BareMetalInstances.Delete` on the BMaaS private API (30 s context deadline per call). The call returns once the delete is accepted; BMaaS handles full host cleanup asynchronously (deprovision, fabric port return to provisioning network). The controller retains each worker entry in `status.workers[]` in `Deleting` phase and polls BMI state on subsequent reconciliation cycles until the BMI is confirmed gone — only then is the entry removed. If the deadline is exceeded or the call fails, the controller retries on the next requeue (controller-runtime exponential backoff); `BareMetalInstances.Delete` is idempotent, so retries are safe. The finalizer holds until all `status.workers[]` entries are confirmed deleted. The InfraEnv CR is garbage collected via its ownerReference to the ClusterOrder (see OSAC-2135).
    - Removes ClusterOrder finalizer

13. **Tenant deletes networking resources** (independently, if desired):
    - Delete ExternalIPAttachments → fabric manager removes DNAT rules
    - Delete NATGateway → fabric manager removes SNAT rule
    - Delete ExternalIPs → fabric manager releases IPs
    - Delete SecurityGroup → fabric manager removes ACL rules
    - Delete Subnet → dispatcher calls both managers: fabric manager removes network segment, k8s_manager removes CUDN overlay + MetalLB IPAddressPool from hosting clusters
    - Delete VirtualNetwork → fabric manager removes tenant segment

### BareMetalInstanceType and Interface Resolution

#### BareMetalInstanceType Network Ports

Per [OSAC-2135](/enhancements/OSAC-2135-caas-bare-metal-worker-provisioning/design.md), `HostType` is deprecated and decommissioned — `BareMetalInstanceType` (OSAC-1201) is the sole source of truth for hardware profiles and interface resolution. CaaS `ClusterNodeSet.baremetal_instance_type` references this resource.

```protobuf
message BareMetalNetworkPortSpec {
  string name = 1;        // e.g., "data-0", "data-1", "mgmt-0" — unique within the type
  string role = 2;        // e.g., "fabric", "management", "storage", "lifecycle"
  string type = 3;        // e.g., "Ethernet"
  string speed = 4;       // e.g., "100Gbps", "1Gbps"
}
```

`BareMetalInstanceType` is a bare-metal-only resource (OSAC-1201) — BM vs VM is classified by resource type (`BareMetalInstance` vs `ComputeInstance`), not by the contents of `network_ports`. Every `BareMetalInstanceType` must declare at least one `network_ports` entry with `role=fabric`; a bare-metal profile with no fabric port is rejected at creation time because both the operator (provisioning-network port move) and the default-interface resolution (first `role=fabric` port) depend on it.

Interfaces are ordered. When multiple interfaces share the same role (e.g., two `fabric` interfaces), the first one in the list is the default for that role.

#### How CaaS Uses BareMetalInstanceType

The tenant provides a single `ClusterNetworkAttachment` with `subnet` only — no node_set or interface field. The `BareMetalWorkerReconciler` resolves the interface from the BareMetalInstanceType for each node set:

1. For each node set in the cluster spec (e.g., "gpu"), read `ClusterSpec.node_sets["gpu"].baremetal_instance_type` = "bm-standard"
2. BareMetalInstanceType "bm-standard" has network_ports:
   ```
   [{name: "data-0", role: "fabric", type: "Ethernet", speed: "100Gbps"},
    {name: "data-1", role: "fabric", type: "Ethernet", speed: "100Gbps"},
    {name: "mgmt-0", role: "management", type: "Ethernet", speed: "1Gbps"}]
   ```
3. The controller picks the first port with `role=fabric` → `data-0`, uses it as the `interface` field on the per-BMI `BareMetalNetworkAttachment`
4. BMaaS receives the `BareMetalNetworkAttachment` (subnet + interface + primary) on the BMI Create call and handles the fabric port move as part of provisioning (see [On-Demand BMI Provisioning Model](#on-demand-bmi-provisioning-model-osac-2135))

For v0.2: **CaaS supports BM node sets only.** VM-based cluster node sets are architecturally possible but are deferred — the HyperShift ↔ CUDN integration for VM worker nodes is not in scope.

For v0.2: **one attachment per cluster → one subnet; each node set resolves its own fabric interface from its BareMetalInstanceType.**

#### Interface Role Convention

| Role | Meaning |
|------|---------|
| `fabric` | Primary fabric traffic (east-west, tenant workloads) |
| `management` | In-band management/control plane traffic |
| `storage` | Storage fabric traffic |
| `lifecycle` | Out-of-band lifecycle management (PXE boot, Redfish/BMC) |

Roles are conventions, not enforced enums. The CaaS template defaults to role `fabric` for the tenant's subnet. The `lifecycle` interface is used by the provisioning system (Ironic, Metal3) for PXE boot and BMC operations — it is NOT tenant-attachable and the template skips it during interface resolution.

### What Changes vs. Today

#### Removed

- `osac.service.cluster_infra` dispatch to `{{ network_steps_collection }}.cluster_infra`
- `osac.service.external_access` dispatch to `{{ network_steps_collection }}.external_access`
- The entire concept of `NETWORK_STEPS_COLLECTION` for CaaS networking
- Step collections: `netris.steps`, `agentless_net.steps`, `osac.steps` etc. — their networking functionality is replaced by the OSAC Networking API + fabric manager roles

#### Added

- `ClusterNetworkAttachment` proto message on ClusterSpec
- `api_endpoint` / `ingress_endpoint` status fields on Cluster and ClusterOrder
- `BareMetalWorkerReconciler` creates on-demand BareMetalInstances via BMaaS private gRPC API; BMaaS owns the fabric port move and IP assignment as part of BMI provisioning (OSAC-2135)
- Template provisions MetalLB VIPs and writes them to ClusterOrder status
- VIP feedback loop: ClusterOrder → fulfillment-service → Cluster → ExternalIPAttachment controller
- ExternalIPAttachment Pending → Ready lifecycle for cluster targets

#### Kept

- HyperShift HostedCluster + NodePool creation (same)
- Agent correlation and labeling (BareMetalWorkerReconciler correlates Agents to BMIs via MAC address)
- DNS record creation (inline, until DNS API is implemented)
- Kubeconfig retrieval (same)
- Wait for nodes + cluster operators (same)
- AAP workflow structure (create → post-install → report-status)

### API Extensions

#### Proto (fulfillment-service)

```protobuf
message ClusterNetworkAttachment {
  optional string subnet = 1;           // omitted -> tenant default Subnet
  repeated string security_groups = 2;  // empty -> tenant default SecurityGroup
}
// Note: fabric_interface is system-populated ONCE on each node set definition
// by the fulfillment-service at cluster creation (resolved from the node set's
// BareMetalInstanceType, immutable after creation). The BareMetalWorkerReconciler
// reads this stored value — it does not re-resolve from BareMetalInstanceType.

message ClusterSpec {
  string template = 1;
  map<string, google.protobuf.Any> template_parameters = 2;
  map<string, ClusterNodeSet> node_sets = 3;
  // ... existing fields ...
  ClusterNetworkAttachment network_attachment = 9;   // NEW, optional, singular
  bool auto_external_ip_attachment = 10;              // NEW, create-time only; auto-provision ExternalIP + ExternalIPAttachment for API and ingress
}

message ClusterStatus {
  // ... existing fields ...
  string api_endpoint = X;      // NEW: set by template via feedback
  string ingress_endpoint = Y;  // NEW: set by template via feedback
}
```

#### Operator CRD (ClusterOrder)

```go
type ClusterOrderSpec struct {
    // ... existing fields ...
    NetworkAttachment *ClusterNetworkAttachment `json:"networkAttachment,omitempty"` // empty message -> both tenant defaults
}

type ClusterNetworkAttachment struct {
    SubnetRef         string   `json:"subnetRef,omitempty"` // resolved before provisioning
    SecurityGroupRefs []string `json:"securityGroupRefs,omitempty"`
}

type ClusterOrderStatus struct {
    // ... existing fields ...
    APIEndpoint     string          `json:"apiEndpoint,omitempty"`     // MetalLB-allocated API VIP, discovered by template
    IngressEndpoint string          `json:"ingressEndpoint,omitempty"` // MetalLB-allocated ingress VIP, discovered by template
    NodeSets        []NodeSetStatus `json:"nodeSets,omitempty"`        // Per-agent data
}

type NodeSetStatus struct {
    Name            string `json:"name"`
    FabricInterface string `json:"fabricInterface,omitempty"` // System-populated from BareMetalInstanceType
}

// Per-worker lifecycle state is tracked in ClusterOrder.status.workers[]
// (see OSAC-2135 WorkerStatus). The BareMetalWorkerReconciler manages
// worker phases (Provisioning → WaitingForAgent → Binding → Ready),
// BMI resource IDs, and failure/retry state. IP addresses are discovered
// by BMaaS as part of BMI provisioning (reconcileIPDiscovery) and do not
// require operator-side Agent CR IP watching.
```

#### Database

Migration adds to clusters table:
- `network_attachment JSONB` — stores the singular ClusterNetworkAttachment
- `api_endpoint TEXT` — discovered API server VIP
- `ingress_endpoint TEXT` — discovered ingress VIP

#### Server Validation

CaaS applies the shared [Unified Networking validation
pipeline](/enhancements/OSAC-1433-unified-networking/design.md#validation-and-enforcement-pipeline)
and adds cluster-wide and
node-set-specific checks. Validation runs before creating the Cluster and
again before creating any private BMaaS worker request.

**Cluster attachment shape and defaulting:**

- `network_attachment` is singular. The API accepts an omitted field or an
  empty message for default resolution, but it rejects any legacy/repeated
  representation that attempts to supply more than one tenant attachment.
- A supplied attachment may contain only the shared `subnet` and
  `security_groups` fields. `fabric_interface`, physical port names, and
  per-node-set attachment selectors are not tenant input and are rejected if
  they appear in the public Cluster request.
- Omitted/empty input resolves both tenant defaults. A partial message fills
  only the missing Subnet or missing/empty SecurityGroup list. Supplied
  fields are preserved exactly.
- After resolution, the Subnet and every SecurityGroup must exist, be Ready,
  be IPv4, be in the effective tenant/project, and belong to one
  VirtualNetwork. Duplicated SecurityGroup references and cross-VirtualNetwork
  combinations are rejected.
- The resolved attachment is stored once in `ClusterOrder.spec.networkAttachments[0]`.
  The worker controller must not append a second tenant attachment while
  enriching worker requests.

**Cluster and node-set validation:**

- The selected Cluster Template must be compatible with the supported CaaS
  node model. v0.2 accepts BM node sets only; VM-based node sets and a
  multi-NIC node request are rejected before networking resources are
  created.
- Every node set must identify a valid `baremetal_instance_type` in the
  permitted scope. The referenced BareMetalInstanceType must be Ready/usable,
  contain at least one ordered port with role `fabric`, and contain no
  malformed port definitions.
- For each node set, fulfillment-service selects the first ordered `fabric`
  port and persists it as the immutable `fabric_interface`. It must reject a
  missing fabric port, a lifecycle-only profile, or a node set whose
  interface cannot be represented in the BMaaS attachment contract.
- The tenant cannot select or override `fabric_interface`. Catalog policy,
  Template defaults, and tenant network input may govern only the tenant
  Subnet and SecurityGroup fields.
- The same resolved Subnet applies to every node set. Per-node-set Subnet,
  SecurityGroup, or tenant-interface overrides are rejected. The node set's
  stored `fabric_interface` may differ by BareMetalInstanceType, but it does
  not create another tenant network attachment.
- The resolved attachment and every network-owned nested field are immutable
  after Cluster creation. Changing them requires deleting and recreating the
  Cluster; changing a BareMetalInstanceType later does not re-resolve an
  existing Cluster's stored interface.

**Private BMaaS worker validation:**

- Every worker create request contains exactly one
  `BareMetalNetworkAttachment` with the Cluster Subnet, Cluster
  SecurityGroups, the immutable node-set `fabric_interface`, and implicit
  `primary: true`.
- BMaaS remains authoritative for the final physical-interface validation:
  the port must still exist in the referenced BareMetalInstanceType, be
  tenant-attachable, and not have role `lifecycle`. A private caller cannot
  bypass BMaaS validation by using the ClusterOrder CR directly.
- The worker controller does not re-resolve the interface after ClusterOrder
  creation. If the stored interface becomes unavailable, worker provisioning
  fails/retries with a clear condition; it does not silently choose another
  port.
- Worker deletion waits for BMaaS to remove the worker and return the selected
  port to the provisioning network. The ClusterOrder finalizer must not
  release the Subnet or related network resources while worker BMIs remain.

**External access and VIP validation:**

- `auto_external_ip_attachment` is create-time-only. When true, the request
  must reserve two IPv4 ExternalIPs atomically: one for `API` and one for
  `INGRESS`. Pool exhaustion or inability to reserve two addresses rejects
  the entire Cluster create and leaves no parent or child records.
- The two ExternalIPs must be distinct, and each ExternalIPAttachment must
  reference the same Cluster with the matching endpoint enum. A Cluster
  target with `UNSPECIFIED`, a Compute/BM target with `API`/`INGRESS`, or
  duplicate API/Ingress attachments is rejected.
- ExternalIPAttachment dispatch waits independently for the corresponding
  ExternalIP to be `Allocated` and the matching ClusterOrder endpoint to be
  populated. API DNAT uses only `status.apiEndpoint`; ingress DNAT uses only
  `status.ingressEndpoint`.
- Each discovered endpoint must be canonical IPv4, belong to the resolved
  Subnet/MetalLB address pool, be distinct from the other endpoint, and be
  stable for the lifetime of the Cluster. Empty, IPv6, duplicate, or
  out-of-subnet endpoint status is rejected and does not activate DNAT.
- The template must not report the Cluster Ready before the required VIP
  resources and endpoint statuses are available. The ExternalIPAttachment
  controller requeues rather than dispatching DNAT with an empty endpoint.

**Validation errors and tests:**

- Field paths identify the failure: `spec.network_attachment.subnet`,
  `spec.network_attachment.security_groups[0]`,
  `spec.node_sets[<name>].baremetal_instance_type`, or the corresponding
  `target_endpoint` field.
- Unit tests reject a repeated/multi-attachment request, unsupported VM node
  set, missing/default-not-Ready network resource, cross-VN reference,
  missing fabric port, lifecycle interface, tenant `fabric_interface`, and
  post-create network mutation.
- Integration tests verify one ClusterOrder attachment, different stored
  fabric interfaces for different node-set types, exactly one BM attachment
  per worker, and no second attachment after worker reconciliation.
- ExternalIP tests cover failure to reserve two addresses, duplicate API or
  ingress endpoint values, wrong endpoint enum, endpoint status arriving
  before ExternalIP allocation, and successful independent API/ingress
  requeue-to-Ready transitions.
- Delete tests prove the Cluster finalizer waits for worker BMI deletion and
  auto-created ExternalIPAttachment/ExternalIP cleanup before releasing
  dependent network resources.

#### Catalog Item interaction

Catalog Item v2 may govern the singular `network_attachment` field as a whole
structured value. It may lock the attachment or make it editable with an
optional default. Catalog resolution occurs before tenant default networking:
tenant input wins for an editable policy, then the Catalog default and Template
defaults are applied. Finally, only missing attachment fields receive the
tenant's default Subnet and SecurityGroup; supplied fields are preserved.

The Catalog Item governs only the tenant-facing Subnet and SecurityGroup
references. `fabric_interface` is derived separately for each node set from
BareMetalInstanceType and is never a Catalog field. A shared Catalog Item therefore cannot
lock or default tenant-local network references; it must leave the attachment
editable or ungoverned. The normal CaaS rules still apply: one attachment per
Cluster, all node sets share its Subnet, and all referenced objects belong to
the same VirtualNetwork.

The editable policy applies only during Cluster creation. After creation, the
resolved attachment and every network-owned field are read-only. Catalog Item
definitions and metadata remain governed by Catalog Items v2 and are not
changed here.

#### Template Changes

**osac.templates.ocp_4_17_small/install.yaml:**
- Remove: `osac.service.cluster_infra` call
- Remove: `osac.service.external_access` call
- Remove: agent selection logic (moved to operator)
- Add: create HostedCluster + NodePools referencing pre-selected agents from ClusterOrder status
- Add: MetalLB VIP provisioning (create LoadBalancer Services, discover VIPs, write to ClusterOrder status)

**osac.templates.ocp_4_17_small/delete.yaml:**
- Remove: step collection delete dispatch
- Remove: switch port cleanup (handled by BMaaS via BMI deletion)
- Keep: delete HostedCluster + NodePools, MetalLB Services, DNS cleanup

### Implementation Details/Notes/Constraints

#### Component Responsibility Summary

| Component | Responsibility |
|-----------|---------------|
| fulfillment-service | Validate `network_attachment` (singular), resolve fabric_interface per node set from BareMetalInstanceType, create ClusterOrder CR, sync VIPs from feedback, auto-provision ExternalIP |
| osac-operator BareMetalWorkerReconciler | Create on-demand BareMetalInstances via BMaaS private gRPC API with enriched `network_attachments` (subnet from ClusterOrder `networkAttachments[0]` + immutable `fabric_interface` from the node set, resolved once by fulfillment-service); correlate Agents to BMIs via MAC; delete BMIs on scale-down/cluster deletion. BMaaS owns the fabric port move and IP discovery as part of BMI provisioning (OSAC-2135) |
| osac-operator ClusterOrder controller | Create namespace/SA/RoleBindings, trigger AAP workflow, aggregate worker status |
| osac-operator ClusterOrder feedback controller | Watch ClusterOrder status, Signal fulfillment-service when VIPs appear |
| osac-operator ExternalIPAttachment controller | Read ClusterOrder `apiEndpoint`/`ingressEndpoint` (MetalLB-allocated, template-discovered) from status, create DNAT via fabric_manager |
| AAP template (ocp_4_17_small) | Create HostedCluster+NodePools (with pre-selected agents; no agent selection logic), provision MetalLB VIPs, write VIPs to ClusterOrder status, host-side networking handled by DHCP |
| BMaaS (bare-metal-fulfillment-operator) | Owns full BMI provisioning lifecycle including inventory → OS provisioning → fabric port move (provisioning network → tenant) → reboot → DHCP lease query IP discovery; returns fabric port to provisioning network on BMI deletion |
| configured network manager(s) | Move network attachments where supported, create/delete external-IP attachments (DNAT), and create/delete NATGateway only when the capability is advertised |
| k8s_manager (Ansible role) | create/delete_subnet (CUDN overlay) — called at subnet creation, NOT at cluster creation |

#### Auto-Provisioned Resource Lifecycle

- Labeled `osac.openshift.io/auto-created: "true"`
- Parent resource finalizer deletes in order: ExternalIPAttachment → ExternalIP
- On permanent cleanup failure: finalizer removed, parent deleted, orphaned resources left for manual cleanup

### Security Considerations

This feature inherits the existing security model:
- Tenant isolation via `osac.openshift.io/tenant` annotation enforced by OPA policies
- Auto-provisioned resources (ExternalIP, ExternalIPAttachment) inherit tenant annotation from parent Cluster
- No new authentication or authorization changes
- SecurityGroup enforcement follows the [Unified Networking SecurityGroup rule semantics](/enhancements/OSAC-1433-unified-networking/design.md#securitygroup-rule-semantics) for explicit and default SecurityGroups.

### Failure Handling and Recovery

#### ClusterOrder Controller Reconciliation Failures

- Subnet resolution failure (subnet not found, not Ready): ClusterOrder enters Failed state with condition, retries on Subnet status change
- BMI creation failure (BMaaS private API error or no available hosts): worker phase set to `Failed`, controller retries with escalating backoff (see OSAC-2135 retry logic)
- Agent registration timeout (host booted but Agent did not register within 30 min): worker phase set to `Failed` with reason `AgentRegistrationTimeout`, controller deletes the timed-out BMI and retries
- AAP job failure (template execution error): ClusterOrder enters Failed state with AAP job ID in status

#### Auto ExternalIP Allocation Failures

- Pool exhaustion: create API call returns error, resource not persisted
- ExternalIP provisioning failure: ExternalIP enters Failed state, Cluster remains in Pending (external access unavailable, cluster may still function without inbound connectivity)
- ExternalIPAttachment provisioning failure: DNAT rule not created, inbound traffic does not reach cluster (cluster functional, external access unavailable)

#### Cleanup Failures

- Auto-provisioned resource cleanup transient failure: finalizer retries
- Auto-provisioned resource cleanup permanent failure: after N retries, finalizer is removed, parent resource deleted, orphaned ExternalIP/ExternalIPAttachment left in cluster (manual cleanup required)

### RBAC / Tenancy

No RBAC or tenancy changes. All new resources (Cluster with new fields, auto-provisioned ExternalIP/ExternalIPAttachment) inherit tenant isolation from parent:
- `osac.openshift.io/tenant` annotation propagated from Cluster to auto-created resources
- OPA policies enforce tenant-scoped list/get/create/delete; update and patch of network-owned fields are rejected
- Tenant User can view auto-provisioned resources (labeled `osac.openshift.io/auto-created: "true"`) via the standard API; their network-owned fields are not editable

### Observability and Monitoring

New structured log events:
- ClusterOrder controller: `AgentSelectionCompleted` (info), `AgentSelectionFailed` (error), `NetworkAttachmentsConfigured` (info), `VIPsDiscovered` (info)
- fulfillment-service: `AutoProvisionedExternalIP` (info), `ExternalIPPoolExhausted` (error), `VIPFeedbackProcessed` (info)

New Kubernetes events on ClusterOrder:
- `AgentsSelected`: agent selection succeeded
- `AgentSelectionFailed`: agent selection failed (no suitable agents)
- `NetworkingConfigured`: network attachments (switch ports) configured
- `NetworkingFailed`: network attachment configuration failed
- `VIPsDiscovered`: API and ingress VIPs written to status
- `AutoExternalIPCreated`: ExternalIP and ExternalIPAttachment auto-provisioned

No new metrics or alerts (existing provisioning duration and failure rate metrics apply).

### Risks and Mitigations

#### Risk: BMaaS private API dependency for worker provisioning

**Impact:** The `BareMetalWorkerReconciler` depends on the BMaaS private gRPC API (`BareMetalInstances.Create`/`Delete`) for all worker lifecycle operations. If the fulfillment-service is unavailable, worker provisioning and deprovisioning stall.

**Mitigation:** Controller uses context deadlines (30s) and sets `FulfillmentServiceUnavailable` condition after 3 consecutive errors, backing off to 5-minute requeue intervals. Existing workers continue running independently of the controller (see OSAC-2135).

**Reviewed by:** osac-operator team

#### Risk: ExternalIPPool exhaustion

**Impact:** Auto ExternalIP allocation fails, create API call returns error, tenant cannot create cluster with `auto_external_ip_attachment=true`.

**Mitigation:** Pool capacity visible in status; clear error directs tenant to explicit allocation from another pool or contact admin.

**Reviewed by:** Cloud Provider Admin

#### Risk: MetalLB IPAddressPool missing on hosting cluster

**Impact:** MetalLB needs an IPAddressPool CR covering the subnet CIDR to allocate VIPs from. If the k8s_manager fails to create it at subnet creation, cluster API/ingress endpoints are unreachable.

**Mitigation:** k8s_manager creates IPAddressPool alongside the CUDN overlay at subnet creation (resolved in OQ#3). Subnet remains Pending until both CUDN overlay and IPAddressPool are confirmed on all hosting clusters.

**Reviewed by:** osac-operator team

### Drawbacks

#### VIP feedback loop adds complexity

VIP discovery flow (template → ClusterOrder status → Signal RPC → fulfillment-service → Cluster → ExternalIPAttachment controller) adds cross-component coordination complexity. Failure in any step breaks the flow.

**Trade-off:** Complexity vs. auto external access. Chosen approach: implement VIP feedback loop to enable auto ExternalIP for clusters. Alternative: manual external access only (simpler, less usable).

## Alternatives (Not Implemented)

### Alternative 1: Keep networking in step collections

Instead of moving networking to the OSAC Networking API, keep step collections and extend them with tenant-scoped VirtualNetwork/Subnet creation.

**Rejected because:** Step collections are deployment-wide (NETWORK_STEPS_COLLECTION env var), not tenant-scoped. Tenants cannot share VirtualNetworks across resources or isolate clusters in separate VNs. The unified networking API provides a cleaner multi-tenant model.

### Alternative 2: No VIP feedback loop, manual external access only

Instead of implementing VIP feedback loop, require tenants to manually create ExternalIP and ExternalIPAttachment after cluster is Ready.

**Rejected because:** Poor user experience. Tenants must poll cluster status, discover VIPs, then manually create external access. Auto external access (single-call API) is a key usability improvement.

## Open Questions

### ~~1. How does the operator select agents?~~ — Resolved

Resolved: Per OSAC-2135, the `BareMetalWorkerReconciler` creates on-demand `BareMetalInstance` objects via the BMaaS private gRPC API. Agents register automatically after BMI provisioning and are correlated to BMIs via MAC address. The static pre-boot agent pool is removed.

### ~~2. NMState NNCP configuration~~ — Resolved

Resolved: DHCP handles host-side networking for CaaS agents. NMState NNCP configuration is no longer needed — agents receive their IP, gateway, and DNS from the fabric's DHCP server when they boot on the network segment. The template does not configure static networking.

### ~~3. MetalLB IP pools~~ — Resolved

Resolved: the **k8s_manager creates the MetalLB IPAddressPool CR at subnet creation time**, alongside the CUDN overlay on each hosting cluster. The IPAddressPool covers the subnet CIDR and is a shared prerequisite for all hosted cluster control planes on that hosting cluster — not a per-cluster resource. The CaaS template creates LoadBalancer Services; MetalLB dynamically allocates VIPs from the pool and announces them. The template discovers the allocated VIPs and writes them to ClusterOrder status.

### ~~4. How does the operator know the fabric_manager name?~~ — Resolved

Resolved: The operator reads the fabric_manager name from the NetworkClass CR. One NetworkClass per deployment, read on first reconcile and cached. The NetworkClass is a K8s CR (not just a fulfillment-service DB object).

### ~~5. Should auto NATGateway treat a Deleting NATGateway as 'does not exist'?~~ — Resolved

Resolved: NATGateway reuse limited to Ready only. Failed/Deleting NATGateways cause the create request to fail with an error. NATGateway auto-provisioning per resource was removed — NATGateway is now a VN default created at tenant onboarding.

### ~~6. Should capacity exhaustion return an API error or create a Failed resource?~~ — Resolved

Resolved: Return error, no resource persisted. Pool capacity is checked synchronously during the API call. If exhausted, the call fails atomically. No Failed resource created.

### ~~7. How is the subnet CIDR partitioned between MetalLB VIP allocation and fabric DHCP assignment?~~ — Resolved

Resolved: The k8s_manager creates the MetalLB IPAddressPool with a reserved sub-range of the subnet CIDR (e.g., last /28). The fabric manager's DHCP server is configured to exclude this range. The sub-range size is configurable on the NetworkClass. This ensures MetalLB VIPs and DHCP-assigned agent IPs never overlap.

### ~~8. What IP addresses do DNS records point to — MetalLB VIPs or ExternalIPs?~~ — Resolved

Resolved: Kubeconfig API address uses the MetalLB VIP directly — workers are on the same subnet and reach it without DNS. External DNS records (api.<cluster>.<domain>, *.apps.<cluster>.<domain>) point to the ExternalIP and are only created when the tenant uses --external-ip-attachment. No bootstrap sequencing issue — workers use VIPs from kubeconfig, not DNS.

## Test Plan

CaaS tests must cover the singular Cluster attachment and the fact that one
tenant network is shared by every node set while each node set may resolve a
different physical fabric interface. The worker path is an integration with
BMaaS, not a second CaaS networking implementation: every private worker
request must be validated again by BMaaS.

### Unit tests

#### Cluster attachment and defaulting

- Accept an omitted `network_attachment` and an empty message for default
  resolution.
- Accept a partial attachment and fill only its missing Subnet or empty
  SecurityGroup list.
- Accept a complete attachment and preserve both fields exactly.
- Accept only the shared tenant-facing fields `subnet` and
  `security_groups`.
- Reject repeated/multi-attachment representations, unknown attachment
  fields, `fabric_interface`, physical-port selectors, and per-node-set
  tenant attachment selectors in the public Cluster request.
- Reject missing, Pending, Failed, wrong-scope, wrong-VirtualNetwork, IPv6,
  or duplicate SecurityGroup references.
- Reject an invalid explicit value instead of replacing it with a default.
- Verify exactly one resolved attachment is stored on ClusterOrder and worker
  reconciliation cannot append a second tenant attachment.

#### Cluster and node-set support

- Accept BM node sets with a Ready/usable BareMetalInstanceType.
- Accept a fabric-only/BM-only CaaS deployment without a K8s manager when
  MetalLB VIP capability and the required `metallb_vip_prefix_length` are
  configured.
- Select the first ordered port with role `fabric` for each node-set type.
- Preserve different resolved `fabric_interface` values for different node-set
  types while keeping the tenant Subnet and SecurityGroups shared.
- Reject a missing or malformed BareMetalInstanceType, a Pending/Failed type,
  a type without a fabric port, a lifecycle-only type, or an invalid port
  definition.
- Reject VM-based node sets and multi-NIC node requests in the current CaaS
  contract.
- Reject tenant attempts to select or override `fabric_interface`.
- Reject per-node-set Subnet, SecurityGroup, or tenant-interface overrides.
- Verify an edit to BareMetalInstanceType or port ordering does not silently
  change an existing Cluster's stored interface.

#### Private BMaaS worker handoff

- Build exactly one `BareMetalNetworkAttachment` for every worker.
- Copy the Cluster Subnet and SecurityGroups and the immutable node-set
  `fabric_interface` into that request.
- Set the worker attachment's implicit primary value correctly.
- Revalidate the worker through BMaaS, including type, scope, same-VN,
  attachable-port, and lifecycle-port checks.
- Reject a worker request with a second attachment, unknown/lifecycle port,
  missing type, or changed stored interface.
- Verify the worker controller does not re-resolve the interface after the
  ClusterOrder has stored it.
- Verify worker deletion waits for BMaaS deletion and port return before the
  ClusterOrder releases network dependencies.

#### VIPs and ExternalIP behavior

- Validate endpoint enum combinations: Cluster requires `API` or `INGRESS`,
  while Compute/BM endpoint rules remain shared and are not accepted here.
- Reserve two distinct IPv4 ExternalIPs atomically for API and ingress when
  auto external access is requested.
- Reject inability to reserve two addresses and roll back Cluster and all
  child records.
- Verify duplicate API/Ingress bindings and duplicate endpoint values are
  rejected.
- Verify each attachment waits independently for its ExternalIP to be
  Allocated and its matching Cluster endpoint to be populated.
- Accept canonical IPv4 endpoints in the resolved Subnet/MetalLB pool and
  reject empty, IPv6, duplicate, or out-of-subnet endpoints.
- Verify API DNAT uses only `status.apiEndpoint` and ingress DNAT uses only
  `status.ingressEndpoint`.
- Reject premature Ready status or DNAT dispatch.

#### Operations and Catalog

- Reject updates, patches, replaces, and field-mask changes to the attachment,
  Subnet, SecurityGroups, stored interfaces, endpoint fields, and
  `auto_external_ip_attachment`.
- Accept controller updates only to status, conditions, and finalizers.
- Verify Catalog policy governs only tenant-facing Subnet and SecurityGroups.
- Verify shared Catalog Items cannot lock/default tenant-local references.
- Verify locked and editable policy precedence and direct/Catalog parity.

### Integration tests

Use fulfillment-service with real PostgreSQL and validation policy, an
envtest/Kind cluster with Cluster/ClusterOrder and BM CRDs, the osac-operator,
the CaaS worker reconciler, and a fake BMaaS private API with controllable
worker lifecycle. Use fake MetalLB and manager responses for asynchronous
VIP and network state.

- Exercise direct, private, REST, and Catalog-based Cluster creation with
  equivalent valid and invalid attachment inputs.
- Verify default resolution happens before Cluster persistence and that only
  missing fields are filled.
- Verify one ClusterOrder attachment is written and remains one after worker
  reconciliation for multiple node sets.
- Verify two node-set types can resolve different fabric interfaces while
  sharing the same tenant attachment.
- Verify the agent-selection and agent-to-BMI MAC-correlation path selects
  the intended worker and does not associate a worker with another host's
  fabric interface.
- Verify missing/NotReady instance types and invalid port roles fail before
  cluster or worker creation.
- Verify private worker requests are revalidated by BMaaS and a direct
  ClusterOrder write cannot bypass BMaaS validation.
- Verify worker deletion and Cluster finalizer ordering protect the Subnet,
  SecurityGroups, and ExternalIP resources.
- Verify VIP feedback flows from the template/ClusterOrder to Cluster status
  and then to ExternalIPAttachment reconciliation.
- Inject endpoint-before-IP, IP-before-endpoint, duplicate endpoint,
  out-of-subnet endpoint, missing/overlapping MetalLB pool range, Signal RPC
  failure, manager failure, and controller restart; verify independent
  requeue and no premature DNAT.
- Verify reserving one of two ExternalIPs and then failing the second rolls
  back both reservations and the Cluster.
- Verify API and ingress auto attachments are deleted before their ExternalIPs
  and no resources leak after Cluster deletion.
- Verify the MetalLB reserved VIP range does not overlap the fabric DHCP
  allocation range and that both API and ingress VIPs remain in the permitted
  Subnet/pool range.
- When the deployment enables inline DNS integration, verify API and wildcard
  application records point to the ExternalIPs as documented; do not treat a
  DNS API as part of this feature.
- Verify API, private, direct-CR, and Catalog paths reject immutable network
  mutations consistently.

### End-to-end tests — supported behavior

In the supported connected single-hub CaaS environment:

- Create a BM-backed Cluster with one explicit attachment and verify every
  node set uses the selected Subnet.
- Repeat the supported BM-backed workflow in a fabric-only/BM-only
  deployment with MetalLB capability and verify that CaaS does not require a
  K8s manager.
- Create a Cluster with omitted and empty attachment input and verify tenant
  defaults.
- Create a Cluster with partial attachment input and verify only missing
  fields are defaulted.
- Create multiple node sets using different BareMetalInstanceTypes and verify
  each stores the correct first fabric-role interface while all share one
  tenant attachment.
- Verify private workers are created with exactly one enriched BMaaS
  attachment, receive an IP, and become usable only after BMaaS validation
  and handoff complete.
- Verify MetalLB allocates API and ingress VIPs and the Cluster does not
  become usable before the required endpoint statuses are present.
- Request auto external access and verify two distinct ExternalIPs,
  endpoint-specific DNAT, API connectivity, and ingress connectivity.
- Create through a Catalog Item with locked and editable policies and verify
  tenant/default precedence.
- Delete the Cluster and verify worker port return, ExternalIPAttachment
  cleanup, ExternalIP cleanup, and release of dependent network resources.

### End-to-end tests — unsupported behavior

- A repeated or multi-entry Cluster attachment is rejected.
- A tenant-supplied `fabric_interface`, physical port, per-node Subnet, or
  per-node SecurityGroup override is rejected.
- VM node sets and multi-NIC node requests are rejected.
- Missing, Pending, Failed, wrong-scope, wrong-VirtualNetwork, or non-Ready
  network references are rejected.
- A BareMetalInstanceType without an ordered fabric-role port, or with only
  lifecycle ports, is rejected.
- A Cluster target with `UNSPECIFIED`, or a non-Cluster target with `API` or
  `INGRESS`, is rejected.
- Duplicate API/ingress endpoints, empty/IPv6/out-of-subnet endpoint status,
  or a second ExternalIP reservation are rejected and leave no partial
  resources.
- Update, patch, replace, and field-mask changes to every network-owned field
  are rejected; delete/recreate is required.
- Worker reconciliation cannot append a second attachment or silently choose
  another interface when the stored one is unavailable.
- A tenant cannot make the Cluster Ready by writing status or bypass the
  fulfillment/BMaaS APIs through ClusterOrder.
- Legacy deployment-wide step collections such as `netris.steps` and
  `agentless_net.steps` are not a supported tenant networking input and must
  not be used as an alternate path for Cluster network configuration.
- NATGateway, DNS API behavior, and other features not defined as part of
  this CaaS networking contract are not accepted through CaaS network fields.

### Coverage gate

Every rule in CaaS Server Validation, the private-worker handoff, the VIP
feedback flow, and the Catalog interaction must map to a unit or integration
test. Every supported Cluster workflow and every user-visible unsupported
workflow must have an E2E case. Failure tests must verify no Cluster, worker,
VIP, ExternalIP, or attachment is left partially created.

## Graduation Criteria

**Note:** This section will be updated when the enhancement is targeted at a release.

Proposed maturity level: **Tech Preview** → **GA**

Tech Preview criteria:
- [ ] API fields (`network_attachment`, `auto_external_ip_attachment`, `api_endpoint`, `ingress_endpoint`) implemented in fulfillment-service
- [ ] Operator CRD updated with `NetworkAttachment`, `APIEndpoint`, `IngressEndpoint` fields
- [ ] BareMetalWorkerReconciler (OSAC-2135) implemented — on-demand BMI creation with enriched network_attachment
- [ ] Agent-to-BMI MAC correlation and NodePool labeling implemented
- [ ] VIP feedback loop (template → ClusterOrder → fulfillment-service → Cluster) implemented
- [ ] Auto ExternalIP attachment provisioning functional
- [ ] Template changes (remove cluster_infra/external_access, add MetalLB VIP provisioning) completed
- [ ] Integration tests pass (E2E coverage for network_attachment, auto ExternalIP attachment, VIP feedback)
- [ ] Documentation: API reference, user guide for simplified cluster creation

GA criteria:
- [ ] k8s_manager implementation (OSAC-1511 or OSAC-1717) delivered and production-tested
- [ ] Multi-job tracking (OSAC-1459) implemented and stable
- [ ] Dispatcher infrastructure (OSAC-1457, OSAC-1458, OSAC-1460) delivered
- [ ] BareMetalInstanceType with `network_ports` (BareMetalNetworkPortSpec) implemented and tested
- [ ] Production deployment verified (MOC or other OSAC deployment)
- [ ] User feedback incorporated (usability, error messages, edge cases)

## Upgrade / Downgrade Strategy

### Upgrade

Micro version upgrades (`x.y.N → x.y.N+2`):
- New fields (`network_attachment`, `auto_external_ip_attachment`, `api_endpoint`, `ingress_endpoint`) are additive
- Existing Cluster resources continue to work (networking managed by step collections)
- No user action required

Minor version upgrades (`x.N → x.N+1`):
- Template changes deployed (cluster_infra/external_access removed, MetalLB VIP provisioning added)
- Existing clusters (created before upgrade) continue to work with old flow
- New clusters (created after upgrade) use new flow (OSAC Networking API)
- No breaking changes

### Downgrade

If `N+1` upgrade fails or cluster is misbehaving:
- Manual rollback: update fulfillment-service, osac-operator, and osac-aap images to `N`
- Existing Cluster resources with new `network_attachment` field will be unrecognized by `N` server
- Manual cleanup required: delete Cluster resources created with new field, re-create with old flow
- Auto-provisioned ExternalIP resources remain (manual cleanup required if not needed)

Acceptable downgrade steps:
- Delete Clusters using new field
- Re-create using old flow (no network_attachment field)
- Manually delete orphaned auto-provisioned resources (ExternalIP, ExternalIPAttachment labeled `osac.openshift.io/auto-created: "true"`)

## Version Skew Strategy

### Control Plane Skew

fulfillment-service, osac-operator, and osac-aap are deployed together in the same namespace and upgraded atomically (all controlled by osac-installer). No skew expected.

### Client Skew

osac-cli (n-1) with fulfillment-service (n):
- Old CLI does not send `--network-attachment` flag → server populates default Subnet + SecurityGroup
- New CLI uses new `--network-attachment` flag → server accepts

osac-cli (n) with fulfillment-service (n-1):
- New CLI uses new `--network-attachment` flag → old server rejects unknown field
- Workaround: omit `--network-attachment` until server is upgraded

Recommendation: keep osac-cli and fulfillment-service within one minor version.

## Support Procedures

### Symptom: Cluster stuck in Pending, condition "NetworkingResolutionFailed"

**Detection:**
```bash
kubectl describe cluster <name> -n <namespace>
# Check status.conditions for NetworkingResolutionFailed
```

**Cause:** Subnet not found, not Ready, or BM-only deployment (no k8s_manager)

**Resolution:**
1. Check Subnet status: `kubectl get subnet <subnet-name> -n <namespace>`
2. If Subnet is not Ready, investigate Subnet provisioning failure (check AAP job logs)
3. If BM-only deployment, tenant must create Cluster in a deployment with k8s_manager configured

### Symptom: Auto-provisioned ExternalIP not cleaned up after Cluster deletion

**Detection:** `kubectl get externalip` shows orphaned ExternalIP labeled `osac.openshift.io/auto-created: "true"` with no parent

**Cause:** Finalizer cleanup failed permanently

**Resolution:**
1. Check Cluster deletion logs (controller logs) for cleanup errors
2. Manually delete orphaned ExternalIPAttachment: `kubectl delete externalipattachment <name> -n <namespace>`
3. Manually delete orphaned ExternalIP: `kubectl delete externalip <name> -n <namespace>`

### Symptom: ClusterOrder VIPs not synced to Cluster

**Detection:** `kubectl get clusterorder <name> -o yaml` shows `apiEndpoint` and `ingressEndpoint` populated, but `kubectl get cluster <name> -o yaml` shows empty fields

**Cause:** VIP feedback loop failure (Signal RPC failed, or fulfillment-service did not process)

**Resolution:**
1. Check osac-operator feedback controller logs for Signal RPC errors
2. Check fulfillment-service logs for VIP sync errors
3. Manually trigger reconciliation: `kubectl annotate clusterorder <name> osac.openshift.io/reconcile=true`

### Disabling the feature

To disable auto ExternalIP attachment:
- Remove or redact ExternalIPPool CRs (capacity exhaustion prevents auto allocation)
- No API extension to disable (fields are part of CRD, cannot be removed at runtime)

Consequences:
- Auto ExternalIP allocation fails with error (resource not created)
- Manual ExternalIP workflows remain functional
- No impact on existing running clusters

## Infrastructure Needed

- AAP execution environment with `osac.templates.ocp_4_17_small` role updated (remove cluster_infra/external_access, add MetalLB VIP provisioning)
- k8s_manager Ansible role (OSAC-1511 or OSAC-1717) for CUDN overlay provisioning
- fabric_manager Ansible role with the generic `move_network_attachment` primitive (OSAC-2081); a provisioned provisioning network segment for BMaaS BMI provisioning
- Integration test environment with CUDN or EVPN fabric
- BareMetalInstanceType test data with `network_ports` (BareMetalNetworkPortSpec)

## Dependencies

| Dependency | Jira | Status |
|-----------|------|--------|
| Dispatcher core | OSAC-1457, OSAC-1458, OSAC-1460 | Closed |
| Multi-job tracking (subnet) | OSAC-1459 | New |
| NATGateway full stack | OSAC-1443 (10 tasks) | 1/10 In Progress |
| ExternalIPAttachment cluster target in CRD | OSAC-2041 | New |
| Cluster DNAT flow in controller | OSAC-1495 | New |
| ClusterNetworkAttachment proto | OSAC-1501 | New |
| api_endpoint/ingress_endpoint on Cluster status | OSAC-2040 | New |
| Immutability validation | OSAC-1503 | New |
| DB migration for Cluster networking fields | OSAC-2079 | New |
| Server validation | OSAC-1504 | New |
| ClusterOrder CRD: networkAttachments | OSAC-1505 | New |
| ClusterOrder CRD: api/ingress endpoint status | OSAC-2080 | New |
| VIP discovery flow (feedback) | OSAC-1506 | New |
| CaaS template: accept network_attachment + per-node config | OSAC-1507 | New |
| CaaS template: MetalLB VIP provisioning + write to status | OSAC-2077 | New |
| BareMetalWorkerReconciler (on-demand BMI provisioning + networking) | OSAC-2135 | New |
| BM provisioning flow — reconcileNetworking dispatcher logic | OSAC-2047 | Closed |
| CLI --network-attachment for Cluster | OSAC-2076 | New |
| Integration test | OSAC-2078 | New |
| Fabric manager `move_network_attachment` role (generic port move) | OSAC-2081 (Netris BM) | Closed |
| BareMetalInstanceType: network ports (BareMetalNetworkPortSpec) with name, role, type, speed | OSAC-1201 | New |
| Remove cluster_infra / external_access step collection dispatch | Not tracked | **GAP** |
| Remove NETWORK_STEPS_COLLECTION dependency | Not tracked | **GAP** |
| fulfillment-service: resolve interface from BareMetalInstanceType (fabric_interface) | Not tracked | **GAP** |
