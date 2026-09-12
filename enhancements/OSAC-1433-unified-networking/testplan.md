# Testplan — OSAC-1433 Unified Networking

## Overview

- **Feature:** OSAC-1433 — Unified Networking API for VMaaS, CaaS, and BMaaS
- **Source design:** [design.md](design.md)
- **Scope:** Shared networking resources, IPv4 field contracts, manager
  capabilities, lifecycle operations, defaulting semantics, dependency
  readiness, allocation transactionality, and cross-service interoperability.
- **Operation contract:** create, read/list, and delete only for network-owned
  fields. Network-owned update, patch, and replace operations are unsupported.
- **Excluded:** East-west networking is not implemented and is governed by its
  own design. Unsupported in the current boundary: multi-interface, IPv6,
  dual-stack, multi-hub, air-gapped, and VN-peering behavior. These are
  negative-test cases, not supported scenarios.

## Execution strategy

The test plan uses three layers:

- **Unit:** fast deterministic validator, resolver, transaction-decision,
  controller-state, dispatcher-plan, and status-parser tests using fake
  repositories, Kubernetes clients, managers, and job responses.
- **Integration:** fulfillment-service with real ephemeral PostgreSQL,
  protovalidate, OPA/RBAC, public/private handlers, and an envtest or Kind
  cluster running real CRDs/admission/controllers. Manager and AAP/fabric
  behavior is simulated with contract-compatible fakes.
- **E2E:** the supported connected single-hub deployment with real
  authentication, OSAC components, the applicable manager, and dataplane
  connectivity checks. Both combined-manager and K8s-only/BM-only topologies
  are tested where their capability matrix declares them supported.

Every negative test verifies both the expected error/condition and the absence
of an invalid parent, child, allocation, backend operation, or orphan.

## Test cases

### R1: NetworkClass manager and capability resolution

#### TC-R1-01: Combined manager configuration is accepted

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration | critical | automated |

##### Preconditions

- Provider registers one fabric manager and one K8s manager.
- Both advertise the required IPv4 create/read/delete capabilities.

##### Steps

1. Create the deployment NetworkClass with both manager references.
2. Resolve a VirtualNetwork and Subnet provisioning plan.
3. Resolve the implementation strategy.

##### Expected results

- NetworkClass is accepted.
- The manager combination covers the requested resource operations.
- The implementation strategy is derived from manager capabilities.
- The tenant cannot replace the derived strategy with an arbitrary value.

#### TC-R1-02: K8s-only and fabric-only supported topologies are evaluated

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Steps

1. Configure a K8s-only manager that advertises the complete supported
   networking surface except NATGateway.
2. Verify VM, CaaS, and shared resource capability resolution.
3. Configure a fabric-only manager and verify BMaaS/fabric resource
   capability resolution.
4. Attempt VM placement without a K8s manager.
5. Attempt a resource operation not advertised by the selected manager.

##### Expected results

- K8s-only VM/CaaS/shared-resource behavior is accepted when advertised.
- Fabric-only BMaaS behavior is accepted when advertised.
- VM creation without a K8s manager is rejected before persistence.
- An unadvertised resource or operation is rejected before backend dispatch.

#### TC-R1-03: Invalid or tenant-controlled manager configuration is rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration | critical | automated |

##### Cases

- neither manager is configured;
- manager is not provider-registered;
- required capability is missing;
- conditional CaaS capability lacks the required MetalLB prefix length;
- tenant supplies a NetworkClass, manager, implementation strategy, or
  provider-only capability override;
- tenant attempts to create NATGateway in a topology without NAT support.

##### Expected results

- The request is rejected with the documented authorization, validation, or
  failed-precondition status.
- No networking resource or backend operation is created.

### R2: Shared resource fields and formats

#### TC-R2-01: Valid IPv4 resources and references are accepted

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration | critical | automated |

##### Steps

1. Create a Ready VirtualNetwork with canonical IPv4 CIDR.
2. Create a contained non-overlapping Subnet.
3. Create a SecurityGroup with a valid rule.
4. Create a Ready IPv4 ExternalIPPool with one CIDR.
5. Allocate an ExternalIP and create valid ExternalIPAttachment and
   NATGateway references where supported.

