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

This document proposes a service enabling tenants to easily create, manage, and operate virtual machines (VMs) within a self-service environment. The service will provide user-friendly APIs for provisioning, customizing, and  controlling the lifecycle of VMs attaching storage, and accessing specialized hardware (GPUs).

This design is focused at delivering VM to tenants with an simple networking model, advanced features related to Virtual Data Center-as-a-Service (VDCaaS) will be part of another design.

## Motivation

Virtualization-as-a-Service (VMaaS) addresses the need for flexible, on-demand compute resources within a multi-tenant environments. This is a need identified in the scope of O-SAC, and will benefit to the MOC.

### User Stories

- As a provider, I want to define VM templates that my tenants will be able to use
- As a tenant, I want to list a pre-defined VM templates
- As a tenant, I want to create a VM based on a pre-defined template
- As a tenant, I want a VM that has access to specialized hardware (e.g.: GPU)
- As a tenant, I want to manage the lifecycle of my VM (start/stop/terminate)
- As a tenant, I want to connect on my VM through serial console
- As a tenant, I want to be able to expose network services to an external network

### Goals

- Provide a self-service API for tenants to create, manage, and operate virtual machines (VMs) with minimal operational overhead
- Support a catalog of pre-defined VM templates
- Offer access to specialized hardware (e.g., GPUs) for tenants that require it trhough the catalog of tamplates
- Use ESI to assign floating IPs to created VM so they can be accessed
- Achieve high availability by supporting live migration of VMs

### Non-Goals

The following are explicitly out of scope for this proposal:

- Implementing advanced VM orchestration features such as auto-scaling, and region placement
- Automatically add physical resources to cope with the demand of VMs
- Offering built-in backup, restore, or disaster recovery solutions for VMs or attached storage
- Delivering a marketplace for third-party VM images or applications, we expect tenant to rely on en external image registry to distribute they OS base images

## Proposal

The implementation of virtual machine fulfillment relies on two concepts:

* VirtualMachine: allows the management of a virtual machine by a tenant
* VirtualMachineTemplate: created by the provider, a template represent a pre-configuration for virtual machines that is made available to tenants. This pre-configuration is exposed to tenant though a template ID, and a set of parameters, parameters may be required or optional.

At a high level, tenants will request a VirtualMachine by specifying:

* the ID of the template they want to use
* input parameters for the selected template
* the state of the virtual machine (started, stopped)

We expect virtual machine fulfillment to follow the same workflow used for other fulfillment workflows; as such, we expect to update the
following existing O-SAC components:

* Fulfillment Service: Define the API for VirtualMachine and VirtualMachineTemplate
* Fulfillment CLI: Give the tenant access to the API
* O-SAC Operator: Manage and reconcile the Custom Resources for VirtualMachine
* O-SAC AAP: Use Ansible playbooks to perform the requested reconciliation operations of VirtualMachine by calling KubeVirt and ESI APIs (to assign floating IPs).

### Workflow Description

#### Virtual machine creation and update

1. The tenant uses the Fulfillment CLI to request the creation of a new VirtualMachine, specifying:
    - The desired VirtualMachineTemplate ID
    - Any required or optional parameters for the template (e.g., CPU, memory, disk size, network configuration)
    - The initial state of the VM (started or stopped)
2. The Fulfillment Service receives the request and validates:
    - The existence and availability of the specified template
    - The correctness and completeness of the provided parameters
3. The Fulfillment Service creates a new VirtualMachine custom resource (CR) in the appropriate namespace.
4. The O-SAC Operator detects the new VirtualMachine CR and triggers the reconciliation process.
5. The Operator, via AAP (Ansible Automation Platform), performs the following automation steps:
    - Creates a dedicated namespace for the VM (if not already present)
    - Provisions the required network resources (e.g., UDN L2 network)
    - Creates the KubeVirt VirtualMachine resource according to the template and parameters
    - Assigns a floating IP to the VM using ESI APIs
    - ...other operations depending on the selected virtual machine template
