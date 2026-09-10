# Testplan — OSAC-1437 BMaaS Networking

## Overview

- **Feature:** OSAC-1437 — BMaaS Networking: Single NIC, Provisioning Handoff,
  DHCP Discovery, and Auto External Access
- **Source design:** [design.md](design.md)
- **Shared contract:** [Unified Networking test plan](../OSAC-1433-unified-networking/testplan.md)
- **Scope:** One tenant-facing physical attachment, BareMetalInstanceType
  interface validation, provisioning-network isolation, port move/reboot,
  DHCP lease discovery, CaaS private handoff, ExternalIP, and cleanup.
- **Prerequisite ownership:** The deployment-owned provisioning network,
  DHCP/gateway/SNAT, initial attach, BMC, inventory, and interface-MAC
  annotation exist before BMaaS begins. BMaaS does not create them.

## Execution strategy

- **Unit:** fulfillment-service validation, interface selection, operator phase
  ordering, move/DHCP request construction, status parsing, and cleanup.
- **Integration:** real PostgreSQL, BM CRD/controllers, fake Ironic/Metal3,
  dispatcher/AAP, fabric DHCP/IPAM, BMC, and feedback RPCs.
- **E2E:** real connected BMaaS with a provisioning network, fabric switch,
  inventory host, DHCP lease, reboot, tenant connectivity, ExternalIP, and
  cleanup.

## Test cases

### R1: One attachment and field-level defaulting

#### TC-R1-01: Omitted, empty, partial, and complete input

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Matrix

| Input | Expected result |
|---|---|
| List omitted/empty | One default Subnet, SecurityGroup, first fabric interface |
| Only Subnet | Preserve Subnet; fill only SecurityGroups/interface |
| Only SecurityGroups | Preserve SecurityGroups; fill only Subnet/interface |
| Only interface | Preserve interface; fill only Subnet/SecurityGroups |
| Complete entry | Preserve every supplied field |
| Invalid explicit value | Reject; never replace with default |

##### Expected results

- Persisted BM resource contains exactly one attachment after resolution.
- All references are Ready, same scope, same VN, IPv4, and unique.
- Omitted/true primary is accepted; sole entry is implicitly primary.

#### TC-R1-02: Multiple and false-primary inputs are rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Expected results

- More than one `network_attachments` entry is rejected before interface
  discovery, persistence, capacity reservation, or dispatch.
- Explicit `primary: false` is rejected.
- Direct API, Catalog, private CaaS, CRD, and controller paths agree.

### R2: BareMetalInstanceType and physical interface

#### TC-R2-01: First ordered fabric port is selected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Preconditions

- Ready BareMetalInstanceType contains multiple ordered ports, including
  fabric and lifecycle ports.

##### Expected results

- Omitted interface selects the first ordered `fabric` port.
- Supplied interface matches canonical port name and is preserved.
- Port list position, display label, tenant MAC, and arbitrary interface text
  are not alternate selectors.
- A later instance-type edit/reorder does not move an existing BM.

#### TC-R2-02: Ineligible interface requests fail closed

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- missing/Pending/Failed instance type;
- no fabric port;
- unknown interface;
- lifecycle, management, storage, or unknown-role port;
- inventory host lacks the selected port;
- selected port has no known MAC.

##### Expected results

- Tenant-visible invalid input is rejected before persistence.
- Infrastructure allocation failure remains Pending/Failed and never becomes
  Ready with a different port.
- No lifecycle or unrelated port is moved.

### R3: Provisioning network and handoff

#### TC-R3-01: Provisioning flow is isolated and ordered

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Steps

1. Allocate an unassigned host on the deployment provisioning network.
2. Complete inventory and OS provisioning.
3. Move only the selected fabric port to the tenant Subnet.
4. Reboot as required for fresh tenant DHCP.
5. Discover the tenant IP.

##### Expected results

- Phase order is inventory → provisioning → networking → reboot → IP
  discovery → Ready.
- Tenant cannot reach the host before the port move and readiness.
- Port move uses provisioning-network → tenant-network direction and selected
  logical interface only.
- Host does not retain the provisioning network after handoff.
- Deployment-owned provisioning network is consumed, not created, by BMaaS.