##### Expected results

- Every create accepts the documented field types and values.
- References are typed, same-scope, and Ready/Allocated before use.
- Provider status is Pending until backend prerequisites complete, then Ready.

#### TC-R2-02: Invalid formats and relationships are rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- malformed IPv4 address or CIDR;
- IPv6 or dual-stack value;
- host bits set in a network CIDR;
- Subnet outside, equal to, or overlapping a sibling Subnet;
- wrong reference type, missing reference, cross-tenant/project reference;
- Pending, Failed, or non-Ready dependency;
- ExternalIPPool with zero or multiple CIDRs;
- duplicate ExternalIP consumer or second NATGateway for one VN;
- arbitrary tenant-selected ExternalIP address.

##### Expected results

- Invalid format/relationship returns `InvalidArgument`.
- Existing but unusable dependency returns `FailedPrecondition`.
- No invalid object or backend operation is left behind.

#### TC-R2-03: Cross-tenant VN CIDR overlap follows the documented isolation rule

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration | high | automated |

##### Expected results

- Overlapping VirtualNetwork CIDRs for different tenants are accepted where
  fabric isolation is the declared boundary.
- Subnet overlap within one VirtualNetwork remains rejected.
- Different VirtualNetworks remain isolated; the API does not implement VN
  peering or cross-VN routing.

### R3: SecurityGroup rules and deployment baseline

#### TC-R3-01: Rule fields and rule-set semantics are enforced

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Cases

- valid allow/deny, ingress/egress, tcp/udp/icmp/any rule;
- required ports for TCP/UDP and omitted ports for ICMP/any;
- valid direction-specific canonical IPv4 CIDR;
- invalid action, direction, protocol, port range, or source/destination;
- duplicate normalized rule;
- conflicting equal-specificity rule;
- tenant-created empty rule list;
- system-created fallback SecurityGroup with an empty list and the provider
  baseline policy configured with either `permit` or `deny`.

##### Expected results

- Tenant-created groups require at least one valid rule.
- The fallback group is accepted empty only with the deployment baseline.
- Invalid, duplicate, and conflicting rules are rejected before persistence.

#### TC-R3-02: Most-specific rule behavior is verified

| Test type | Priority | Automation |
|---|---|---|
| Unit, E2E | critical | automated |

##### Expected results

- Deployment-wide least-specific permit remains active.
- The most-specific matching tenant rule wins.
- Exact protocol outranks `any`; exact port outranks omitted port.
- The tenant fallback SecurityGroup is not confused with the deployment
  baseline rule.

### R4: Attachment defaulting and cardinality

#### TC-R4-01: Omitted, empty, partial, and complete attachments resolve correctly

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Matrix

| Input | Expected result |
|---|---|
| Missing attachment field | All applicable defaults are resolved |
| Explicit empty list/message | Same default behavior as documented for the resource |
| Only Subnet supplied | Preserve Subnet; fill only SecurityGroups |
| Only SecurityGroups supplied | Preserve SecurityGroups; fill only Subnet |
| Complete attachment supplied | Preserve every supplied value |
| Explicit invalid supplied value | Reject; never repair with a default |

##### Expected results

- Catalog and Template precedence is resolved before tenant defaults.
- Direct tenant creates cannot persist a Pending dependency graph.
- All resolved references are Ready, same-scope, same-VirtualNetwork, and
  unique before persistence.

#### TC-R4-02: Service cardinality restrictions are enforced centrally

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- Compute list with more than one entry;
- BM list with more than one entry;
- Compute or BM sole entry with explicit `primary: false`;
- Cluster repeated/multi-attachment representation;
- duplicate SecurityGroup references;
- direct CR containing values rejected by the public API.

##### Expected results

- Rejection identifies the most specific field path.
- No template, worker, port-move, or backend operation is dispatched.

### R5: ExternalIP and NATGateway lifecycle

#### TC-R5-01: Allocation, readiness, and capacity are atomic

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Steps

