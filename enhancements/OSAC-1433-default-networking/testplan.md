# Testplan — OSAC-1433 Default Networking

## Overview

- **Feature:** OSAC-1433 — Default Networking and simplified resource creation
- **Source design:** [design.md](design.md)
- **Shared contract:** [Unified Networking test plan](../OSAC-1433-unified-networking/testplan.md)
- **Scope:** Tenant onboarding, default-resource lifecycle, readiness, default
  attachment resolution, auto ExternalIP creation, cleanup, and supported
  combined-manager/K8s-only behavior.
- **Non-goals:** Per-tenant default configuration, additional automatic VN or
  Subnet creation, retroactive migration of existing resources, and UI
  support. API, REST, private API, and CLI are the tested surfaces.

## Execution strategy

- **Unit:** fulfillment-service defaulting, onboarding, readiness, pool
  selection, and rollback logic with fake manager status.
- **Integration:** real ephemeral PostgreSQL, fulfillment-service validation
  and authorization, envtest/Kind CRDs/controllers, and controllable manager
  jobs/feedback.
- **E2E:** connected single-hub deployments using real tenants, API/CLI,
  operators, supported managers, and workload connectivity.

## Test cases

### R1: NetworkClass defaults are valid and mandatory

#### TC-R1-01: Valid defaults are accepted

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration | critical | automated |

##### Steps

1. Configure canonical IPv4 `virtual_network_cidr`.
2. Configure a contained canonical IPv4 `ipv4_subnet_cidr`.
3. Configure `metallb_vip_prefix_length` when CaaS/MetalLB capability is
   advertised.

##### Expected results

- NetworkClass is accepted.
- There is no separate enable/disable knob for defaults.
- The conditional MetalLB field is required only when its capability is
  advertised; no universal default is invented.

#### TC-R1-02: Invalid defaults are rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- missing `spec.defaults`;
- malformed, IPv6, dual-stack, or host-bit CIDR;
- Subnet outside/equal to VN;
- missing conditional MetalLB prefix;
- unsupported manager capability;
- tenant attempts to configure provider-only defaults.

##### Expected results

- NetworkClass creation fails before any tenant onboarding.
- No partial default graph is created.

### R2: Tenant onboarding creates exactly the supported graph

#### TC-R2-01: Combined-manager onboarding

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | critical | automated |

##### Preconditions

- Valid combined-manager NetworkClass.
- Tenant does not already have defaults.

##### Expected results

- Exactly one default VirtualNetwork, IPv4 Subnet, and fallback SecurityGroup
  are created with tenant ownership and default labels.
- NATGateway and its auto ExternalIP are created only when capability supports
  NATGateway.
- The deployment-wide permit baseline is present independently of the tenant
  fallback SecurityGroup's rule list.

#### TC-R2-02: K8s-only onboarding excludes NATGateway

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Expected results

- VN, Subnet, and fallback SecurityGroup become Ready.
- No NATGateway create or NAT backend operation is attempted.
- NATGateway is excluded from the readiness set, not left Pending or Failed.
- A later tenant NATGateway request is rejected by capability validation.

#### TC-R2-03: Onboarding is idempotent and does not create extra defaults

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration | high | automated |

##### Steps

1. Submit duplicate/concurrent onboarding requests.
2. Restart onboarding reconciliation between each default resource.
3. Repeat with an exactly matching existing graph.
4. Repeat with a mismatched existing graph.

##### Expected results

- Matching graph is adopted idempotently.
- No duplicate default resources, jobs, or capacity reservations are created.
- A mismatched graph is a provider configuration error, not silently adopted.

### R3: Default readiness and failure recovery

#### TC-R3-01: Readiness waits for every supported default

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Cases

- VN Pending/Failed;
- Subnet Pending/Failed;
- fallback SecurityGroup Pending/Failed;
- supported NATGateway Pending/Failed;
- feedback for another tenant or another VN;
- all expected resources Ready.

