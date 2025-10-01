---
title: Virtualization as a service
authors:
  - Adrien Gentil
creation-date: 2025-09-15
last-updated: 2025-09-15
tracking-link:
  - TBD
see-also:
replaces:
superseded-by:
---

# Virtualization-as-a-Service


## Summary

This document proposes a service enabling tenants to easily create, manage, and
operate virtual machines (VMs) within a self-service environment. The service
will provide user-friendly APIs for provisioning, customizing, and  controlling
the lifecycle of VMs attaching storage, and accessing specialized hardware
(GPUs).

This design aims to provide tenants with virtual machines using a
straightforward networking model. More advanced capabilities, such as those
related to Virtual Data Center-as-a-Service (VDCaaS), will be addressed in a
separate proposal.

## Motivation

Virtualization-as-a-Service (VMaaS) addresses the need for flexible, on-demand
compute resources within a multi-tenant environments. This is a need identified
in the scope of O-SAC, and will benefit to the MOC.

### User Stories

- As a provider, I want to define VM templates that my tenants will be able to
  use
- As a tenant, I want to list a pre-defined VM templates
- As a tenant, I want to create a VM based on a pre-defined template
- As a tenant, I want a VM that has access to specialized hardware (e.g.: GPU)
- As a tenant, I want to manage the lifecycle of my VM (start/stop/terminate)
- As a tenant, I want to connect on my VM through serial console
- As a tenant, I want to be able to expose network services to an external
  network

### Goals

- Provide a self-service API for tenants to create, manage, and operate virtual
  machines (VMs) with minimal operational overhead
- Support a catalog of pre-defined VM templates
- Offer access to specialized hardware (e.g., GPUs) for tenants that require it
  through the catalog of templates
- Use ESI to assign floating IPs to created VM so they can be accessed
- Achieve high availability by supporting live migration of VMs

### Non-Goals

The following are explicitly out of scope for this proposal:

- Implementing advanced VM orchestration features such as auto-scaling, and
  region placement
- Implementing Virtual Data Center-as-a-Service (VDCaaS) features such as
  virtual private networks
- Automatically add physical resources to cope with the demand of VMs
- Offering built-in backup, restore, or disaster recovery solutions for VMs or
  attached storage
- Delivering a marketplace for third-party VM images or applications, we expect
  tenant to rely on en external image registry to distribute they OS base images

## Proposal

The process of fulfilling virtual machine requests is based on two primary
concepts:

* **VirtualMachine**: Represents an individual virtual machine that a tenant can
  create and manage. Tenants can only see the virtual machines they created.
* **VirtualMachineTemplate**: Defined by the provider, this is a pre-configured
  blueprint for virtual machines. Each template is identified by a unique
  template ID and includes a set of parameters (some required, some optional)
  that tenants can specify when creating a VM. Templates are available to all
  tenants to use, they cannot edit them.

To request a new VirtualMachine, tenants must provide:

* The ID of the desired VirtualMachineTemplate
* Any required or optional parameters for that template
* The desired initial state of the VM (e.g., started or stopped)

The virtual machine fulfillment process will align with existing O-SAC
fulfillment workflows. To support this, the following O-SAC components will be
enhanced or updated:

* **Fulfillment Service**: Defines and exposes the APIs for managing
  VirtualMachine and VirtualMachineTemplate resources.
* **Fulfillment CLI**: Provides tenants with command-line access to the
  Fulfillment Service APIs.
* **O-SAC Operator**: Monitors and reconciles VirtualMachine custom resources
  within the system.
* **O-SAC AAP (Ansible Automation Platform)**: Executes automation tasks (via
  Ansible playbooks) to reconcile VirtualMachine resources, including
  interactions with KubeVirt for VM lifecycle management and ESI APIs for
  assigning floating IPs.

Under the hood, the virtual machines will be managed using OpenShift
Virtualization. Each VirtualMachine will be created in its own dedicated
namespace on the Hub cluster. The VM will be connected to a dedicated UDN L2
network, which provides network isolation, mainly for 2 reasons:
- security: this means the VM cannot communicate with other workloads on the Hub
  cluster using its internal IP address.
