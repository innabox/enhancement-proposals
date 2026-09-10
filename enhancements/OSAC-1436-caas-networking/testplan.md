# Testplan — OSAC-1436 CaaS Networking

## Overview

- **Feature:** OSAC-1436 — CaaS Networking via the OSAC Networking API
- **Source design:** [design.md](design.md)
- **Shared contract:** [Unified Networking test plan](../OSAC-1433-unified-networking/testplan.md)
- **Scope:** Singular Cluster attachment, BM node-set interface resolution,
  private BMaaS worker handoff, MetalLB/API/Ingress VIP feedback, auto
  ExternalIP, and cleanup.
- **Current support boundary:** BM node sets only, one tenant attachment per
  Cluster, one Subnet shared by all node sets, and one resolved fabric
  interface per node-set type. VM node sets, multi-NIC, tenant-selected
  physical interfaces, and DNS API are unsupported.

## Execution strategy

- **Unit:** Cluster server validation, node-set/port resolution, worker request
  construction, endpoint/VIP validation, Catalog resolution, and finalizer
  decisions.
- **Integration:** real PostgreSQL and CaaS handlers, Cluster/ClusterOrder
  CRDs/controllers in envtest/Kind, fake BMaaS private API, fake MetalLB and
  manager jobs, and asynchronous feedback.
- **E2E:** real connected CaaS with BM workers, MetalLB, API/Ingress
  connectivity, ExternalIP/DNAT, and deletion.

## Test cases

### R1: Singular Cluster attachment

#### TC-R1-01: Omitted, empty, partial, and complete attachment input

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Matrix

| Input | Expected result |
|---|---|
| Field omitted | Tenant default Subnet and SecurityGroup |
| Empty message | Tenant default Subnet and SecurityGroup |
| Only Subnet | Preserve Subnet; fill only SecurityGroups |
| Only SecurityGroups | Preserve SecurityGroups; fill only Subnet |
| Complete message | Preserve all supplied fields |
| Invalid explicit value | Reject; never repair with default |

##### Expected results

- Catalog/Template resolution precedes tenant defaults.
- Exactly one resolved Cluster attachment is stored.
- Subnet and SecurityGroups are Ready, same-scope, same-VN, IPv4, and unique.

#### TC-R1-02: Unsupported Cluster attachment shapes are rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- repeated/multi-attachment representation;
- `fabric_interface` or physical-port field in public Cluster input;
- per-node Subnet/SecurityGroup/tenant-interface override;
- wrong-scope, cross-VN, Pending, Failed, IPv6, or duplicate reference.

##### Expected results

- Request is rejected before Cluster, ClusterOrder, or worker persistence.
- No worker or port-move operation is dispatched.

### R2: BM node-set and interface resolution

#### TC-R2-01: Node-set types resolve ordered fabric interfaces

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Preconditions

- Two Ready BareMetalInstanceTypes with different ordered fabric ports.

##### Expected results

- Each node set stores the first ordered `fabric` port for its type.
- Node sets may have different physical interfaces while sharing one tenant
  Subnet and SecurityGroups.
- The stored interface is immutable after Cluster creation.

#### TC-R2-02: Invalid node-set types and ports fail closed

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- missing/Pending/Failed BareMetalInstanceType;
- no fabric-role port;
- lifecycle-only, malformed, or unknown-role ports;
- inventory host cannot provide stored interface;
- VM node set or multi-NIC node request.

##### Expected results

- Cluster create or worker provisioning fails with the specific field/condition.
- No fallback to arbitrary or first non-fabric port occurs.
- Existing Cluster never silently re-resolves to a different port.

### R3: Private BMaaS worker handoff

#### TC-R3-01: Worker request is enriched with exactly one attachment

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Expected results

- Each worker request contains one BM attachment.
- Subnet and SecurityGroups come from the Cluster attachment.
- Physical interface comes from immutable node-set resolution.
- Primary is implicit/true.
- BMaaS revalidates scope, same-VN, readiness, instance type, and lifecycle
  role.