##### Expected results

- `DefaultNetworkingReady` stays false until every capability-required object
  is Ready and has the expected parent/identity.
- A workload relying on an unavailable default is rejected or remains blocked
  according to the shared contract.
- Existing immutable workload attachments are not rewritten if readiness later
  degrades.

#### TC-R3-02: Failure and documented recovery path

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | high | automated |

##### Steps

1. Fail each default manager operation independently.
2. Verify condition reason and non-Ready tenant state.
3. Restore the manager and exercise controller retry.
4. Exercise provider repair followed by tenant recreation, the documented
   recovery path for a terminal onboarding graph.

##### Expected results

- Failure is visible on the Tenant condition and events.
- Controllers requeue transient failures without marking false Ready.
- Recovery produces one clean default graph.

### R4: Workload default resolution

#### TC-R4-01: Omitted, empty, partial, and complete inputs

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Matrix

| Resource/input | Expected result |
|---|---|
| VM field omitted or empty | One default Subnet and SecurityGroup |
| Cluster message omitted or empty | One attachment containing both defaults |
| BM list omitted or empty | One attachment with defaults and first eligible fabric interface |
| Only Subnet supplied | Preserve Subnet; fill only SecurityGroups |
| Only SecurityGroups supplied | Preserve SecurityGroups; fill only Subnet |
| Complete input supplied | Preserve every network field |
| Invalid explicit value | Reject; never repair with defaults |

##### Expected results

- Catalog/Template precedence runs before tenant defaulting.
- Every resolved reference is Ready, same-scope, same-VN, and valid for the
  owning service.
- VM/BM cardinality and primary restrictions remain enforced.

#### TC-R4-02: Default resources and fields are immutable

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Expected results

- Update, patch, replace, and field-mask changes to default network fields are
  rejected.
- Delete is blocked while workloads or reverse references remain.
- Delete/recreate is required to change a default network specification.

### R5: Auto ExternalIP lifecycle

#### TC-R5-01: Successful automatic external access

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | critical | automated |

##### Steps

1. Enable auto external access for VM, Cluster, and BM workflows.
2. Verify pool selection and atomic child creation.
3. Complete target IP/VIP discovery.
4. Verify ExternalIPAttachment dispatch and connectivity.

##### Expected results

- Correct number of ExternalIPs is allocated: one for VM/BM and two for
  Cluster API/Ingress.
- Children start Pending and dispatch only after all prerequisites are Ready.
- DNAT targets the discovered workload IP/VIPs.
- Parent deletion removes auto-created attachment before ExternalIP.

#### TC-R5-02: Capacity and partial-failure rollback

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Expected results

- Pool selection prefers greatest available capacity and deterministic ties.
- Exhaustion returns an API error.
- Parent, ExternalIP, ExternalIPAttachment, and capacity reservation are all
  absent after failure.
- Transient cleanup failure retries; permanent cleanup follows the documented
  orphan/manual-cleanup behavior.

### R6: Unsupported Default Networking behavior

#### TC-R6-01: Unsupported scope is not silently enabled

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | high | automated where user-visible |

##### Cases

- per-tenant custom default CIDRs/configuration;
- automatic additional VN/Subnet creation;
- retroactive defaults for existing tenants;
- UI-only simplified creation;
- tenant-created empty SecurityGroup used as fallback;
- workload create with missing/Pending/Failed defaults;
- unsafe parent/default deletion;
- network-owned update/patch/replace;
- arbitrary ExternalIP selection.

##### Expected results

- Unsupported behavior is rejected or excluded from this API/CLI scope.
- No hidden fallback or partial resource graph is created.

## Graduation gate

- Every onboarding and defaulting rule maps to a unit or integration test.
- Combined-manager and K8s-only supported workflows have E2E coverage.
- All three workload services have omitted/empty/partial/complete coverage.
- Failure, retry, idempotency, capacity rollback, cleanup, and immutability
  tests pass.
