---
title: bare-metal-observability
authors:
  - Austin Jamias
creation-date: 2025-09-24
last-updated: 2025-09-30
tracking-link: # link to the tracking ticket (for example: Github issue) that corresponds to this enhancement
  - N/A
see-also:
  - https://github.com/ajamias/baremetal-observability-aap
replaces:
  - N/A
superseded-by:
  - N/A
---

# Bare Metal Observability

## Summary

We want a way to gather bare metal metrics from tenant clusters and have them
available at some configurable endpoint for the cloud provider to manage. This
feature will provide an interface compatible to many inventory services.

## Motivation

Gathering baremetal metrics is an important aspect of observability in cloud
systems. It allows the cloud provider to make informed decisions on cost
estimates and abnormal hardware behavior.

If the cloud provider decides to expose baremetal metrics to tenants,
it would allow them to also make informed decisions on cost estimates
and essential hardware metrics if they should use it for their projects.

### User Stories

* As a provider, I want to easily deploy and undeploy bare metal
  observability using Ansible playbooks.
* As a provider, I want to be able to access a metric endpoint so I
  can connect it to Prometheus compatible frontend applications and
  stacks.
* As a provider, I want my metrics to come with labels about the
  originating clusters and nodes so I can build my own RBAC system
  to the metrics for the tenants.
* As a provider, I want to easily include Ansible roles for other
  metric exporters if I decide I want to use something other than
  Prometheus's IPMI and SNMP exporters.
* As a provider, I want to easily swap different Ansible roles that
  deploy using different inventory services.

### Goals

This will be a success if this can be deployed as an optional feature
in the OSAC installation process. The implementation will rely on
Ansible roles providing an interface that can work with any inventory
service for retrieving information on where to get baremetal metrics.
The implementation will also rely on Prometheus compatible
applications because the Prometheus is already built in to OpenShift
(openshift-monitoring) and ACM observability
(open-cluster-management-observability).

### Non-Goals

* We will not be looking into how to use metrics for billing purposes.
* We will not be looking into proxies/applications that would usually
  go on top of the metric API endpoint.
* We will not be looking into collecting from in-OS exporters in bare
  metal clusters. This may call for a later enhancement.
* We will not be looking into fine-grain access to metrics, but we
  can implement metric labeling node labels now to help with
  implementing fine-grain access later. This will call for a later
  enhancement.

## Proposal

The proposed implementation makes use of the [multi-target exporter pattern](https://prometheus.io/docs/guides/multi-target-exporter/#the-multi-target-exporter-pattern),
notably the [IPMI-exporter](https://github.com/prometheus-community/ipmi_exporter)
and the [SNMP-exporter](https://github.com/prometheus/snmp_exporter)
Multi-target exporters have properties perfect for our goals:
* the exporter does not have to run on the machine the metrics are taken from
* the exporter will get the target’s metrics via a network protocol
* the exporter can query multiple targets

The following items describe the key points of the proposal:

**Devices will be scraped remotely**

The first proposed change comes from the idea that the provider
should not expect any tenant to run any metric exporter. Therefore,
the proposed implementation has the exporters to be ran on the ACM
hub cluster and perform remote scrapes.

**Discoverable**

The nodes that host the exporters (the hub cluster) must be on the
same network as the BMCs (baseboard management controller). The nodes
given to the tenants should have no access to the BMCs.

**Distinguishable**

Initially, the scraped metrics will need to be labeled with a
node identifier so that the provider can then identify which cluster
and tenant it belongs to. Once the enhancement proposal for the
baremetal fulfillment gets implemented, the implementation can switch
from using a node identifier to a cloudkit.Host and cloudkit.HostPool
resource identifier.

### Workflow Description

**Deploying Baremetal Observability**
1. The cloud provider navigates to either the Ansible web interface,
   or prepares a POST request to send to the Ansible Automation
   Platform API.
2. The cloud provider submits a request to run the baremetal-observability
   playbook with extra-vars that instruct the playbook to create the system,
   which inventory service they are using and which exporters to deploy.
3. The resources needed for the baremetal metric collection system
   gets deployed.

**Removing Baremetal Observability**
1. The cloud provider navigates to either the Ansible web interface,
   or prepares a POST request to send to the Ansible Automation
   Platform API.
2. The cloud provider submits a request to run the
   baremetal-observability playbook with extra-vars that indicate the
   signal to destroy the system.
3. The Ansible job removes everything deployed by the
   baremetal-observability template.

### API Extensions

N/A

### Implementation Details/Notes/Constraints

The directory structure focuses on keeping the inventory service and
types of exporters modular so that the cloud provider can pick and
choose for their needs. An example might look like this:

```bash
└── roles
    ├── baremetal_observability
    │   ├── defaults
    │   │   └── main.yaml
    │   ├── meta
    │   │   └── argument_specs.yaml
    │   └── tasks
    │       ├── create_baremetal_observability.yaml
    │       ├── destroy_baremetal_observability.yaml
    │       └── main.yaml
    │
    │   # inventory services
    ├── openstack
    │   ├── defaults
    │   │   └── main.yaml
    │   ├── meta
    │   │   └── argument_specs.yaml
    │   └── tasks
    │       └── main.yaml
    │
    │   # metric exporters
    ├── ipmi-exporter
    │   └── tasks
    │       └── main.yaml
    ├── snmp-exporter
    │   └── tasks
    │       └── main.yaml
```

**Exporter constraints**:

Operational metrics are metrics that are scraped from exporters
running on the same host. Operational metrics from baremetal clusters
cannot be trusted because the tenant can theoretically supply fake
metrics to the cloud provider. For now, we assume that all exporters
scrape from the BMC.

**AAP**:

The installation process will be described by a bunch of tasks in an
Ansible playbook. The playbook will need to be repeated any time a
new node gets added to the cloud provider's node pool. To keep this
playbook flexible, the user will need to provide the following
parameters in the extra-vars flag when executing the playbook:

* string bmo\_state: Either "present" or "absent". Set to "present"
  to deploy baremetal-observability, set to "absent" to undeploy.
* string bmo\_inventory\_service: Set it to the name of the Ansible
  role that will retrieve relevant information for the exporters
* string[] bmo\_exporters: Set it to a list of metric exporters you
  wish to deploy

The task of setting up exporters to scrape metrics from all nodes
looks like this:

1. Connect the hub nodes to the BMC network
2. Get all BMC IPs and ports to scrape from the inventory service
3. Create a k8s.Deployment for each exporter in bmo\_exporters on the
   hub cluster configured with the username and password required to
   access the BMCs of each node
4. Create a k8s.Service for each exporter
5. Create an IPMI exporter ServiceMonitor connected to the IPMI
   exporter service and configured to scrape the IPs and ports, and
   discoverable by openshift-monitoring's Prometheus pods

**Access to Metrics**:

The cloud provider can access metrics through Prometheus or the
Thanos Querier (also the Observatorium API). Providers are able to
deploy their own Prometheus API compatible applications for tenants
to access metrics if they choose to do so.

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