- Worker reconciliation never appends a second attachment or silently chooses
  another interface.

#### TC-R3-02: Worker deletion protects network dependencies

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | high | automated |

##### Expected results

- Cluster deletion calls BMaaS deletion for every worker.
- Worker port returns to provisioning network before dependent network
  resources are released.
- ClusterOrder finalizer waits while workers remain.
- A worker failure/retry does not release the Subnet or ExternalIP early.

### R4: MetalLB and VIP feedback

#### TC-R4-01: VIPs are allocated and synchronized before readiness

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Steps

1. Create a Cluster with a valid attachment.
2. Provision MetalLB API and Ingress VIPs.
3. Propagate endpoint status through ClusterOrder to Cluster.
4. Verify readiness and connectivity.

##### Expected results

- API and ingress endpoints are canonical IPv4 values in the permitted Subnet
  and VIP pool.
- Cluster is not Ready before required endpoint status is present.
- Reserved MetalLB range does not overlap fabric DHCP allocation.
- API and wildcard ingress DNS records, when inline DNS is enabled, point to
  the documented ExternalIPs; DNS API is not part of this feature.

#### TC-R4-02: Endpoint and ExternalIP ordering failures requeue

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Cases

- endpoint status before ExternalIP allocation;
- ExternalIP allocation before endpoint status;
- empty, IPv6, duplicate, or out-of-subnet endpoint;
- missing/overlapping MetalLB pool;
- Signal RPC failure;
- manager/controller restart.

##### Expected results

- API and ingress attachments wait independently for their matching endpoint
  and Allocated ExternalIP.
- DNAT never dispatches with an empty, wrong, or duplicate endpoint.
- Retry is idempotent and does not allocate duplicate VIPs or IPs.

### R5: Automatic ExternalIP access

#### TC-R5-01: Cluster auto external access reserves two distinct addresses

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Expected results

- Two distinct IPv4 ExternalIPs are reserved atomically.
- One attachment uses `API`, the other `INGRESS`.
- Pool exhaustion or inability to reserve two addresses leaves no Cluster,
  child, or capacity reservation.
- API DNAT uses only `status.apiEndpoint`; ingress DNAT uses only
  `status.ingressEndpoint`.

### R6: Operations, Catalog, and unsupported behavior

#### TC-R6-01: CaaS network-owned fields are immutable

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Expected results

- Update, patch, replace, and field-mask changes to attachment, Subnet,
  SecurityGroups, stored interfaces, endpoint fields, and auto-external switch
  are rejected.
- Status/conditions/finalizers remain controller-owned mutable fields.

#### TC-R6-02: Catalog and direct Cluster creates are equivalent

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | high | automated |

##### Expected results

- Locked/editable policies and tenant/default precedence are identical.
- `fabric_interface` is never Catalog-governed.
- Shared Catalog Items cannot lock/default tenant-local references.
- Catalog edits do not mutate existing Cluster networking or metadata.

#### TC-R6-03: Unsupported CaaS surface is rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated where user-visible |

##### Cases

- VM-based node set;
- multi-NIC or repeated Cluster attachment;
- tenant-selected physical interface/per-node network;
- lifecycle/no-fabric port;
- wrong endpoint enum or duplicate API/Ingress binding;
- direct ClusterOrder bypass;
- legacy deployment-wide step collections as a tenant input;
- DNS API, NATGateway, and other non-CaaS network fields.

##### Expected results

- Unsupported behavior is rejected or excluded from the CaaS API.
- No Cluster, worker, VIP, IP, or port move is partially created.

## Graduation gate

- Every CaaS server-validation and worker-handoff rule has unit/integration
  coverage.
- BM-only and combined-manager supported workflows have E2E coverage.
- API/Ingress VIP feedback, ExternalIP ordering, cleanup, and retry pass.
- Every user-visible unsupported CaaS path has a negative E2E test.
