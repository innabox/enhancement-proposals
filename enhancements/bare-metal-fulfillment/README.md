---
title: bare-metal-fulfillment
authors:
  - Tzu-Mainn Chen
creation-date: 2025-09-08
last-updated: 2025-09-15
tracking-link:
  - None
see-also:
  - None
replaces:
  - None
superseded-by:
  - None
---

# Bare Metal Fulfillment

## Summary

Bare metal fulfillment refers to the process through which a tenant acquires bare metal hosts and configures their networking.
Afterwards, the tenant will be able to perform selected operations on the host: inventory information, power control, and
serial console access. Any further operations - for example, image-based provisioning - are outside the scope of the O-SAC
solution and must be integrated by the cloud provider.

We believe this feature set is generic enough to support a wide range of desired bare metal cluster use cases, including:

* support for an environment where developers have to flexibility to install their own operating systems and software
* support for alternative clusters such as SLURM
* support for bare metal configuration during O-SAC cluster fulfillment

In this context, a “tenant” is a person with admin rights to the requested bare metal resources; at the MOC, this person would be
a ColdFront PI or manager.

## Motivation

Bare metal fulfillment is a fundamental requirement for O-SAC, identified as an explicit need for the MOC. It will also serve
as the basis of bare metal configuration for other fulfillment workflows, such as OpenShift cluster fulfillment.

### User Stories

* As a provider, I want to be able to define the available bare metal resource classes.
* As a provider, I want to mark hosts as available for bare metal fulfillment.
* As a tenant, I want to be able to see available bare metal resource classes.
* As a tenant, I want to be able to select hosts for a bare metal cluster by resource class.
* As a tenant, I want to be able to view inventory details for my hosts.
* As a tenant, I want to be able to connect to the serial console of my hosts.
* As a tenant, I want to be able to perform basic power control (power on/power off/reset) of my hosts.
* As a tenant, I want to be able to attach hosts to existing networks.
* As a tenant, I want to be able to modify the network connectivity of my hosts by attaching or detaching networks.
* As a tenant, I want to be able to manage connectivity at the interface level in order to support hardware that may have both regular and high performance interfaces (for example, some hosts may have high-bandwidth connectivity for GPU workloads, and it may be necessary to attach specific networks to these interfaces).

### Goals

We will implement bare metal fulfillment in the O-SAC solution, covering the user stories described above. This implementation will
be first deployed and tested in the MOC; as a result, the implementation will rely upon ESI for bare metal management (although
it will be designed to allow easy replacement of the bare metal management layer). While not addressed in this proposal, a long term goal
of bare metal fulfillment is to have it be used as the basis of bare metal configuration during cluster fulfillment.

### Non-Goals

We will not look into alternatives for ESI; that work will be covered through a future enhancement.

We will not substantially modify the existing cluster fulfillment workflow at this time.

## Proposal

The implementation of bare metal fulfillment relies on three concepts:

* HostPool: A collection of requested bare metal machines, along with their desired network configuration.
* Host: An ephemeral resource created when bare metal resources are acquired from the underlying bare metal management layer. They represent the assignment of a bare metal resource to a HostPool, and provide an endpoint for host-specific operations.
* HostClass: Defines a set of bare metal properties, such as memory, CPU, and network interfaces. Each Host has a single HostClass attribute. HostClasses are defined by the provider.

At a high level, tenants will request a HostPool by specifying:

* the number and HostClass of hosts
* the network configuration to be applied to those hosts (note that this configuration applies to each individual host in the HostPool)

The O-SAC solution will assign the requested hosts to the tenant and create matching Host resources for each host. The tenant
can then perform needed operations upon the Host.

We expect bare metal fulfillment to follow the same workflow used for cluster fulfillment; as such, we expect to update the
following existing O-SAC components:

* Fulfillment Service: Define the API for HostPools, Hosts, and HostClasses
* Fulfillment CLI: Give the tenant access to the API
* O-SAC Operator: Manage and reconcile the Custom Resources for HostPools and Hosts
* O-SAC AAP: Use Ansible playbooks to perform the requested reconciliation operations of HostPools and Hosts by calling Bare Metal Management APIs.
* Bare Metal Management: Manage the hardware; we will use ESI for now

Much of the development work can simply follow the established patterns set by the cluster fulfillment workflow. However, the
following topics merit further discussion in the "Implementation Details/Notes/Constraints" below:

* ESI playbooks
* Serial console support

### Workflow Description

#### Host Pool Creation

1. The tenant uses the Fulfillment CLI to request a HostPool.
2. The O-SAC solution fulfills the request and creates Host resources corresponding to the allocated hosts.

#### Host Pool Network Update

1. The tenant uses the Fulfillment CLI to update the network configuration of a HostPool.
2. The O-SAC solution fulfills the request by updating the network configuration of the hosts in the HostPool.

#### Host Pool Expansion

1. The tenant uses the Fulfillment CLI to increase the number of requested hosts specified in a HostPool.
2. The O-SAC solution fulfills the request by adding the requested hosts into the HostPool.

#### Host Pool Reduction

