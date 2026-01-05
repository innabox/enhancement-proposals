---
title: Pluggable Inventory Sources
authors:
  - Juan Hernández
creation-date: 2025-12-10
last-updated: 2025-12-10
tracking-link:
  - TBD
replaces:
superseded-by:
---

# Pluggable Inventory Sources

## Summary

This document proposes enhancements to the fulfillment service to support pluggable inventory
sources. An inventory source is an external system that manages the physical infrastructure
(hosts, racks, network configuration, etc.) and provides this information to the fulfillment
service. By supporting pluggable inventory sources, the fulfillment service can integrate with
different datacenter management systems without requiring changes to its core logic.

The proposal includes API extensions to hosts, host classes, clusters, and hubs that capture the
additional hardware and configuration details needed for provisioning bare-metal infrastructure.
It also introduces a synchronization architecture where inventory source adapters run as separate
deployments and communicate with the fulfillment service through its private API.

## Motivation

The fulfillment service needs to provision clusters on bare-metal hosts. However, physical
infrastructure is typically managed by specialized datacenter management systems such as NVIDIA
Base Command Manager (BCM), OpenStack Ironic, or custom inventory databases. Each of these systems
has its own API, data model, and capabilities.

Rather than embedding support for each inventory source directly into the fulfillment service, a
pluggable architecture allows:

- Integration with existing datacenter management systems without modifying core service logic.
- Different deployments to use different inventory sources based on their infrastructure.
- Independent development and maintenance of inventory source adapters.
- Testing and validation of the core service without requiring access to physical infrastructure.

### User Stories

- As a provider, I want to integrate my existing datacenter management system with the fulfillment
  service so that I can leverage my current inventory data.
- As a provider, I want to define host classes that map to my hardware categories so tenants can
  request specific types of resources.
- As a provider, I want the fulfillment service to automatically discover hosts from my inventory
  system and keep the data synchronized.
- As a provider, I want to configure BMC (Baseboard Management Controller) credentials so the
  service can power on/off hosts during provisioning.
- As a tenant, I want to see which hosts are assigned to my clusters so I can understand my
  resource allocation.

### Goals

- Define API extensions to capture hardware details needed for bare-metal provisioning.
- Establish a synchronization pattern for inventory source adapters.
- Support hub configuration for HyperShift-based cluster provisioning.
- Enable host assignment tracking for clusters.
- Identify DNS provisioning as a required capability for cluster creation.

### Non-Goals

The following are explicitly out of scope for this proposal:

- Implementation of specific inventory source adapters beyond the example provided.
- Automatic hardware discovery without an inventory source.
- Network topology management (addressed by VDCaaS proposal).
- Storage management and provisioning.
- Detailed DNS provisioning implementation (mentioned as a requirement but implementation details
  are out of scope).
- Mandating a specific host provisioning mechanism. While this document uses `BareMetalHost`
  resources (from the Metal3 project) as an example for provisioning bare-metal hosts, the
  pluggable inventory source architecture does not require this specific technology. Other
  provisioning mechanisms (e.g., Ironic directly, vendor-specific tools) can be used depending
  on the deployment environment.

## Proposal

### API Extensions

To support bare-metal provisioning, the fulfillment service API requires extensions to capture
hardware details, BMC configuration, and host assignment information.

#### Host Type Extensions

The host type requires additional fields to store hardware and provisioning details:

**Spec fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bmc` | `BMC` | BMC (Baseboard Management Controller) connection details |
| `rack` | `string` | Physical rack location |
| `class` | `string` | Reference to the host class identifier |
| `boot_mac` | `string` | MAC address of the network interface used for PXE boot |
| `boot_ip` | `string` | IP address assigned for network boot |
| `title` | `string` | Human-readable title |
| `description` | `string` | Detailed description |

The `BMC` message contains:

| Field | Type | Description |
|-------|------|-------------|
| `url` | `string` | URL of the BMC interface (e.g., `redfish-virtualmedia://10.0.0.1/redfish/v1/Systems/1`) |
| `user` | `string` | Username for BMC authentication |
| `password` | `string` | Password for BMC authentication |
| `insecure` | `bool` | Whether to skip TLS certificate verification |