#### TC-R3-02: Deletion reverses the handoff safely

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E | critical | automated |

##### Expected results

- Host powers off while still on tenant network.
- Selected port moves tenant network → provisioning network.
- Host is not running tenant workload on provisioning network.
- Ironic/Metal3 cleanup runs after the network move.
- Subsequent inspection can use the provisioning network.

### R4: DHCP lease discovery and status

#### TC-R4-01: Correct lease becomes the sole status entry

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Cases

- lease matches selected port MAC;
- documented named-server fallback;
- lease delayed;
- wrong MAC/server;
- wrong Subnet;
- IPv6/malformed address;
- duplicate or multiple leases.

##### Expected results

- Only canonical IPv4 in the resolved Subnet is published.
- Status contains at most one interface/IP entry.
- Missing/wrong lease requeues and keeps BM non-Ready.
- Status feedback updates fulfillment-service without changing spec.

### R5: Automatic ExternalIP

#### TC-R5-01: Auto ExternalIP waits for BM IP

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | critical | automated |

##### Expected results

- Ready IPv4 pool and capacity are required.
- Parent, ExternalIP, and Pending ExternalIPAttachment are atomic.
- Attachment target is BM with `UNSPECIFIED` endpoint.
- DNAT waits for both ExternalIP Allocated and discovered BM IP.
- DNAT uses the selected interface's discovered IP only.
- VM/CaaS endpoint semantics are not accepted on the BM path.

#### TC-R5-02: Allocation and cleanup failure are safe

| Test type | Priority | Automation |
|---|---|---|
| Integration, E2E rejection/recovery | critical | automated |

##### Expected results

- Pool exhaustion leaves no BM, child, job, or capacity reservation.
- Auto attachment is deleted before ExternalIP and before parent finalizer
  removal.
- Manual ExternalIP resources remain tenant-managed.
- Transient finalizer/fabric failure retries without duplicate moves or IPs;
  permanent failure follows documented manual cleanup.

### R6: CaaS private handoff and Catalog parity

#### TC-R6-01: Private CaaS workers use normal BMaaS validation

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | high | automated |

##### Expected results

- Private request contains exactly one attachment with Cluster Subnet,
  SecurityGroups, and immutable node-set fabric interface.
- BMaaS revalidates port role, type, scope, readiness, and same-VN.
- Private caller cannot inject a second attachment or lifecycle port.

#### TC-R6-02: Catalog and direct BM creates are equivalent

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E | high | automated |

##### Expected results

- Locked/editable policy and tenant/default precedence match direct creation.
- Shared Catalog Items cannot lock/default tenant-local references.
- Catalog metadata and existing BM network specs remain unchanged after policy
  updates.

### R7: Immutability and unsupported BM networking

#### TC-R7-01: Network-owned fields are immutable

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated |

##### Cases

- attachment list, Subnet, SecurityGroups, interface, primary;
- auto-external switch;
- status attempt to mutate spec;
- update, patch, replace, and nested field mask;
- in-place Ready-resource re-provision handoff reset.

##### Expected results

- All unsupported changes are rejected; delete/recreate is required.
- Controller may update status, conditions, IP, and finalizers only.

#### TC-R7-02: Unsupported host-network behavior is rejected

| Test type | Priority | Automation |
|---|---|---|
| Unit, integration, E2E rejection | critical | automated where user-visible |

##### Cases

- multi-NIC or second tenant attachment;
- tenant-selected MAC, DHCP address, static host config, alternate IPAM, or
  lifecycle/provisioning interface;
- moving all host ports;
- BMaaS VM/KubeVirt networking operations;
- operator creation of the deployment provisioning network.

##### Expected results

- Unsupported behavior is rejected or remains deployment-owned/out of scope.
- No tenant access or backend mutation occurs.

## Graduation gate

- Every BMaaS server-validation rule and phase-ordering rule has unit or
  integration coverage.
- E2E covers one-attachment success, isolation, port move, reboot, DHCP,
  ExternalIP, CaaS handoff, deletion, and recovery.
- Every user-visible unsupported interface, cardinality, IP, and update path
  has a negative test.