1. The tenant uses the Fulfillment CLI to decrease the number of requested hosts specified in a HostPool.
2. The O-SAC solution fulfills the request by removing the requested hosts from the HostPool.

#### Host Operations

1. The tenant uses the Fulfillment CLI to see their Hosts.
2. The tenant uses the Fulfillment CLI to perform an operation upon the desired Host.

#### Host Pool Deletion

1. The tenant uses the Fulfillment CLI to delete a HostPool.
2. The O-SAC solution fulfills the request and removes the Host resources corresponding to the hosts in the HostPool.

### API Extensions

#### HostPools

A tenant requests bare metal resources by creating a HostPool. In the following example, the
tenant is requesting a HostPool with two fc430 hosts. Each host will have `network1` attached
as a native VLAN on one physical interface; and a trunk port with `network2` as a native VLAN
and `network3` as a tagged VLAN on a second physical interface.

    apiVersion: o-sac.openshift.io/v1alpha1
    kind: HostPool
    metadata:
      name: example
    spec:
      hostRequests:
      - resourceClass: fc430
        numberOfHosts: 2

      # The networkAttachments section controls how networks are connected to
      # physical interfaces.
      networkAttachments:
      # This configuration will match any available interface.
      - primary: network1
      - primary: network2
        vlans:
	- network3

Tenants can also attach networks to interfaces matching a specific property. In this example,
each fc430 will be configured with `network1` attached to any available physical interface,
while `storage-network` will only be attached to an interface with the `25gb` property.

    apiVersion: o-sac.openshift.io/v1alpha1
    kind: HostPool
    metadata:
      name: example
    spec:
      hostRequests:
      - resourceClass: fc430
        numberOfHosts: 2

      # The networkAttachments section controls how networks are connected to
      # physical interfaces.
      networkAttachments:
      # This configuration will match any available interface.
      - primary: network1
      # This configuration will only match interfaces with the `25gb` property
      - matches:
   	    property: 25gb
        primary: storage-network

If a tenant wishes to change the number of hosts or network configuration of their HostPool, they can simply update the HostPool.

#### Hosts

Tenants do not create Hosts directly; instead, they are created as part of the HostPool fulfillment workflow. Once created,
tenants can perform host-specific operations:

* Power control
* Serial console access
* Inventory information

To support these operations, we propose a new Hosts API. For example, we can implement power control as an attribute on the Host object:

    apiVersion: cloudkit.openshift.io/v1alpha1
    kind: Host
    metadata:
      name: example
    spec:
      powerState: PowerOn
      serialConsole: Enabled

### Implementation Details/Notes/Constraints

#### ESI Playbooks

The ESI API supports all of the needed bare metal functionality (the cluster fulfillment workflow already relies upon ESI
playbooks for bare metal network configuration) . However, it is important to recognize that O-SAC will not use the ESI concept
of tenancy; from an ESI perspective, hosts will always remain leased to the O-SAC project. As a result, we will need to introduce
a new method of keeping track of O-SAC tenancy.

One solution would be to rely upon Ironic’s extra field, which allows an ESI project to set arbitrary key/value pairs upon a
specified host. Doing so would not be difficult; it simply creates additional considerations when implementing playbooks related
to host assignment and unassignment.

#### Serial Console Support

There are multiple directions we could explore for serial console support:

* ESI already supports serial console access through socat (using an Ironic feature exposed through an ESI proxy). We could simply
generate the direct console URL and store that in the resource status.
* We could implement serial console support similar to the pod exec api (https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.23/#execaction-v1-core)

The first solution has the advantage of already being implemented within ESI; all we have to do is expose the URL generated by
ESI. However, it is unknown whether other bare metal services would have similar support for serial console access; for that
reason, we may want to investigate the possibility of a more generic solution that can be consistently used across multiple
bare metal management implementations.

#### Task Groupings

We can perform this implementation in smaller steps:

* HostPool and Host
  * Tenants can create/update/delete HostPools
  * No network attachments
  * Hosts are created when a HostPool is fulfilled
  * Tenants can view their Hosts
  * Tenants have power control on their Hosts
* Network Attachments
  * Tenants can specify network attachments when creating/updating HostPools
  * Requires network service
* Serial Console
  * Tenants can enable/disable serial console on a Host

### Risks and Mitigations

??

### Drawbacks

??

## Alternatives (Not Implemented)

One alternative would be to focus on an ESI replacement before developing the bare metal fulfillment
functionality. However, we anticipate that the MOC will continue to use ESI for now; for that reason,
it makes sense to perform this implementation with ESI in mind, and simply make it easy to replace
ESI if/when needed. Note that it is also possible that we will continue to use ESI if the issues
pushing us towards a replacement are fixed.

## Open Questions [optional]

* Do we have consensus that network configuration can only be performed on a HostPool, and not on an individual Host?
* Can we remove network attachment by MAC address?

## Test Plan

TBD

## Graduation Criteria

TBD

### Removing a deprecated feature

TBD

## Upgrade / Downgrade Strategy

TBD

## Version Skew Strategy

TBD

## Support Procedures

TBD

## Infrastructure Needed [optional]

None