**Status fields:**

| Field | Type | Description |
|-------|------|-------------|
| `cluster` | `string` | Identifier of the cluster this host is assigned to |
| `hub` | `string` | Identifier of the hub managing this host |

#### Cluster Type Extensions

The cluster type requires extensions to track host assignments:

**Status fields:**

| Field | Type | Description |
|-------|------|-------------|
| `alias` | `string` | Short alias used for Kubernetes object names in the hub |
| `port` | `int32` | NodePort number allocated for the cluster API service |

**ClusterNodeSet extensions:**

| Field | Type | Description |
|-------|------|-------------|
| `hosts` | `repeated string` | List of host identifiers assigned to this node set |

#### Hub Type Extensions

The hub type requires additional configuration for HyperShift-based provisioning:

| Field | Type | Description |
|-------|------|-------------|
| `pull_secret` | `string` | Docker configuration JSON for pulling container images |
| `ssh_public_key` | `string` | SSH public key to install on provisioned hosts |
| `ip` | `string` | IP address of the hub cluster (used for DNS configuration) |

### Hub Reconciler

A new hub reconciler is introduced to manage the Kubernetes resources required for HyperShift-based
cluster provisioning. When a hub is created or updated, the reconciler ensures the following
resources exist in the hub cluster:

1. **Namespace**: A dedicated namespace for the fulfillment service resources.

2. **Pull Secret**: A Kubernetes secret containing Docker registry credentials for pulling
   container images during cluster installation.

3. **InfraEnv**: An Agent-based installer `InfraEnv` resource that configures the discovery ISO
   parameters, including SSH authorized keys and network configuration.

4. **CAPI Provider Role**: An RBAC role granting the Cluster API provider access to manage Agent
   resources for bare-metal provisioning.

The hub reconciler also starts a Kubernetes resource watcher for each hub. This watcher monitors
changes to relevant Kubernetes resources, signaling the appropriate fulfillment service entities
when changes occur. This enables reactive reconciliation instead of polling.

For example, in a HyperShift-based deployment using Metal3 for bare-metal provisioning, the
watcher would monitor `HostedCluster`, `NodePool`, `BareMetalHost`, and `Agent` resources.
Different provisioning mechanisms may require watching different resource types.

### Inventory Synchronization Architecture

Inventory source adapters follow a common architecture pattern:

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│                     │     │                     │     │                     │
│  Inventory Source   │────▶│  Synchronizer       │────▶│  Fulfillment        │
│  (BCM, Ironic, etc) │     │  Deployment         │     │  Service            │
│                     │     │                     │     │                     │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

The synchronizer is deployed as an optional component, separate from the core fulfillment service.
It periodically queries the inventory source and updates the fulfillment service database through
the private gRPC API. This design provides:

- **Loose coupling**: The core service has no knowledge of specific inventory sources.
- **Independent scaling**: Synchronizers can be scaled and configured independently.
- **Failure isolation**: Inventory source issues don't affect core service operations.
- **Flexible deployment**: Only the needed synchronizers are deployed for each environment.

#### Synchronization Protocol

Inventory synchronization should preferably be **event-driven**, with periodic synchronization
serving as a fallback mechanism. This approach minimizes latency and reduces unnecessary API calls.

**Event-Based Synchronization (Preferred)**

When the inventory source supports event notifications (webhooks, message queues, change streams,
etc.), the synchronizer should:

1. **Subscribe**: Register for change events from the inventory source.

2. **React**: When an event is received, fetch only the affected resource(s) from the inventory
   source.

3. **Transform**: Convert the inventory source data model to the fulfillment service data model.

4. **Reconcile**: Use the private API to create, update, or delete the corresponding fulfillment
   service entity.

**Periodic Synchronization (Fallback)**

When event-based synchronization is not available, or as a complement to catch missed events, the
synchronizer falls back to periodic polling:

1. **Fetch**: Query the inventory source for the current state of all resources (hosts,
   categories, racks, etc.).