- Live migration: UDN L2 enables the virtual machine to be migrated live from
  OpenShift nodes to others. Migration can happen when a node is degraded or in
  maintenance.

To enable external connectivity, a Kubernetes Service of type LoadBalancer will
be created in front of the VM. A floating (external) IP address will be assigned
to this LoadBalancer service, allowing the VM to be accessed from outside the
cluster.

### Workflow Description

#### Virtual machine creation and update

1. The tenant initiates the creation of a new VirtualMachine using the
   Fulfillment CLI. The tenant must provide:
    - The ID of the desired VirtualMachineTemplate
    - All required and any optional parameters for the template (such as CPU,
      memory, disk size, network configuration)
    - The desired initial state of the VM (e.g., started or stopped)

2. The Fulfillment Service receives this request and performs validation to
   ensure:
    - The specified template exists and is available
    - All required parameters are provided and valid

3. Upon successful validation, the Fulfillment Service creates a new
   VirtualMachine custom resource (CR) in the appropriate Hub and namespace.

4. The O-SAC Operator detects the new VirtualMachine CR and begins the
   reconciliation process.

5. The Operator, using Ansible Automation Platform (AAP), automates the
   following steps:
    - Creates a dedicated namespace for the VM if one does not already exist
    - Provisions necessary network resources, including:
        - A UDN L2 network to provide network isolation
        - A load balancer service with the VM as its backend
        - Assignment of a floating IP to the load balancer service for external
          access
    - Creates the KubeVirt VirtualMachine resource using the specified template
      and parameters
    - Performs any additional operations required by the selected template

6. The Operator continuously monitors the VM’s status and updates the
   VirtualMachine CR status to reflect the current state.

7. The tenant can check the VM’s status at any time using the Fulfillment CLI or
   API, and can access the VM via the assigned floating IP.

The update process is the same as the creation workflow as it will be designed
to be idempotent.

#### Virtual machine deletion

When a tenant requests the deletion of a VirtualMachine, the following workflow
is executed:

1. The tenant initiates the deletion of a VirtualMachine using the Fulfillment
   CLI or API by specifying its identifier.

2. The Fulfillment Service receives the deletion request and performs validation
   to ensure:
    - The specified VirtualMachine resource exists and is available.
    - The tenant has permission to delete the resource.

3. Upon successful validation, the Fulfillment Service deletes the
   VirtualMachine custom resource (CR) from the appropriate namespace.

4. The O-SAC Operator detects the deletion of the VirtualMachine CR and begins
   the cleanup process.

5. The Operator, using Ansible Automation Platform (AAP), automates the
   following steps:
    - Deletes the KubeVirt VirtualMachine resource.
    - Releases and deallocate any associated network resources, including:
        - UDN L2 network
        - Load balancer service
        - Floating IPs via ESI APIs
    - Performs any additional cleanup operations required by the selected
      virtual machine template.
    - Deletes the dedicated namespace if it is no longer needed.

6. The Operator updates the status of the deletion operation and ensures all
   resources are properly cleaned up.

7. The tenant can confirm the deletion and cleanup via the Fulfillment CLI or
   API.

This workflow ensures that all resources associated with the VirtualMachine are
properly deprovisioned and that no orphaned resources remain.

#### Virtual machine template management

Virtual machine templates are centrally managed by the provider using a GitOps
approach. All templates are stored in a version-controlled repository, which
acts as the single source of truth. At regular intervals, an automated job in
Ansible Automation Platform (AAP) synchronizes the latest templates from this
repository to the Fulfillment Service. As a result, any changes to the
templates—such as updates, additions, or deletions—are automatically and
consistently reflected in the Fulfillment Service. This process ensures that
tenants always have access to the most current catalog of available VM
templates.

### API Extensions

#### VirtualMachine

