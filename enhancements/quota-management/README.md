---
title: quota-management
authors:
  - Lars Kellogg-Stedman <lars@redhat.com>
reviewers:
approvers:
api-approvers:
creation-date: 2025-09-11
last-updated: 2025-09-11
tracking-link:
see-also:
replaces:
superseded-by:
---

# Quota management

## Summary

We need to implement a quota mechanism for resources allocated by the Open Sovereign AI Cloud solution (oSAC). Our initial implementation will need to integrate with [ColdFront], the resource allocation management tool used by the MOC to manage resource quotas across multiple services.

[coldfront]: https://docs.ccr.buffalo.edu/en/latest/portals/coldfront/

## Motivation

Service providers establish upper limits on the resources tenants can consume for multiple reasons:

- They "sell" chunks of resources (storage, memory, etc) and want to limit tenants to only consume their allocated resources.

- They want to ensure that a tenant cannot accidentally or maliciously consume excessive resources and prevent other tenants from using the service.

### User Stories

- As a service provider, I want to create, modify, and delete resource quotas for a tenant organizations.
- As a service provider, I want to view quota limits and usage for tenant organizations.
- As a tenant, I want to be able to view the resource quota limits and utilization that apply to my organization.
- As a tenant, I want to know when an operation fails due to quota enforcement.

### Goals

TBD.

### Non-Goals

This work is specifically about creating an API and implementation logic for supporting quotas. It does not include any user interface components.

## Proposal

We propose to implement a generic approval workflow in the fulfillment API and to introduce a loosely coupled quota service that will serve as the integration point with ColdFront. When resources are requested via the fulfillment API, they will initially be in an "unapproved" state. The quota service will watch for resources in this state, and for each resource will query the fulfillment service for resource usage information and either approve the resource request or annotate with information about why it was not approved.

The quota service will expose an API that can be used to create, modify, list, and get details for quotas. Write operations (create, modify) will require administrative privileges. Read operations (list, get) will permit a tenant to see quotas associated with their organization and will permit an administrator to see values for all tenants.

Quota limits will be limited as sets of arbitrary key/value pairs, in order to support quotas for new resource types int he future without requiring code changes to the quota service.

There are several advantages to this model:

- The generic approval workflow can be used for things other than quota management. For example, a service provider may require a manual approval workflow for certain types of requests.

- The quota service as proposed is generic enough that it may be sufficient in a number of situations, but at the same time it is easy to replace for service providers that need alternative logic.

### Workflow Description

An example workflow may look something like this:

1. A **tenant** requests a new cluster using the fulfillment API.

2. The cluster request is recorded in the fulfillment service but has not yet been approved, so the fulfillment service takes no further action at this time.

3. The quota service sees the pending request and looks up the tenants resource quotas on "number of clusters" and "number of bare metal hosts".

4. If the new cluster would not violate these quotas, the request is approved. At this point, the fulfillment service will past the request on to the operator and the cluster will be created.

### API Extensions

- This will require all resources that can be requested using the fulfillment API to support a new "approved" metadata attribute.
- The fulfillment service should record but not otherwise act on unapproved requests.
- Changing the "approved" attribute is a privileged operation and should only be available to fulfillment service administrators
- The fulfillment service must provide an API for requesting information about current resource usage

### Implementation details/notes/constraints

For deployment at the MOC, we expect [ColdFront](https://coldfront.readthedocs.io/en/stable/) to be the source of truth for quota information. ColdFront operates using a push model -- administrators create allocations in ColdFront, and then ColdFront uses service-specific plugins to implement resource quotas in external services. For example, the OpenShift plugin implements quotas by creating namespaces and then populating them with ResourceQuota objects, while for OpenStack ColdFront will create quotas using the quota APIs provided by the various OpenStack services.

* See [What is NERC’s ColdFront?](https://nerc-project.github.io/nerc-docs/get-started/allocation/coldfront/) for more information about ColdFront and how it is currently used to manage resource allocations.
* See [coldfront-plugin-cloud](https://github.com/nerc-project/coldfront-plugin-cloud) for an example of a MOC-developed ColdFront plugin that pushes information to OpenStack and OpenShift.

### Risks and Mitigations

N/A

### Drawbacks

N/A

## Alternatives (Not Implemented)

We could implement quota support directly in the fulfillment service, but we were concerned that this solution would bind the fulfillment service too tightly to the MOC requirements, whereas we want a solution that can be deployed by arbitrary service providers who may have different needs both around quota management and around approval workflows.

## Open Questions [optional]

- Need discussion with MOC/commercial on the concept of "unit" aka service unit aka SU (@hpdempsey)

- Like any API field that seems like a natural boolean, I suggest we treat the "approved" field as a string to allow for more states. We may only be interested in states "pending" and "approved" to start, but others could be useful later like "denied".  (@mhrivnak)

- We should probably have a "reason" field where the external service can explain its decision to the user. "Would exceed your quota by 3 nodes", "not enough nodes available", "cluster must be upgraded before adding nodes of type X", etc. (@mhrivnak)

- Just because we've overloaded the term "baremetal", it may be worth clarifying that when we talk about a quota on the number of baremetal nodes that this applies to bare metal nodes regardless of whether they are in a cluster or how they are being used. (@mhrivnak)

- I would add that the quota service being implemented can and should be specific to the MOC. It's especially worth clarifying that we are not trying to create a generic all-usecase quota service. (@mhrivnak)

## Test Plan

TBD

## Graduation Criteria

TBD

## Support Procedures

TBD

## Infrastructure Needed [optional]

N/A