2. **Transform**: Convert the inventory source data model to the fulfillment service data model.
   This includes extracting relevant metadata from inventory source fields.

3. **Reconcile**: For each resource, use the private API to create or update the corresponding
   fulfillment service entity. The synchronizer uses field masks to update only the fields it
   manages.

4. **Repeat**: Wait for the configured interval and repeat the process.

**Hybrid Approach**

The recommended pattern is to combine both mechanisms:

- Use event-based synchronization for real-time updates.
- Run periodic synchronization at longer intervals (e.g., hourly) to catch any missed events and
  ensure eventual consistency.
- Track synchronization state to avoid redundant updates when both mechanisms report the same
  change.

#### Host Class Mapping

Host classes in the fulfillment service correspond to hardware categories in the inventory source.
The synchronizer maps inventory categories to host classes, preserving:

- Unique identifier from the inventory source
- Human-readable name
- Title and description (extracted from inventory source metadata if available)

#### Host Synchronization

For each host in the inventory source, the synchronizer:

1. Searches for an existing host by identifier or name.
2. Creates a new host if not found, using the inventory source identifier.
3. Updates the host spec with BMC details, boot MAC/IP, rack location, and host class reference.
4. Updates links back to the inventory source for operator reference.

### Example: BCM Synchronizer

An example implementation for NVIDIA Base Command Manager (BCM) demonstrates the synchronization
pattern. The initial implementation uses periodic synchronization; future iterations should
leverage BCM's event capabilities if available to enable real-time updates.

It is deployed as a separate Helm chart (`bcm-sync`) with the following configuration:

| Parameter | Description |
|-----------|-------------|
| `bcm.url` | URL of the BCM API endpoint |
| `bcm.credentialsSecret` | Kubernetes secret containing TLS client certificate and key |
| `bcm.syncInterval` | Interval between synchronization cycles |
| `grpc.server.address` | Address of the fulfillment service gRPC endpoint |

The BCM synchronizer maps:

- BCM device categories → Host classes
- BCM devices (LiteNode type) → Hosts
- BCM rack positions → Host rack field
- BCM BMC settings → Host BMC configuration
- BCM network interfaces → Boot MAC and IP addresses

### Workflow Integration

Host assignment for clusters follows this general flow:

1. **Host Discovery**: Synchronizer creates/updates hosts with hardware details and host class
   references.

2. **Cluster Creation**: Tenant requests a cluster with node sets specifying host class and count.

3. **Host Selection**: Cluster reconciler selects unassigned hosts matching the requested host
   class.

4. **Host Provisioning**: Reconciler triggers the provisioning mechanism with BMC credentials
   from the host spec.

5. **Host Registration**: When hosts boot and complete provisioning, they are registered with
   the cluster.

6. **Status Update**: Host status is updated with the assigned cluster and hub identifiers.

#### Example: HyperShift with Metal3

As a concrete example, when using HyperShift with Metal3 for bare-metal provisioning, the workflow
becomes:

1. **Host Discovery**: Same as above.

2. **Cluster Creation**: Same as above.

3. **Host Selection**: Same as above.

4. **BareMetalHost Creation**: Reconciler creates `BareMetalHost` resources in the hub cluster
   with BMC credentials from the host spec. Metal3 manages the hardware lifecycle.

5. **Agent Binding**: When hosts boot and register as Agents, they are bound to the appropriate
   `HostedCluster`.

6. **Status Update**: Same as above.

Other provisioning mechanisms would implement steps 4-5 differently while maintaining the same
overall inventory synchronization and host selection patterns.

### DNS Provisioning Requirements

Bare-metal cluster provisioning requires dynamic DNS record management. When a cluster is created,
the fulfillment service must provision DNS records for:

- **API endpoint**: `api.<cluster-alias>.<base-domain>` pointing to the hub cluster IP where the
  hosted control plane runs.
- **Internal API endpoint**: `api-int.<cluster-alias>.<base-domain>` for internal cluster
  communication.
- **Ingress wildcard**: `*.apps.<cluster-alias>.<base-domain>` for application routes.