A tenant requests a virtual machine by requesting a VirtualMachine to the
Fulfillment Service. Here is an example of request that creates a VM, using a
template that let tenants to customize the amount of CPUs, memory and boot disk
size:

```json
{
  "object": {
    "id": "myvm",
    "spec": {
      "state": "started",
      "template": "ocp_virt_vm",
      "template_parameters": {
        "vm_cpu_cores": {
          "value": 4
        },
        "vm_disk_size": {
          "value": "30Gi"
        },
        "vm_memory": {
          "value": "4Gi"
        }
      }
    }
  }
}
```

After creating a virtual machine, tenants can check its current status and
details as follows:

```json
{
  "@type": "type.googleapis.com/fulfillment.v1.VirtualMachine",
  "id": "fecb9b9e-07ac-4d56-8b48-9d50aab71677",
  "metadata": {
    "creation_timestamp": "2025-09-17T08:14:17.569076Z",
    "creators": [
      "guest"
    ]
  },
  "spec": {
    "state": "started",
    "template": "ocp_virt_vm",
    "template_parameters": {
      "vm_cpu_cores": {
        "value": 4
      },
      "vm_disk_size": {
        "value": "30Gi"
      },
      "vm_memory": {
        "value": "4Gi"
      }
    }
  },
  "status": {
    "conditions": [
      {
        "last_transition_time": "2025-09-19T17:32:24.054439350Z",
        "message": "",
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_CONDITION_TYPE_PROVISIONNING"
      },
      {
        "last_transition_time": "2025-09-17T08:52:12.652582382Z",
        "message": "",
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_STATE_STARTING"
      },
      {
        "last_transition_time": "2025-09-17T08:52:12.652582382Z",
        "message": "",
        "status": "CONDITION_STATUS_TRUE",
        "type": "VIRTUAL_MACHINE_STATE_RUNNING"
      },
      {
        "last_transition_time": "2025-09-17T08:52:12.652582382Z",
        "message": "",
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_STATE_STOPPING"
      },
      {
        "last_transition_time": "2025-09-17T08:52:12.652582382Z",
        "message": "",
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_STATE_STOPPED"
      },
      {
        "last_transition_time": "2025-09-17T08:52:12.652582382Z",
        "message": "",
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_STATE_TERMINATING"
      },
      {
        "last_transition_time": "2025-09-17T08:52:12.652582382Z",
        "message": "",
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_STATE_PAUSED"
      },
      {
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_CONDITION_TYPE_FAILED"
      },
      {
        "status": "CONDITION_STATUS_FALSE",
        "type": "VIRTUAL_MACHINE_CONDITION_TYPE_DEGRADED"
      }
    ],
    "state": "VIRTUAL_MACHINE_STATE_RUNNING",
    "internalIP": "10.0.0.1",
    "externalIP": "193.1.2.3"
  }
}
```

The status section provides two types of IP addresses for the virtual machine:

- `internalIP`: The private IP address assigned to the VM on the internal
  network.

- `externalIP`: The public (floating) IP address assigned to the VM. This
  address allows the VM to be accessed from outside the internal network, such
  as from the internet.

The Virtual Machine can be in one of the following states, as reflected in the
status section above. These states are mapped from the underlying KubeVirt
VirtualMachine status conditions:

- **Provisioning** (`VIRTUAL_MACHINE_STATE_PROVISIONING`): The VM is being
  created.
- **Starting** (`VIRTUAL_MACHINE_STATE_STARTING`): The Pod for the Virtual
  Machine Instance (VMI) is being scheduled and started.
- **Running** (`VIRTUAL_MACHINE_STATE_RUNNING`): The VM is actively running
  inside its Pod.
- **Stopping** (`VIRTUAL_MACHINE_STATE_STOPPING`): The VM is in the process of
  shutting down.
- **Stopped** (`VIRTUAL_MACHINE_STATE_STOPPED`): The VM is not running. It
  exists as a VirtualMachine object, but there is no active VMI or Pod.
- **Terminating** (`VIRTUAL_MACHINE_STATE_TERMINATING`): The VM object is in the
  process of being deleted.