6. The Operator monitors the status of the VM and updates the VirtualMachine CR status accordingly.
7. The tenant can query the status of the VM via the Fulfillment CLI or API, and access the VM using the assigned floating IP.

The update process is the same as the creation workflow as it will be designed to be idempotent.

#### Virtual machine deletion

When a tenant requests the deletion of a VirtualMachine, the following workflow is executed:

1. The tenant uses the Fulfillment CLI or API to request deletion of a VirtualMachine by specifying its identifier.
2. The Fulfillment Service receives the deletion request and validates:
    - The existence of the specified VirtualMachine resource.
    - That the tenant has permission to delete the resource.
3. The Fulfillment Service deletes the VirtualMachine custom resource (CR) from the appropriate namespace.
4. The O-SAC Operator detects the deletion of the VirtualMachine CR and triggers the cleanup process.
5. The Operator, via AAP (Ansible Automation Platform), performs the following automation steps:
    - Deletes the KubeVirt VirtualMachine resource.
    - Releases and deallocates any associated network resources (e.g., UDN L2 network, floating IPs via ESI APIs).
    - ...other cleanup operations depending on the selected virtual machine template
    - Deletes the dedicated namespace
6. The Operator updates the status of the deletion operation and ensures all resources are properly cleaned up.
7. The tenant can confirm the deletion via the Fulfillment CLI or API.

This workflow ensures that all resources associated with the VirtualMachine are properly deprovisioned and that no orphaned resources remain.

#### Virtual machine template management

Virtual machine templates are managed by the provider using a GitOps workflow. The source of truth for templates resides in a version-controlled repository. A periodic job running in Ansible Automation Platform (AAP) is responsible for publishing the current set of templates to the Fulfillment Service. This ensures that any updates, additions, or removals of templates in the repository are automatically reflected in the Fulfillment Service, providing tenants with an up-to-date catalog of available VM templates.

### API Extensions

#### VirtualMachine

A tenant requests a virtual machine by requesting a VirtualMachine to the Fulfillment Service. Here is an example of request that creates a VM, using a template that let tenants to customize the amount of CPUs, memory and boot disk size:

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

Once the virtual machine is created, tenants are able to review its current state:

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
        "type": "VIRTUAL_MACHINE_CONDITION_TYPE_PROGRESSING"
      },
      {
        "last_transition_time": "2025-09-17T08:52:12.652582382Z",
        "message": "",
        "status": "CONDITION_STATUS_TRUE",
        "type": "VIRTUAL_MACHINE_CONDITION_TYPE_READY"
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
    "state": "VIRTUAL_MACHINE_STATE_READY",
    "internalIP": "10.0.0.1",
    "externalIP": "193.1.2.3"
  }
}
```

`internalIP` is the IP assigned directly to the virtual machine, and `externalIP` is the floating IP pointing to the virtual machine.

#### VirtualMachineTemplate

Virtual machine template are designed as Ansible roles, these roles must follow the follwing definition:



There will be a peridioc job witch will publish the Ansible roles as virtual machine templates to the Fulfillment Service, so tenants will be able to reference them to create their virtual machines:

```json
{
  "object": {
    "id": "simple_vm",
    "title": "Simple VM Template",
    "description": "This template provisions a virtual machine. CPU, memory, and boot volume size is configurable",
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

Virtual machines will be created on the HUB cluster that was selected by Fulfillment Service, it was discussed to create a dedicated cluster to handle VM workloads using Cluster-as-a-Service API, but since they are HostedCluster it won't increase the reliability of the solution, as their reliability are tied to the same HUB cluster.

### Risks and Mitigations

TBD

### Drawbacks

TBD

## Alternatives (Not Implemented)

TBD

## Open Questions [optional]

- I think that without the concept of regions (mapped on HUB cluster?) in the Fulfillment Service, we are stuck with storage (as it is local to a HUB), and with private networking (for example, I want my web server with a floating IP to communicate internally with my DB).

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