The DNS provisioning mechanism must support:

- Dynamic record creation when clusters are provisioned.
- Record cleanup when clusters are deleted.
- Authentication with the DNS server (e.g., TSIG keys for BIND).
- Both A records and wildcard records.

The specific implementation of DNS provisioning (which DNS server to use, authentication
mechanism, etc.) is deployment-specific and may vary between environments. The fulfillment
service should provide a pluggable or configurable mechanism for DNS updates, similar to the
inventory source pattern.

### Risks and Mitigations

**Risk**: Synchronization conflicts if multiple sources manage the same hosts.

**Mitigation**: Each host should be managed by a single inventory source. The host identifier
should be stable and unique across sources.

**Risk**: Stale data if synchronization fails.

**Mitigation**: Synchronizers should log failures clearly and expose health metrics. Operators
should monitor synchronization health.

**Risk**: Security of BMC credentials in transit and at rest.

**Mitigation**: BMC passwords are stored in the fulfillment service database. The gRPC connection
between synchronizer and service should use TLS. Future work may introduce secret references
instead of inline passwords.

**Risk**: DNS provisioning failures leave clusters unreachable.

**Mitigation**: DNS record creation should be idempotent and retried on failure. The cluster
reconciler should verify DNS records are resolvable before marking the cluster as ready. Cleanup
of DNS records during cluster deletion should be best-effort to avoid blocking deletion.

### Drawbacks

- Additional deployment complexity with separate synchronizer components.
- When event-based synchronization is not available, falling back to periodic synchronization
  introduces latency for inventory changes.
- Not all inventory sources support event notifications, limiting real-time synchronization
  capabilities in some environments.
- BMC credentials are stored in the fulfillment service database, requiring appropriate security
  measures.

## Alternatives

### Embedded Inventory Source Support

Embedding inventory source adapters directly in the fulfillment service was considered but
rejected because:

- It would require service redeployment to add new inventory sources.
- It would increase the core service's complexity and dependency footprint.
- It would make testing harder without access to all supported inventory systems.

### Direct API Integration

Having the fulfillment service query inventory sources on-demand was considered but rejected
because:

- It would create tight coupling between the service and inventory source availability.
- It would add latency to operations that need inventory data.
- It would complicate error handling when inventory sources are unavailable.

## Test Plan

- Unit tests for API extensions and field handling.
- Integration tests with mock inventory data.
- End-to-end tests with BCM synchronizer against a test BCM instance.

## Graduation Criteria

- API extensions are stable and documented.
- BCM synchronizer is deployed and validated in a production-like environment.
- Documentation covers creating custom inventory source adapters.

### Dev Preview

- API extensions implemented in private API.
- BCM synchronizer functional with periodic synchronization as initial implementation.

### Tech Preview

- API extensions evaluated for public API inclusion.
- Event-based synchronization implemented for inventory sources that support it.
- Hybrid synchronization pattern (events + periodic fallback) validated.
- Monitoring and alerting guidance documented.

### GA

- Public API stable for tenant-facing fields.
- Multiple inventory source adapters validated.
- Security review completed for credential handling.

## Upgrade / Downgrade Strategy

New fields are additive and optional. Existing deployments without inventory sources continue to
work. Downgrading removes synchronizer functionality but preserves manually-created host data.

## Version Skew Strategy

Synchronizers should be compatible with the fulfillment service version they were released with.
Minor version skew between synchronizer and service is acceptable. Major version changes may
require synchronizer updates.

## Support Procedures

- Synchronizer logs should be checked for connection and authentication errors.
- Host data can be verified through the private API.
- Stale hosts can be manually deleted or updated through the private API.

## Infrastructure Needed

- Access to inventory source for synchronizer deployment.
- TLS certificates for secure communication between synchronizer and fulfillment service.
- Network connectivity between synchronizer, inventory source, and fulfillment service.
- DNS server with dynamic update support (e.g., BIND with TSIG authentication) for cluster
  endpoint records.
- DNS zone delegated to the fulfillment service for cluster domains.
