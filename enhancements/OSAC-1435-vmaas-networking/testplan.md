# Testplan — OSAC-1435 VMaaS Networking

## Overview

- **Feature:** OSAC-1435 — VMaaS Networking: Single Interface, Optional
  Attachments, and Auto External Access
- **Source design:** [design.md](design.md)
- **Shared contract:** [Unified Networking test plan](../OSAC-1433-unified-networking/testplan.md)
- **Current support boundary:** `compute_network_attachments` remains a list
  for compatibility but accepts zero or one entry. Multi-interface VM support
  is not supported.
- **Compatibility boundary:** deprecated field-14 `network_attachments` may
  be converted when supplied alone; supplying both old and canonical fields is
  rejected.

## Execution strategy

- **Unit:** fulfillment-service migration/defaulting/reference validators,
  Compute controller helpers, template input validation, feedback/status
  parsing, and ExternalIP transaction logic.
- **Integration:** real PostgreSQL, public/private/Catalog handlers, Compute
  CRD/CEL validation, osac-operator, fake K8s manager/KubeVirt, and
  controllable VMI/manager status.
- **E2E:** connected VMaaS deployment with real KubeVirt/CUDN placement,
  DHCP/IP discovery, ExternalIP/DNAT, and cleanup.

## Test cases

### R1: Single-interface request and migration contract

#### TC-R1-01: Zero or one canonical attachment is accepted

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Cases

- canonical field omitted;
- canonical field explicitly empty;
- one entry with omitted `primary`;
- one entry with `primary: true`.

##### Expected results

- The request is accepted according to defaulting semantics.
- The resolved resource contains exactly one attachment.
- The sole attachment is implicitly primary.

#### TC-R1-02: Multiple and false-primary inputs are rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Steps

1. Submit two canonical entries.
2. Submit one entry with explicit `primary: false`.
3. Repeat through public API, private API, Catalog, REST, and direct CR.

##### Expected results

- Each request is rejected before reference lookup, defaulting, capacity
  reservation, persistence, or template dispatch.
- Error identifies `spec.compute_network_attachments` or the precise primary
  field.

#### TC-R1-03: Deprecated field conversion is safe

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | high | automated |

##### Expected results

- Field 14 alone with zero/one entry is converted to the canonical message.
- A converted sole entry is implicitly primary.
- Field 14 and field 18 supplied together are rejected even when one is empty.
- A second deprecated entry is rejected.
- Explicit invalid values are never rewritten during conversion.

### R2: Attachment defaulting and readiness

#### TC-R2-01: VM attachment fields resolve independently

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Matrix

| Input | Expected result |
|---|---|
| Missing/empty list | Default Subnet and default SecurityGroup |
| Only Subnet | Preserve Subnet; fill only SecurityGroups |
| Only SecurityGroups | Preserve SecurityGroups; fill only Subnet |
| Complete entry | Preserve Subnet and SecurityGroups exactly |
| Invalid explicit reference | Reject; do not repair with defaults |

##### Expected results

- Catalog/Template resolution occurs before tenant defaults.
- Subnet and every SecurityGroup are Ready, same scope, same VN, IPv4, and
  unique before ComputeInstance persistence.
- A missing/Pending/Failed default blocks creation.

#### TC-R2-02: K8s-manager capability gates VM creation

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Expected results

- K8s-only VM placement succeeds when the manager advertises VM support.
- Fabric-only/BM-only deployment rejects VM creation before persistence.
- EVPN or other prerequisite-gated manager accepts the VM only when Subnet,
  namespace/CUDN, and manager readiness checks pass.
- VMaaS does not require a Fabric Manager when the K8s-only capability is
  complete.

### R3: Single-interface provisioning and status

#### TC-R3-01: Template creates exactly one KubeVirt interface

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Steps

1. Create a valid ComputeInstance with one resolved attachment.
2. Observe the operator/template input.
3. Inspect the resulting VirtualMachine/VMI.

##### Expected results

- One `l2bridge` interface is created in the selected CUDN namespace.
- No `move_network_attachment` operation is invoked.
- A malformed CR with multiple entries fails closed rather than using the
  first entry.

#### TC-R3-02: IP feedback publishes only a valid sole status entry

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | high | automated |

##### Cases

- canonical IPv4 in the selected Subnet;
- missing status while VMI is starting;
- wrong NAD/subnet;
- IPv6 or malformed IP;
- duplicate or multiple VMI interfaces.

##### Expected results

- Only the valid sole interface produces a Ready network status.
- Invalid or ambiguous status causes retry/failure and never mutates spec or
  reports a false Ready IP.

### R4: Automatic ExternalIP

#### TC-R4-01: Automatic VM external access succeeds

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Steps

1. Create a VM with `auto_external_ip_attachment=true`.
2. Verify one IPv4 ExternalIP and Pending ExternalIPAttachment are created
   atomically.
3. Complete ExternalIP allocation and VM IP discovery independently.
4. Verify DNAT and inbound connectivity.

##### Expected results

- Attachment target is the VM and endpoint is `UNSPECIFIED`.
- DNAT dispatch waits for both prerequisites.
- DNAT uses the discovered sole interface IP, not a tenant-supplied IP.

#### TC-R4-02: Automatic allocation failure rolls back

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Expected results

- Pool selection uses greatest capacity and deterministic ties.
- Exhaustion or any validation failure leaves no VM, ExternalIP,
  ExternalIPAttachment, job, or capacity reservation.
- Cleanup retries attachment before ExternalIP.

### R5: Immutability and cleanup

#### TC-R5-01: Network-owned changes are rejected after create

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- attachment list/cardinality/order;
- Subnet;
- SecurityGroups;
- primary;
- auto-external switch;
- nested field-mask and direct CR mutations.

##### Expected results

- All are rejected. Controller status, conditions, discovered IP, and
  finalizers remain writable by controllers.
- Delete/recreate is required for a network change.

#### TC-R5-02: Parent deletion follows ownership rules

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | high | automated |

##### Expected results

- Auto-created attachment is deleted before auto-created ExternalIP.
- Manually created ExternalIP resources remain tenant-managed.
- Shared default VN/Subnet/SecurityGroup are not deleted with the VM.
- Restart or transient cleanup failure does not leak duplicate children.

### R6: Unsupported VM networking

#### TC-R6-01: Future or invalid VM networking is rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated where user-visible |

##### Cases

- multi-interface/multi-NIC VM;
- explicit false primary;
- cross-tenant, cross-VN, non-Ready, IPv6, or fabric-only Subnet;
- tenant-selected implementation strategy, CUDN namespace, MAC, or IPAM;
- arbitrary ExternalIP target IP;
- update/patch/replace;
- BM/CaaS port-move behavior for VM;
- static host-side networking.

##### Expected results

- Unsupported behavior is rejected or fails closed and no partial resource is
  persisted.

### R7: Catalog parity

#### TC-R7-01: Direct and Catalog creation produce the same contract

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | high | automated |

##### Expected results

- Locked, editable, empty, and default policies resolve before tenant default
  networking.
- Both direct and Catalog creates enforce zero-or-one and primary rules.
- Shared Catalog Items cannot lock/default tenant-local references.
- Catalog updates do not mutate existing VM network specs or Catalog metadata.

## Graduation gate

- Every VMaaS validation rule has unit or integration coverage.
- One-interface success, defaults, migration, auto ExternalIP, cleanup, and
  K8s-only capability have E2E coverage.
- Every user-visible unsupported VM networking path has a negative E2E test.
