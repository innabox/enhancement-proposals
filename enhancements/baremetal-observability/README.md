---
title: bare-metal-observability
authors:
  - Austin Jamias
creation-date: 2025-09-24
last-updated: 2025-09-24
tracking-link: # link to the tracking ticket (for example: Github issue) that corresponds to this enhancement
  - N/A
see-also:
  - N/A
replaces:
  - N/A
superseded-by:
  - N/A
---

# Bare Metal Observability

## Summary

We want a way to gather bare metal metrics from tenant clusters and have them 
available at some configurable endpoint for the cloud provider to manage. This 
feature will be easily toggleable per tenant cluster.

## Motivation

Gathering baremetal metrics is an important aspect of observability in cloud 
systems. It allows the cloud provider to make informed decisions on cost 
estimates and abnormal hardware behavior.

If the cloud provider decides to expose baremetal metrics to tenants, 
it would allow them to also make informed decisions on cost estimates 
and essential hardware metrics if they should use it for their projects.

### User Stories

* As a provider, I want to easily deploy and undeploy bare metal 
  observability using an automation application like Ansible 
  or an operator.
* As a provider, I want to be able to access a metric endpoint so I 
  can connect it to Prometheus compatible frontend applications and
  stacks.
* As a provider, I want my metrics to come with labels about the
  originating clusters and nodes so I can build my own RBAC system 
  to the metrics for the tenants.
* As a provider, I want to easily include another metric exporter if 
  I decide I want to use something other than Prometheus's IPMI and 
  SNMP exporters.

### Goals

This will be a success if this can be deployed as an optional feature 
in the OSAC installation process. The implementation will rely on ESI 
and OpenStack for retrieving information on where to get baremetal 
metrics. This will be using Prometheus compatible applications 
because the Prometheus is built-in to OpenShift.

This will be a success if there is minimal to no communication needed 
between the tenant and the provider regarding additional observability 
management and configuration.

### Non-Goals

* We will not be looking into how to use metrics for billing purposes.
* We will not be looking into proxies/applications that would usually 
  go on top of the metric API endpoint.
* We will not be looking into collecting from in-OS exporters in bare 
  metal clusters. This may call for a later enhancement.
* We will not be looking into fine-grain access to metrics, but we 
  can implement metric labeling with cluster and node labels now to 
  help with implementing fine-grain access later. This will call for 
  a later enhancement.

## Proposal

The proposed implementation makes use of the [multi-target exporter pattern](https://prometheus.io/docs/guides/multi-target-exporter/#the-multi-target-exporter-pattern),
notably the [IPMI-exporter](https://github.com/prometheus-community/ipmi_exporter) 
and the [SNMP-exporter](https://github.com/prometheus/snmp_exporter).
Multi-target exporters have properties perfect for our goals:
* the exporter does not have to run on the machine the metrics are taken from
* the exporter will get the target’s metrics via a network protocol
* the exporter can query multiple targets

The following items describe the key points of the proposal:

**Devices will be scraped remotely**

The first proposed change comes from the idea that the provider 
should not expect any tenant to run any metric exporter. Therefore, 
the proposed implementation has the exporters to be ran on the hub
cluster and perform remote scrapes.

**Discoverable**

The nodes that host the exporters must be on the same network as the 
devices that the exporters perform the scrape on. The way this might 
happen might be through the fulfillment service. The nodes given to 
the tenants should have either minimal or no direct read/write access 
to the devices.

**Distinguishable**

The scraped metrics will need to be labeled with a cluster and node
identifier so that the provider can identify which metric belongs to 
which cluster, node, and tenant, and the tenant can identify which node 
each of their metric belongs to.


### Workflow Description

**Deploying Baremetal Observability**
1. The cloud provider runs an ansible playbook with an argument that 
   indicates the want to deploy.
2. The resources needed for the baremetal metric collection system 
   gets deployed

**Removing Baremetal Observability**
1. The cloud provider runs an ansible playbook with an argument that 
   indicates the want to remove.
2. The resources needed for the baremetal metric collection system 
   gets removed

### API Extensions

N/A

### Implementation Details/Notes/Constraints

For simplicity, this section will only talk about Prometheus's IPMI 
exporter, but we also plan on deploying Prometheus's SNMP exporter,
and more exporters can easily be added aswell.

**Exporter constraints**:

Operational metrics are metrics that are scraped from exporters 
running on the same host. Operational metrics from baremetal clusters 
cannot be trusted because the tenant can theoretically supply fake
metrics to the cloud provider.

**AAP**: 

The installation process will be described by a bunch of tasks in an 
Ansible playbook. The playbook will need to be repeated any time a 
new node gets added to the cloud provider's node pool. The task of 
setting up an IPMI exporter to scrape metrics from all ESI nodes 
looks like this:

1. Connect the hub nodes to the BMC network
2. Get all IPMI IPs and ports to scrape from OpenStack
3. Create an IPMI exporter deployment on the hub cluster configured 
   with the username and password required to access the BMCs of each 
   node
4. Create an IPMI exporter service
5. Create an IPMI exporter ServiceMonitor connected to the IPMI 
   exporter service and configured to scrape the IPs and ports, and 
   discoverable by openshift-monitoring's Prometheus pods

**Access to Metrics**:

Access to metrics can be done through Prometheus or the Thanos 
Querier (also the Observatorium API). Providers are able to 
deploy their own Prometheus API compatible applications if they 
choose to do so.

### Risks and Mitigations

Metrics will have to be proxied by some sort of fine-grain 
access system to comply with privacy laws such as GDPR.

### Drawbacks

N/A

## Alternatives (Not Implemented)

An alternative for tenant OpenShift clusters is to have exporters 
exist as a daemonset on tenant nodes and the metrics will be seen by 
openshift-monitoring and then open-cluster-management-observability. 
However, this means that the tenant could potentially supply any kind 
of metric they want, and this would require two different 
implementations for tenant OpenShift clusters and baremetal clusters.

There are alternative metric collection projects out there, but 
this will use Prometheus because it is part of OpenShift, and there 
are a vast amount of supported Prometheus compatible exporters and 
applications.

## Open Questions [optional]

N/A

## Test Plan

N/A

## Graduation Criteria

N/A

### Removing a deprecated feature

N/A

## Upgrade / Downgrade Strategy

N/A

## Version Skew Strategy

N/A

## Support Procedures

N/A

## Infrastructure Needed [optional]

N/A

