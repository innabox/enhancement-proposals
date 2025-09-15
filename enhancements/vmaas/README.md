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

# Virtualization as a service


## Summary

We want to provide a service that allows a tenant to create and manage VMs.

## Motivation

TBD

### User Stories

#### As a tenant

- I want to list a pre-defined VM templates
- I want to create a VM based on a pre-defined template
- I want a VM that has access to specialized hardware (e.g.: GPU)
- I want to customize the pre-defined template for my usage
- I want to attach and detach block storage on my VM that transcends the lifecycle of the VM
- I want to manage the lifecycle of my VM (start/stop/terminate)
- I want to import my OS base image
- I want to list available base OS images
- I want to manage (create, list, delete) my private network
- I want to attach my VMs in a virtual private network
- I want my VM to be exposed outside of my private network
- I want my VMs to be attached to my own physical L2 network
- I want to connect on my VM through serial console
- I want to keep running my VM when a node goes out of service

#### As a service provider:

- I want to define VM templates
- I want to manually trigger VM migration

### Goals

TBD

### Non-Goals

TBD

## Proposal

### Network isolation

This design relies on UDN (User Defined Networking, it is the networking component provided with Openshift, it allows the definition of virtual private subnets, and provides the ability to connect on physical networks (localnet).

Moverover, Kubevirt supports UDN layer 2 mode which offers the ability to live-migrate VMs across OCP nodes.

### Ingress

We can expose services running on VM(s) using a “LoadBalancer” service (e.g.: relying on MetalLB).

### APIs

Virtual private subnet creation:

```
apiVersion: cloudkit.openshift.io/v1alpha1
kind: VirtualPrivateSubnet
metadata:
  name: example
  finalizers:
  - cloudkit.openshift.io/finalizer
annotations:
  cloudkit.openshift.io/ref-count: 1 # +1 when a VM is created, -1 when a VM is deleted  
spec:
  ipv4Cidr: 192.168.100.0/24
```

We will create a new, unique namespace, and the UDN definition to create a L2 layer and the corresponding subnet.

Since several VMs can be attached to the same network, we introduce an annotation that will be used to count the number of VMs attached to this network, and a finalizer to prevent its deletion before all the VMs are deleted.

Load balancer:

```
apiVersion: cloudkit.openshift.io/v1alpha1
kind: LoadBalancer
metadata:
  name: example
spec:
  hostRefs:
  - kind: VirtualMachineHost
    name: exampleVM
  portMapping:
  - protocol: TCP
    externalPort: 80
    internalPort: 80
```

All hosts must be associated with the same network.

### Template management

Like cluster fulfillment, there will be a mechanism to define templates as Ansible roles. Templates contain predefined VM classes which define default OS base image, CPU architecture, number of cores, amount of memory, storage, user data, …

A template VM might define the following properties, and let a tenant to customize some of them (should be a 1:1 mapping to KubeVirt resources):

- Name
- Tenant
- OS base image
- Instance class, which specify the family (translating into general/compute/memory/gpu/arch), and the amount of CPU and memory (TBD, e.g.: general.large)
- User-data (cloud-init)
- Networking, namespace + UDN at first, and localnet later?
  * Layer 3 only for Networking.
- SSH keys
- Storage, size of the boot volume (+ I/O performance, encryption)
- State (started/stopped)

There will be an API to publish these templates in the fulfillment service, and list these templates from it.

KubeVirt UI provides a functionality based on OCP templates that generates a VirtualMachine resource, it is safe to assume that we can use any tool we want to, and rely on Ansible/AAP to define our own.

### VM management

VMs will be managed using KuberVirt, basically the user will have to provide 3 informations to create a VM:

- Template name
- Template overrides
- A network

### OS base image management

Tenants will have the ability to import their own base images. Since OSC backend relies on multiple OCP clusters, and tenants’ VMs may be distributed on multiple ones, base images be centralized on an OCI container registry before being consumed by KubeVirt on the destination cluster.

### APIs

```
apiVersion: cloudkit.openshift.io/v1alpha1
kind: VirtualMachineHost
metadata:
  name: example
  finalizers:
  - cloudkit.openshift.io/finalizer # to update ref-count in VirtualPrivateNetwork
spec 
  networkRef:
    kind: VirtualPrivateNetwork
    name: exampleNetwork
 template: rhel-10
 templateParameters:
   instanceType: o1.small
   SSHPublicKey: ...
   powerState: stopped
```

### Workflow Description

TBD

### API Extensions

TBD

### Implementation Details/Notes/Constraints

#### VM creation minimal flow

1. Tenant creates a VM Host, the automation:
    1. Creates a namespace
    2. Creates a UDN L2 network
    3. Creates a Kubevirt CR

#### Tasks

- Fulfilment-cli
  * CRUD on VirtualMachineHost
  * List VM templates
- Fulfillment-service:
  * [Create VirtualMachineHost management API in fulfillment-service](https://github.com/innabox/issues/issues/201&sa=D&source=editors&ust=1757970010188331&usg=AOvVaw07B9NvURxHW07nF4X-1X41)
  * [Publish VM templates endpoint in fulfillment-service](https://github.com/innabox/issues/issues/203&sa=D&source=editors&ust=1757970010188598&usg=AOvVaw35ilTLz7wwMg4_W6YdNeMB)
  * [List VM templates](https://github.com/innabox/issues/issues/202&sa=D&source=editors&ust=1757970010188846&usg=AOvVaw2vg_K25W8xerGfSgYxrI4z)
- Cloudkit-operator:
  * [Create VirtualMachineHost controller](https://github.com/innabox/issues/issues/204&sa=D&source=editors&ust=1757970010189157&usg=AOvVaw3brz_MVBsWOSWzjjv6Mv9P)
* AAP:
  - [Create/Delete VM EDA and playbooks](https://github.com/innabox/issues/issues/207&sa=D&source=editors&ust=1757970010189421&usg=AOvVaw3xVLsU3dXhvFOKs1ZxGPzf
  - [Create VM templates](https://github.com/innabox/issues/issues/205&sa=D&source=editors&ust=1757970010189609&usg=AOvVaw0buvglSiCKKLOSh-VBrxJH)
  - [Publish VM templates to fulfillment-service](https://github.com/innabox/issues/issues/206&sa=D&source=editors&ust=1757970010189850&usg=AOvVaw1JCATg3Xsg0QA93zUyQUZf)

Development:

- Public API to manage networks + operator + AAP (?)
- Public API to manage VMs + operator + AAP
- Public API to publish template
- Create VM template in AAP + publication
- OS base image management + operator

#### UDN layer 2 definition

```
apiVersion: v1
kind: Namespace
metadata:
  name: udn-dev
  labels:
    k8s.ovn.org/primary-user-defined-network: ""
---
apiVersion: k8s.ovn.org/v1
kind: UserDefinedNetwork
metadata:
  name: udn-dev
  namespace: udn-dev
spec:
  layer2:
    ipam:
      lifecycle: Persistent
    role: Primary
    subnets:
    - 10.200.0.0/16
  topology: Layer2
```

#### UDN localnet definition

Requires NMState operator:

```
apiVersion: nmstate.io/v1
kind: NodeNetworkConfigurationPolicy
metadata:
  name: mapping 
spec:
  nodeSelector:
    node-role.kubernetes.io/worker: '' 
  desiredState:
    ovn:
      bridge-mappings:
      - localnet: localnet1 
        bridge: br-ex 
        state: present
---
apiVersion: k8s.ovn.org/v1
kind: ClusterUserDefinedNetwork
metadata:
  name: cudn-localnet 
spec:
  namespaceSelector: 
    matchExpressions: 
    - key: kubernetes.io/metadata.name
      operator: In 
      values: ["red", "blue"]
  network:
    topology: Localnet 
    localnet:
        role: Secondary 
        physicalNetworkName: localnet1 
        ipam:
          mode: Disabled
```

#### Live Migrations using UDN and KubeVirt

- Kubevirt only allows/supports UDN L2
- Localnet is not ideal due to the static nature of this approach and the VLAN is not necessarily the same on the destination node. (IE VxLAN endpoints)
- Complex hardware dependencies are hit and miss.  It all depends on the hardware, but there is the ability to migrate things like GPUs and NICs (SR-IOV) in specific circumstances.
- Here is an instance where we can use templates to avoid the complexity.
- Things to be aware of which could cause problems:
  * Localnet networks which tie to specific h/w i/f.,
  * SR-IOV,
  * DPDK,
  * Node selecting or filtering logic,
  * Possible DHCP issues.

- Live migrations describe the type of migration and effected changes.  

  * L2 UDN: Updates MAC learning tables, & ARP caches.
  * L3 UDN: Updates node IP routing tables pointing to the new hosting node.
  * L3 migrations should not be interpreted as allowing an IP address to change on the fly.

#### UDN Topology Types

UDN has topology types (L2/L3) with different block types highlighting the differences between one or the other.

Layer2 (layer2: block)

- Bridged networking - VMs appear on same broadcast domain
- DHCP/Static IP assignment - Needs IPAM (IP Address Management) for IP allocation
- East-west traffic flows directly between VMs without routing
- Flat network model - All VMs share the same subnet

Layer3 (layer3: block):

- Routed networking - Each node gets its own subnet slice
- Distributed subnets - hostSubnet defines how the CIDR is carved up per node
- Inter-node routing required for VM-to-VM communication
- Scalable addressing - Prevents IP exhaustion on large clusters

 Configuration Differences:

- Layer2 needs IPAM for IP management

  ```
  layer2:
    ipam:
      lifecycle: Persistent  # How long IPs are reserved
    subnets: [10.200.0.0/16]  # Flat subnet
  ```

- Layer3 needs subnet distribution

  ```
  layer3:
    subnets:
    - cidr: 10.200.0.0/16     # Overall range
      hostSubnet: 24          # Each node gets /24 slice
  ```

#### Tasks

- List options in kubevirt that prevents Live VM migration
- Try UDN + kubevirt
  - Describe how Egress IP works
    - Default Egress
    - Why do we need an Egress IP
  - Look at the manifests, will help to design API
- Describe Template and MVP
  - VM Host / HostPool
    - Disk
    - Memory
    - Storage
    - Persistent vs Ephemeral
    - SSH keys
    - Cloud-init 
  - Network
  - OS base image (Registry Service)
  - Test: 
    - Create network
    - Create VM in the network
    - Communicate between Nodes (2 VMs)
    - Floating IP / LoadBalancer
- Create a sequence diagram, showing service/operator/AAP responsibilities
  - VM management
  - Base image management
  - Network management
- Get information about Metal LB and UDN’s floating IP is supposed to work in order to grab a public IP (and other related networking stuff)

#### External resources

- [Red Hat Sovereignty Technical Architecture](https://docs.google.com/presentation/d/1g23omSQ46NZ6qyDi-I4Q8mGNt-NQpKk0vOuaZf8Usqw/edit?slide%3Did.g344ca2ed691_0_2780%23slide%3Did.g344ca2ed691_0_2780&sa=D&source=editors&ust=1757970010209722&usg=AOvVaw0KkWOZaTJyX2nac50mzfW)
- [RHSovCloud-Network-Scenarios-0.1](https://docs.google.com/presentation/d/1_wYAbfoCcmuIOx-esCcOoSFJFR7tgkrypyyIHa7S4AY/edit?slide%3Did.g30e84f14e68_0_6149%23slide%3Did.g30e84f14e68_0_6149&sa=D&source=editors&ust=1757970010209955&usg=AOvVaw3oLbSpaYriqUYAxZ1TQlWX)
- [Red Hat Sovereignty Technical Architecture](https://docs.google.com/presentation/d/1g23omSQ46NZ6qyDi-I4Q8mGNt-NQpKk0vOuaZf8Usqw/edit?slide%3Did.g344ca2ed691_0_2780%23slide%3Did.g344ca2ed691_0_2780&sa=D&source=editors&ust=1757970010210162&usg=AOvVaw1NbKJtheHnk47tN4Ot5KVy)

UDN:  

- [User Defined Networks on OpenShift](https://docs.google.com/presentation/d/1Hx1Fzm1F9EkmqrmTjbMHPBAuIls-2-oK1IVrzFnW3L4/edit?slide%3Did.g31966f3f64c_0_855%23slide%3Did.g31966f3f64c_0_855&sa=D&source=editors&ust=1757970010210475&usg=AOvVaw3lrbnP41fTOVcfwnbXAuwW)
- <https://ovn-kubernetes.io/okeps/okep-5193-user-defined-networks/>
- [Chapter 2. Primary networks | Multiple networks | OpenShift Container Platform | 4.19 | Red Hat Documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/multiple_networks/primary-networks%23about-user-defined-networks&sa=D&source=editors&ust=1757970010211384&usg=AOvVaw22g82g1WsGtCpIV_OOnpnt)
- [Chapter 3. Secondary networks | Multiple networks | OpenShift Container Platform | 4.19 | Red Hat Documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/multiple_networks/secondary-networks%23configuration-localnet-switched-topology_configuring-additional-network-ovnk&sa=D&source=editors&ust=1757970010211903&usg=AOvVaw0q1VmdCCcREjz1O3xKPmt)
- [User defined networks in Red Hat OpenShift Virtualization](https://www.redhat.com/en/blog/user-defined-networks-red-hat-openshift-virtualization&sa=D&source=editors&ust=1757970010212242&usg=AOvVaw2KBAek4qp-jL8eF_I9gN5)

### Risks and Mitigations

TBD

### Drawbacks

TBD

## Alternatives (Not Implemented)

TBD

## Open Questions [optional]

- The main point is to provide a public API that will select a management cluster to provision a VM (given requested resources CPU/Mem/GPU)? => not the priority
- What is the added value on top of kube virt? => multi-tenancy, multiple virt clusters, higher level networking primitives
- Since we plan to rely on the OCP stack (ACM/KubeVirt/Hypershift), is there something we want to make pluggable using Ansible? (access network configuration to the VM?)
- Do we need to provision infra on-demand to run kubevirt workload?
- What about networking isolation, how kubevirt works? What model to prioritize?
- Representation of resources a la AWS? `<class>.<size>` (e.g.: t3.xlarge (general purpose), c3.small (compute), m3.medium (memory))
- Storage options?
- Should we focus on cluster provisioning or VM provisioning?
- Which networking model should we prioritize? The ability to connect on a physical network or the ability to create a virtual private network?
- How to make sure we co-collocate network and VM definitions together?
- From what I understand, there will be different ways to handle networking depending if we want VM workloads (UDN), BM workloads (Openstack), or BM+VM workloads (UDN localnet + Openstack). Would it make sense to create a templating system where the service provider would define pre-defined network setups, and have only one “Network” CR?

- Our existing template concept should continue to be valuable for defining different kinds of VMs or even virtualized applications delivered as VMs.

- That seem like an advanced use case to tackle later. It seems reasonable to start with an assumption that cloud providers will divide their compute hosts into logical virtualization clusters based largely on physical location and network topology. If they have 900 virt host, maybe they divide into 3 clusters of 300 nodes each. I wouldn't worry about "rebalancing" among different virt clusters at this point.

  Conversation from google doc comment:

  > * yes, makes sense
  > 
  > * Are we thinking VMs will be served by the HCP hub worker nodes or the HCP spoke clusters?
  > 
  > * A provider-run cluster will host VMs. For simplicity, we can start by making that the same cluster that the rest of the management tooling runs on. But there could be good reason to separate the virt-hosting cluster later.
  > 
  > * Will networking become complex if we have a tenant cluster and a tenant VM that want to be on the same L2?  Technically doesn't the VM need to run on the tenant cluster for this?
  > 
  > * No. There is no requirement that a VM needs to be located on the tenant cluster in order to access a particular L2 network. L2 networks are managed external to the clusters.
  > 
  > * A UDN can be connected to a VLAN on the physical network. I assume that'll be a primary mechanism for establishing a "VPC" experience. A tenant's VMs will be connected to the UDN, whether those are individual VMs or openshift nodes in VMs. If the tenant also has a bare metal openshift cluster, then we'd depend on the physical network fabric to put those nodes onto a VLAN, which can be bridged to the UDN.
  > 
  > * Basic UDN+virt info: https://www.redhat.com/en/blog/user-defined-networks-red-hat-openshift-virtualization
  > 
  > * Lots of detail about UDNs: https://docs.redhat.com/en/documentation/openshift\_container\_platform/4.19/html/multiple\_networks/primary-networks#about-user-defined-networks

- We need to start fitting this into a broader concept of a VPC. But generally, we should do a quick survey of what the options are for connecting a VM to other networks besides the pod network.

  > - We talked about the concept of network in the case of the baremetal fulfillment, so I was thinking that we could extend it to mkae it work for the VM case as well.

  > - Yes, though I think that comes with downsides IIRC, for example there won't be health checks on a VM if it's not on the pod network. Not a deal-breaker, but that's the sort of thing we need to understand.

  > - Also we could potentially simplify the network isolation story even if we're using real VLANs on the physical network. If we put the host OS in charge of connecting a VM to a particular VLAN, and give each host access to all the VLANs, that means we don't have to worry about about dynamically managing the network fabric like we do in the BM case.

  > - @mhrivnak@redhat.com Is the definition of VPC you're referring to the AWS definition?

  > - That's the inspiration, but we need to have our own definition. Private network, isolated from other tenants, controls around ingress and egress, perhaps continuity across management clusters, etc. Lots of things to consider.

  > - Sure.  Fundamentally VPC only allows layer 3 and they do some funky stuff that is hidden in layer 2.  For v1.0, I would say we stick to what is supported by OCP Virtualization.

- I think I need more context to help me understand this question.

  > It's what we discussed in our last meeting. 

  > In case of UDN L2, VM and network definition need to be on the same HUB cluster. Knowing that network must be defined before the VM, what should condition the selection of the HUB cluster. The network or the VM?

  > Thinking about it, it's maybe not an interesting question, because a tenant may want to spawn VMs in that same network latter, and then face a issue getting the resources they want.

  > For localnet, we should not have this constraint, as the network is defined globally, and not local to a HUB cluster.

- openstack? Is this just referencing that ESI uses some openstack parts?

- I think we need some formality around defining networks, similar to a VPC construct found in many clouds. We should have some more focused design discussion on that topic.

- Is there another option supported by openshift virt?

- Could you add a bit of context for each of these explaining why it might cause a problem that we should be aware of?

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