- **Paused** (`VIRTUAL_MACHINE_STATE_PAUSED`): The VM is in a suspended state.
  Its process is frozen, but its memory and resources are still allocated.

These states are reported in the `type` field of the VM's `conditions` array in
the status section.


#### VirtualMachineTemplate

Virtual machine templates are implemented as Ansible roles. Each role must
include the following files:

* `vm_template_role/meta/argument_specs.yaml`: Defines the [Ansible argument
  specification](https://docs.ansible.com/ansible/latest/dev_guide/developing_program_flow_modules.html#argument-spec).
  This file is required.
* `vm_template_role/meta/cloudkit.yaml`: Contains metadata for the template,
  including the title and description. This file is required.

Example of `cloudkit.yaml`:

```yaml
title: VM Template
description: >
  This template provisions a virtual machine.
```

A periodic job will publish the Ansible roles as virtual machine templates to
the Fulfillment Service, using the required files described above. The following
is the API format used for this publication:

```json
{
  "object": {
    "id": "vm_template_role",
    "title": "VM Template",
    "description": "This template provisions a virtual machine.",
    "parameters": [
      {
        "name": "vm_cpu_cores",
        "default": {
          "value": 2
        }
      },
      {
        "name": "vm_memory",
        "default": {
          "value": "2Gi"
        }
      },
      {
        "name": "vm_disk_size",
        "default": {
          "value": "20Gi"
        }
      }
    ]
  }
}
```

### Implementation Details/Notes/Constraints


#### Virtual machines on HUB cluster

Virtual machines will be created on the HUB cluster chosen by the Fulfillment
Service. Although there was discussion about creating a dedicated cluster for VM
workloads using the Cluster-as-a-Service API, this approach would not improve
reliability. This is because these dedicated clusters would still be implemented
as HostedClusters, whose reliability ultimately depends on the same underlying
HUB cluster.

#### Networking

Because O-SAC does not yet provide a VDCaaS (Virtual Data Center as a Service)
layer, and the Fulfillment Service cannot guarantee that two virtual machines
will be provisioned on the same HUB cluster, each virtual machine must be
assigned a floating IP. This ensures that every VM is accessible regardless of
where it is deployed.


#### Load balancer service type and MetalLB

Even though a Kubernetes Service of type LoadBalancer requires explicit port
mappings to be defined, MetalLB will actually expose all ports on the assigned
external IP address. This means that, in practice, any port on the VM can be
accessed via the floating IP, regardless of the ports specified in the Service
manifest.

#### UDN and network isolation

Virtual machines that are provisioned on different UDN networks will still be
able to communicate with each other by using their assigned floating IPs. Since
each VM is given a floating IP for external access, network traffic between VMs
on separate UDN networks can be routed through these public endpoints, ensuring
connectivity even in the absence of a shared internal network.

### Risks and Mitigations

TBD

### Drawbacks

The initial design of VMaaS has significant limitations due to the absence of
regions and zones in our API:

- Tenants cannot create complex VM architectures that use both public and
  private networks. Features such as security groups and network ACLs are also
  missing.
- Tenants are unable to provision permanent block storage that can be attached
  to and detached from different VMs as needed.

We expect to revisit and improve this design once the VDCaaS (Virtual Data
Center as a Service) functionality is available.

Another limitation is that currently, virtual machines can only be managed on
the local (HUB) cluster. In the future, there may be a need to manage virtual
machines on remote or dedicated clusters, especially if service providers deploy
clusters specifically for VM workloads. This would allow for enhanced security
and the use of specialized hardware. The development of such feature will be
part of another enhancement.

## Alternatives (Not Implemented)

TBD

## Open Questions [optional]


## Test Plan

TBD

## Graduation Criteria

TBD

### Removing a deprecated feature

N/A

## Upgrade / Downgrade Strategy

N/A

## Version Skew Strategy

N/A

## Support Procedures

TBD

## Infrastructure Needed [optional]

N/A