1. Provide multiple Ready IPv4 pools with different capacity.
2. Request auto external access.
3. Exhaust all pools and repeat the request.
4. Inject a failure after capacity reservation but before parent persistence.

##### Expected results

- Greatest-capacity pool is selected; equal-capacity selection is deterministic.
- Exhaustion returns an API error and persists no parent, child, or capacity
  reservation.
- Rollback releases capacity and leaves no orphan.
- Internal auto-provisioning children begin Pending and activate only after
  the target IP and ExternalIP are ready.

#### TC-R5-02: ExternalIPAttachment and NATGateway endpoint rules are enforced

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Expected results

- Compute/BM attachments use `UNSPECIFIED` endpoint.
- Cluster attachments use exactly `API` or `INGRESS`.
- Target oneof has exactly one arm.
- NATGateway requires a Ready VN and unconsumed Allocated ExternalIP.
- Malformed manager SNAT/DNAT status never produces Ready.

### R6: Create/read/delete-only operations and dependency guards

#### TC-R6-01: Network-owned updates are rejected everywhere

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- API update, patch, replace, and field-mask mutation;
- nested Subnet, SecurityGroup, CIDR, rule, interface, primary, endpoint,
  target, list-length/order, and auto-external mutations;
- direct hub-CR mutation;
- status write attempting to mutate spec.

##### Expected results

- Every network-owned mutation is rejected.
- Controller may change only status, conditions, timestamps, discovered IPs,
  and finalizers.
- Delete/recreate is the only supported network-spec change path.

#### TC-R6-02: Leaf-first deletion and finalizers protect dependencies

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | critical | automated |

##### Expected results

- Parent deletion is blocked while children or reverse references exist.
- Auto-created ExternalIPAttachment is deleted before ExternalIP.
- ExternalIP is deleted before ExternalIPPool.
- Subnets, SecurityGroups, and NATGateway are gone before VN deletion.
- VN is deleted before any provider VPC/backend parent.
- Concurrent deletion is idempotent and does not orphan backend state.

### R7: Direct CR bypass, state machine, and recovery

#### TC-R7-01: Admission and controllers enforce the same contract as the API

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration | critical | automated |

##### Expected results

- Direct CRs with invalid cardinality, IPv6, bad references, unsupported
  operations, or false Ready status are rejected or fail closed.
- A manager can transition Pending → Ready or Pending → Failed only through
  the documented reconciliation path.
- Pending dependencies requeue; terminal failures remain Failed.
- Restarting controllers does not duplicate jobs, allocations, rules,
  segments, or finalizers.

### R8: Cross-service interoperability

#### TC-R8-01: VMaaS, CaaS, and BMaaS consume a shared Ready Subnet

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | critical | automated |

##### Expected results

- VMaaS uses one virtual interface.
- CaaS uses one cluster attachment and BM worker enrichment.
- BMaaS uses one physical tenant attachment.
- All services preserve shared IPv4, same-VN, readiness, SecurityGroup, and
  create/read/delete-only rules.
- Multiple hosting clusters receive the required overlay for a shared Subnet
  when the K8s manager advertises that capability.
- Workloads in different VNs remain isolated.

### R9: Explicitly unsupported surface

#### TC-R9-01: Unsupported shared behavior is rejected or excluded

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated where user-visible |

##### Cases

- IPv6 or dual-stack;
- multi-CIDR pool;
- multi-interface VM/BM or multi-NIC tenant attachment;
- VN peering/cross-VN routing;
- multi-hub or air-gapped deployment;
- tenant-selected provider implementation or arbitrary IP;
- unsupported NATGateway capability;
- unsafe parent deletion;
- East-west update/resize behavior.

##### Expected results

- Unsupported user-visible requests fail with the documented error.
- Provider-only or future behavior is not advertised as a capability and does
  not dispatch a backend operation.

## Graduation gate

- Every normative shared validation rule maps to a unit or integration test.
- Every supported user workflow maps to an E2E test.
- Every user-visible unsupported workflow maps to an E2E rejection test.
- Negative tests verify no partial persistence or backend side effect.
- Concurrent create/delete, controller restart, manager failure, and cleanup
  tests pass.
