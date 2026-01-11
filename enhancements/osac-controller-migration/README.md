# OSAC Controller Migration: Design Document

**Project:** Move VirtualMachine Provisioning from Ansible to Native Kubernetes Controller
**Author:** CloudKit Team
**Last Updated:** January 11, 2026
**Status:** Phase 1 Research Complete

---

## Executive Summary

### Overview
This document outlines the migration of VirtualMachine creation logic from Ansible Automation Platform (AAP) to a native Kubernetes controller within cloudkit-controller. This migration eliminates external orchestration dependencies and simplifies the provisioning architecture.

### Scope
**In Scope:**
- Moving kubevirt.io/v1 VirtualMachine CR creation from Ansible playbooks to cloudkit-controller
- Creating associated resources (DataVolumes, Secrets, Services) in the controller
- Maintaining backwards compatibility during migration
- Future application to Cluster resource provisioning

**Out of Scope:**
- Changes to ComputeInstance CR creation (already handled by fulfillment-service)
- Complete AAP infrastructure removal (future phase)
- Floating IP management (massopencloud.esi integration remains in Ansible initially)

### Key Benefits
- **Reduced Latency:** Eliminate webhook → AAP → EDA → Ansible pipeline (30s → <5s)
- **Simplified Architecture:** Remove external orchestration dependency
- **Improved Reliability:** Native Kubernetes reconciliation loops vs. job queue
- **Enhanced Debuggability:** Single codebase for troubleshooting vs. distributed logs
- **Lower Operational Overhead:** Eliminate AAP infrastructure maintenance

---

## Background & Problem Statement

### Current Architecture Challenges

#### System Complexity
The current architecture spans multiple systems to provision a single VirtualMachine:

```
User → fulfillment-api → fulfillment-service → ComputeInstance CR
     → Webhook → AAP EDA → Rulebook Match → Job Template
     → Ansible Playbook → KubeVirt VirtualMachine CR
     → cloudkit-operator watches → Status updates
```

**Pain Points:**
1. **Multiple failure points:** Webhook delivery, AAP job queue, Ansible execution, K8s API
2. **Debugging complexity:** Logs distributed across fulfillment, AAP, EDA, and controller
3. **Latency overhead:** ~30 seconds from order to VM provisioning start
4. **Infrastructure overhead:** AAP Controller, EDA, Execution Environments requiring maintenance
5. **Deployment complexity:** AAP configuration-as-code, collections, job templates

#### Component Details

**AAP (Ansible Automation Platform):**
- AAP Controller: Manages job templates, inventories, credentials
- EDA (Event-Driven Ansible): Webhook listener with rulebook engine
- Execution Environment: Container images with Ansible + collections

**cloudkit-aap Repository:**
- Playbooks: `playbook_cloudkit_create_vm.yml`, `playbook_cloudkit_delete_vm.yml`
- Template Roles: `cloudkit.templates.ocp_virt_vm`
- EDA Rulebooks: Webhook routing logic

**Current cloudkit-operator Behavior:**
- Watches `cloudkit.openshift.io/v1alpha1/VirtualMachine` CR
- Triggers webhook to AAP when `DesiredConfigVersion != ReconciledConfigVersion`
- Waits for Ansible to set `cloudkit.openshift.io/reconciled-config-version` annotation
- Monitors `kubevirt.io/v1/VirtualMachine` for actual VM status

### Problem Statement

**The current AAP-based provisioning architecture introduces unnecessary complexity, latency, and operational overhead for a fundamentally simple Kubernetes native operation: creating child resources from parent CRs.**

---

## Current Architecture Deep Dive

### Resource Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 1: Order Submission                                           │
├─────────────────────────────────────────────────────────────────────┤
│ User → fulfillment API → fulfillment-service                        │
│   ↓                                                                  │
│ Creates: cloudkit.openshift.io/v1alpha1/VirtualMachine CR          │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 2: Controller Detection (Current)                             │
├─────────────────────────────────────────────────────────────────────┤
│ cloudkit-operator VirtualMachineReconciler watches CR               │
│   ↓                                                                  │
│ Detects: spec.desiredConfigVersion ≠ status.reconciledConfigVersion│
│   ↓                                                                  │
│ Triggers: CreateVMWebhook(vm) → HTTP POST to AAP EDA                │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 3: AAP Orchestration (TO BE REMOVED)                          │
├─────────────────────────────────────────────────────────────────────┤
│ EDA Rulebook matches webhook → Launches Job Template                │
│   ↓                                                                  │
│ AAP schedules Ansible playbook in Execution Environment             │
│   ↓                                                                  │
│ Playbook: playbook_cloudkit_create_vm.yml                           │
│   ↓                                                                  │
│ Calls Role: cloudkit.templates.ocp_virt_vm (tasks_from: create)    │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 4: Resource Creation (Ansible → Will move to Controller)      │
├─────────────────────────────────────────────────────────────────────┤
│ Creates in target namespace:                                        │
│   1. Secret: {vm_name}-cloud-init (base64 cloud-init data)         │
│   2. Secret: {vm_name}-ssh-public-key (optional)                   │
│   3. DataVolume: {vm_name}-root-disk (CDI, from container image)   │
│   4. VirtualMachine: {vm_name} (kubevirt.io/v1)                     │
│   5. Service: {vm_name}-load-balancer (LoadBalancer type)           │
│   6. Floating IP + Port Forwarding (massopencloud.esi)             │
│   ↓                                                                  │
│ Sets annotation: cloudkit.openshift.io/reconciled-config-version   │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 5: Status Tracking                                            │
├─────────────────────────────────────────────────────────────────────┤
│ cloudkit-operator watches kubevirt.io/v1/VirtualMachine             │
│   ↓                                                                  │
│ Updates: status.conditions[VirtualMachineConditionAvailable]        │
│   ↓                                                                  │
│ fulfillment-service polls CR status → Updates order in database     │
└─────────────────────────────────────────────────────────────────────┘
```

### Resources Created by Ansible Template

**Template:** `cloudkit.templates.ocp_virt_vm`
**Location:** `/cloudkit-aap/collections/ansible_collections/cloudkit/templates/roles/ocp_virt_vm/`

#### 1. Cloud-Init Secret
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {vm_name}-cloud-init
  namespace: {tenant_namespace}
type: Opaque
data:
  userdata: <base64(cloud_init_config)>
```

#### 2. SSH Public Key Secret (Optional)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {vm_name}-ssh-public-key
  namespace: {tenant_namespace}
type: Opaque
data:
  key: <base64(ssh_public_key)>
```

#### 3. DataVolume (CDI)
```yaml
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: {vm_name}-root-disk
  namespace: {tenant_namespace}
spec:
  source:
    registry:
      url: {image_source}
  storage:
    storageClassName: {CLOUDKIT_VM_OPERATIONS_STORAGE_CLASS or default}
    resources:
      requests:
        storage: {disk_size}
```

#### 4. VirtualMachine (KubeVirt)
```yaml
apiVersion: kubevirt.io/v1
kind: VirtualMachine
metadata:
  name: {vm_name}
  namespace: {tenant_namespace}
spec:
  running: true
  template:
    spec:
      domain:
        cpu:
          cores: {cpu_cores}
        memory:
          guest: {memory}
        devices:
          disks:
            - name: root-disk
              disk: {}
            - name: cloudinit
              disk: {}
      volumes:
        - name: root-disk
          dataVolume:
            name: {vm_name}-root-disk
        - name: cloudinit
          cloudInitNoCloud:
            secretRef:
              name: {vm_name}-cloud-init
      accessCredentials:
        - sshPublicKey:
            source:
              secret:
                secretName: {vm_name}-ssh-public-key
```

#### 5. LoadBalancer Service
```yaml
apiVersion: v1
kind: Service
metadata:
  name: {vm_name}-load-balancer
  namespace: {tenant_namespace}
spec:
  type: LoadBalancer
  selector:
    kubevirt.io/vm: {vm_name}
  ports:
    # Parsed from exposed_ports: "22/tcp,80/tcp,443/tcp"
    - name: port-22
      port: 22
      targetPort: 22
      protocol: TCP
```

#### 6. Floating IP & Port Forwarding
Handled by `massopencloud.esi.floating_ip` role (complex, kept in Ansible initially)

### Template Parameters

From `TemplateParameters` JSON field in `cloudkit.openshift.io/v1alpha1/VirtualMachine.spec`:

| Parameter          | Type   | Required | Example                    | Description                      |
|--------------------|--------|----------|----------------------------|----------------------------------|
| `cpu_cores`        | int    | Yes      | `4`                        | Number of CPU cores              |
| `memory`           | string | Yes      | `"8Gi"`                    | Memory allocation                |
| `disk_size`        | string | Yes      | `"50Gi"`                   | Root disk size                   |
| `image_source`     | string | Yes      | `"docker://registry/image"`| Container image for VM disk      |
| `cloud_init_config`| string | Yes      | `"#cloud-config\n..."`     | Cloud-init user data (base64)    |
| `ssh_public_key`   | string | No       | `"ssh-rsa AAAA..."`        | SSH public key (base64)          |
| `exposed_ports`    | string | Yes      | `"22/tcp,80/tcp"`          | Comma-separated port list        |

---

## Proposed Solution

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 1: Order Submission (UNCHANGED)                               │
├─────────────────────────────────────────────────────────────────────┤
│ User → fulfillment API → fulfillment-service                        │
│   ↓                                                                  │
│ Creates: cloudkit.openshift.io/v1alpha1/VirtualMachine CR          │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 2: Controller Reconciliation (NEW LOGIC)                      │
├─────────────────────────────────────────────────────────────────────┤
│ cloudkit-operator VirtualMachineReconciler watches CR               │
│   ↓                                                                  │
│ Detects: spec.desiredConfigVersion ≠ status.reconciledConfigVersion│
│   ↓                                                                  │
│ IF annotation "cloudkit.openshift.io/managed-by" = "controller":    │
│   ↓                                                                  │
│   Parse TemplateParameters JSON → Go struct                         │
│   ↓                                                                  │
│   Call resource builders:                                           │
│     - BuildCloudInitSecret()                                        │
│     - BuildSSHKeySecret()                                           │
│     - BuildDataVolume()                                             │
│     - BuildVirtualMachine()                                         │
│     - BuildLoadBalancerService()                                    │
│   ↓                                                                  │
│   Create resources in target namespace                              │
│   ↓                                                                  │
│   Set annotation: cloudkit.openshift.io/reconciled-config-version  │
│   ↓                                                                  │
│   Update status conditions                                          │
│                                                                      │
│ ELSE (managed-by = "aap"):                                          │
│   Trigger CreateVMWebhook() (FALLBACK during migration)            │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 3: Status Tracking (UNCHANGED)                                │
├─────────────────────────────────────────────────────────────────────┤
│ cloudkit-operator watches kubevirt.io/v1/VirtualMachine             │
│   ↓                                                                  │
│ Updates: status.conditions[VirtualMachineConditionAvailable]        │
│   ↓                                                                  │
│ fulfillment-service polls CR status → Updates order in database     │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Changes

#### 1. Extend VirtualMachineReconciler
**File:** `cloudkit-operator/internal/controller/virtualmachine_controller.go`

**Current:**
```go
func (r *VirtualMachineReconciler) handleUpdate(ctx context.Context, vm *cloudkitv1alpha1.VirtualMachine) error {
    if vm.Spec.DesiredConfigVersion != vm.Status.ReconciledConfigVersion {
        // Trigger webhook to AAP
        return r.CreateVMWebhook(ctx, vm)
    }
    return nil
}
```

**Proposed:**
```go
func (r *VirtualMachineReconciler) handleUpdate(ctx context.Context, vm *cloudkitv1alpha1.VirtualMachine) error {
    if vm.Spec.DesiredConfigVersion != vm.Status.ReconciledConfigVersion {
        // Check management mode
        managedBy := vm.Annotations["cloudkit.openshift.io/managed-by"]

        if managedBy == "controller" {
            // NEW: Create resources directly
            return r.reconcileVMResources(ctx, vm)
        }

        // FALLBACK: Use AAP webhook (during migration)
        return r.CreateVMWebhook(ctx, vm)
    }
    return nil
}

func (r *VirtualMachineReconciler) reconcileVMResources(ctx context.Context, vm *cloudkitv1alpha1.VirtualMachine) error {
    // 1. Parse TemplateParameters JSON
    params, err := parseTemplateParameters(vm.Spec.TemplateParameters)
    if err != nil {
        return err
    }

    // 2. Build resources
    resources := []client.Object{
        resources.BuildCloudInitSecret(vm, params),
        resources.BuildSSHKeySecret(vm, params),
        resources.BuildDataVolume(vm, params),
        resources.BuildVirtualMachine(vm, params),
        resources.BuildLoadBalancerService(vm, params),
    }

    // 3. Create/update resources
    for _, resource := range resources {
        if err := r.createOrUpdate(ctx, resource); err != nil {
            return err
        }
    }

    // 4. Update status
    vm.Status.ReconciledConfigVersion = vm.Spec.DesiredConfigVersion
    return r.Status().Update(ctx, vm)
}
```

#### 2. New Package: pkg/resources
Create resource builder functions to generate Kubernetes objects:

```
cloudkit-operator/pkg/resources/
├── virtualmachine/
│   ├── secret.go              # BuildCloudInitSecret, BuildSSHKeySecret
│   ├── datavolume.go          # BuildDataVolume
│   ├── virtualmachine.go      # BuildVirtualMachine (kubevirt.io/v1)
│   ├── service.go             # BuildLoadBalancerService
│   └── types.go               # TemplateParameters struct
└── common/
    └── utils.go               # Shared utilities
```

#### 3. Template Parameter Parser
```go
// pkg/resources/virtualmachine/types.go
type TemplateParameters struct {
    CPUCores       int    `json:"cpu_cores"`
    Memory         string `json:"memory"`
    DiskSize       string `json:"disk_size"`
    ImageSource    string `json:"image_source"`
    CloudInitB64   string `json:"cloud_init_config"`
    SSHPublicKeyB64 string `json:"ssh_public_key,omitempty"`
    ExposedPorts   string `json:"exposed_ports"`
}

func parseTemplateParameters(jsonStr string) (*TemplateParameters, error) {
    var params TemplateParameters
    if err := json.Unmarshal([]byte(jsonStr), &params); err != nil {
        return nil, fmt.Errorf("failed to parse template parameters: %w", err)
    }
    return &params, nil
}
```

---

## Design Details

### Resource Builder Implementations

#### 1. Cloud-Init Secret Builder
```go
// pkg/resources/virtualmachine/secret.go
func BuildCloudInitSecret(vm *cloudkitv1alpha1.VirtualMachine, params *TemplateParameters) *corev1.Secret {
    cloudInitData, _ := base64.StdEncoding.DecodeString(params.CloudInitB64)

    return &corev1.Secret{
        ObjectMeta: metav1.ObjectMeta{
            Name:      fmt.Sprintf("%s-cloud-init", vm.Name),
            Namespace: vm.Spec.TenantNamespace,
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(vm, cloudkitv1alpha1.GroupVersion.WithKind("VirtualMachine")),
            },
        },
        Type: corev1.SecretTypeOpaque,
        Data: map[string][]byte{
            "userdata": cloudInitData,
        },
    }
}
```

#### 2. DataVolume Builder
```go
// pkg/resources/virtualmachine/datavolume.go
func BuildDataVolume(vm *cloudkitv1alpha1.VirtualMachine, params *TemplateParameters) *cdiv1beta1.DataVolume {
    storageClass := getStorageClass() // From env or default

    return &cdiv1beta1.DataVolume{
        ObjectMeta: metav1.ObjectMeta{
            Name:      fmt.Sprintf("%s-root-disk", vm.Name),
            Namespace: vm.Spec.TenantNamespace,
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(vm, cloudkitv1alpha1.GroupVersion.WithKind("VirtualMachine")),
            },
        },
        Spec: cdiv1beta1.DataVolumeSpec{
            Source: &cdiv1beta1.DataVolumeSource{
                Registry: &cdiv1beta1.DataVolumeSourceRegistry{
                    URL: &params.ImageSource,
                },
            },
            Storage: &cdiv1beta1.StorageSpec{
                StorageClassName: &storageClass,
                Resources: corev1.ResourceRequirements{
                    Requests: corev1.ResourceList{
                        corev1.ResourceStorage: resource.MustParse(params.DiskSize),
                    },
                },
            },
        },
    }
}
```

#### 3. VirtualMachine Builder
```go
// pkg/resources/virtualmachine/virtualmachine.go
func BuildVirtualMachine(vm *cloudkitv1alpha1.VirtualMachine, params *TemplateParameters) *kubevirtv1.VirtualMachine {
    running := true

    kvVM := &kubevirtv1.VirtualMachine{
        ObjectMeta: metav1.ObjectMeta{
            Name:      vm.Name,
            Namespace: vm.Spec.TenantNamespace,
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(vm, cloudkitv1alpha1.GroupVersion.WithKind("VirtualMachine")),
            },
        },
        Spec: kubevirtv1.VirtualMachineSpec{
            Running: &running,
            Template: &kubevirtv1.VirtualMachineInstanceTemplateSpec{
                Spec: kubevirtv1.VirtualMachineInstanceSpec{
                    Domain: kubevirtv1.DomainSpec{
                        CPU: &kubevirtv1.CPU{
                            Cores: uint32(params.CPUCores),
                        },
                        Memory: &kubevirtv1.Memory{
                            Guest: resource.MustParse(params.Memory),
                        },
                        Devices: kubevirtv1.Devices{
                            Disks: []kubevirtv1.Disk{
                                {
                                    Name: "root-disk",
                                    DiskDevice: kubevirtv1.DiskDevice{
                                        Disk: &kubevirtv1.DiskTarget{},
                                    },
                                },
                                {
                                    Name: "cloudinit",
                                    DiskDevice: kubevirtv1.DiskDevice{
                                        Disk: &kubevirtv1.DiskTarget{},
                                    },
                                },
                            },
                        },
                    },
                    Volumes: []kubevirtv1.Volume{
                        {
                            Name: "root-disk",
                            VolumeSource: kubevirtv1.VolumeSource{
                                DataVolume: &kubevirtv1.DataVolumeSource{
                                    Name: fmt.Sprintf("%s-root-disk", vm.Name),
                                },
                            },
                        },
                        {
                            Name: "cloudinit",
                            VolumeSource: kubevirtv1.VolumeSource{
                                CloudInitNoCloud: &kubevirtv1.CloudInitNoCloudSource{
                                    UserDataSecretRef: &corev1.LocalObjectReference{
                                        Name: fmt.Sprintf("%s-cloud-init", vm.Name),
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }

    // Add SSH access credentials if provided
    if params.SSHPublicKeyB64 != "" {
        kvVM.Spec.Template.Spec.AccessCredentials = []kubevirtv1.AccessCredential{
            {
                SSHPublicKey: &kubevirtv1.SSHPublicKeyAccessCredential{
                    Source: kubevirtv1.SSHPublicKeyAccessCredentialSource{
                        Secret: &kubevirtv1.AccessCredentialSecretSource{
                            SecretName: fmt.Sprintf("%s-ssh-public-key", vm.Name),
                        },
                    },
                },
            },
        }
    }

    return kvVM
}
```

#### 4. LoadBalancer Service Builder
```go
// pkg/resources/virtualmachine/service.go
func BuildLoadBalancerService(vm *cloudkitv1alpha1.VirtualMachine, params *TemplateParameters) *corev1.Service {
    ports := parseExposedPorts(params.ExposedPorts)

    return &corev1.Service{
        ObjectMeta: metav1.ObjectMeta{
            Name:      fmt.Sprintf("%s-load-balancer", vm.Name),
            Namespace: vm.Spec.TenantNamespace,
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(vm, cloudkitv1alpha1.GroupVersion.WithKind("VirtualMachine")),
            },
        },
        Spec: corev1.ServiceSpec{
            Type: corev1.ServiceTypeLoadBalancer,
            Selector: map[string]string{
                "kubevirt.io/vm": vm.Name,
            },
            Ports: ports,
        },
    }
}

func parseExposedPorts(portsStr string) []corev1.ServicePort {
    // Parse "22/tcp,80/tcp,443/tcp" → []ServicePort
    var servicePorts []corev1.ServicePort
    for _, portSpec := range strings.Split(portsStr, ",") {
        parts := strings.Split(strings.TrimSpace(portSpec), "/")
        if len(parts) != 2 {
            continue
        }
        port, _ := strconv.Atoi(parts[0])
        protocol := strings.ToUpper(parts[1])

        servicePorts = append(servicePorts, corev1.ServicePort{
            Name:       fmt.Sprintf("port-%d", port),
            Port:       int32(port),
            TargetPort: intstr.FromInt(port),
            Protocol:   corev1.Protocol(protocol),
        })
    }
    return servicePorts
}
```

### Dual-Mode Support (Migration Strategy)

To enable zero-downtime migration, the controller will respect an annotation:

```yaml
apiVersion: cloudkit.openshift.io/v1alpha1
kind: VirtualMachine
metadata:
  name: test-vm-001
  annotations:
    cloudkit.openshift.io/managed-by: "controller"  # or "aap"
```

**Migration Flow:**
1. Deploy updated cloudkit-operator with new resource builder logic
2. Default annotation to `"aap"` → no behavior change
3. Gradually update VMs with `managed-by: "controller"` annotation
4. Monitor success rates, rollback if needed by reverting annotation
5. Once stable, update fulfillment-service to set `managed-by: "controller"` on new VMs
6. After 100% adoption, remove AAP webhook code path

---

## Implementation Plan

### Phase 1: Research and Design ✅ COMPLETE

**Completed Tasks:**
- ✅ Mapped Ansible playbook flow
- ✅ Documented all resources created by template role
- ✅ Analyzed cloudkit-operator VirtualMachine controller
- ✅ Identified template parameters
- ✅ Corrected project scope
- ✅ Created design document

### Phase 2: Core Controller Implementation

**Tasks:**
1. Create `pkg/resources/virtualmachine/` package
2. Implement resource builder functions:
   - `BuildCloudInitSecret()`
   - `BuildSSHKeySecret()`
   - `BuildDataVolume()`
   - `BuildVirtualMachine()`
   - `BuildLoadBalancerService()`
3. Implement `parseTemplateParameters()` JSON parser
4. Extend `VirtualMachineReconciler.handleUpdate()` with dual-mode logic
5. Implement `reconcileVMResources()` method
6. Add annotation check for `managed-by` field
7. Add comprehensive logging and error handling

**Deliverables:**
- Working controller code that creates VMs natively
- Unit tests for all resource builders
- Integration test with fake Kubernetes client

### Phase 3: Testing

#### Unit Tests
- Test each resource builder with various parameter combinations
- Test template parameter parsing (valid/invalid JSON)
- Test annotation-based routing logic
- Target: >80% code coverage

#### Integration Tests
- Set up `envtest` environment with KubeVirt + CDI CRDs
- Test full reconciliation loop:
  - Create VirtualMachine CR → verify all child resources created
  - Update VirtualMachine CR → verify resources updated
  - Delete VirtualMachine CR → verify cleanup (OwnerReferences)
- Test dual-mode annotation switching

#### E2E Testing
- Deploy to dev cluster with real KubeVirt
- Create VirtualMachine CR with `managed-by: controller`
- Verify VM boots successfully
- Compare created resources with AAP-generated resources (diff check)
- Test error scenarios:
  - Invalid template parameters
  - Missing DataVolume storage class
  - KubeVirt API errors

**Acceptance Criteria:**
- All resources match AAP output (functional parity)
- VM boots and is accessible via SSH
- Status updates correctly propagate
- Cleanup works (deletion removes all child resources)

### Phase 4: Pilot Deployment

#### Dev Environment
- Deploy updated cloudkit-operator to dev namespace
- Test with manual VirtualMachine CR creation
- Fix any bugs discovered during testing

#### Staging Environment
- Deploy to staging cluster
- Configure fulfillment-service to create 10% of VMs with `managed-by: controller`
- Monitor metrics:
  - Success rate (target: >99%)
  - Latency (target: <5s order-to-VM-creation)
  - Resource parity (automated diff check)

#### Gradual Rollout
- Increase to 25% traffic if initial metrics pass
- Increase to 50% traffic if previous metrics pass
- Each increase requires monitoring window

**Rollback Plan:**
- Revert annotation to `managed-by: aap` in fulfillment-service
- AAP continues to handle provisioning (no code changes needed)

### Phase 5: Full Migration

#### Production Deployment
- Deploy to production cluster
- Start with 10% traffic, same gradual rollout approach
- Monitoring windows between increases

#### 100% Adoption
- All new VMs created with `managed-by: controller`
- AAP infrastructure kept running (idle)
- Monitor for extended period

#### AAP Decommissioning
- Verify zero AAP jobs triggered
- Archive AAP job history
- Backup playbooks and collections to archive repository
- Remove EDA rulebooks
- Shut down AAP Controller and EDA services
- Remove AAP deployment manifests

### Phase 6: Cleanup

**Tasks:**
1. Remove webhook code path from `VirtualMachineReconciler`
2. Remove `managed-by` annotation check (always use controller)
3. Archive `cloudkit-aap` repository
4. Update documentation:
   - Architecture diagrams
   - Deployment guides
   - Troubleshooting runbooks
5. Remove AAP-related dependencies from `go.mod`
6. Celebrate success

---

## Risk Analysis & Mitigation

### Risk 1: Template Porting Bugs
**Description:** Go resource builders create resources with subtle differences from Ansible, causing VM boot failures

**Impact:** High - VMs fail to provision, user orders fail
**Probability:** Medium - Complex YAML generation logic

**Mitigation:**
- Automated diff testing: Compare controller-generated resources with AAP-generated resources
- Parallel testing: Run AAP and controller side-by-side, compare outputs
- Incremental rollout: Start with 10% traffic, increase only if metrics pass
- Fast rollback: Annotation-based switching allows instant revert to AAP

### Risk 2: Performance Regression
**Description:** Controller reconciliation causes performance issues (high CPU, slow provisioning)

**Impact:** Medium - Slower provisioning, increased resource usage
**Probability:** Low - Kubernetes controllers are well-optimized

**Mitigation:**
- Load testing in staging with 100+ concurrent VM creations
- Prometheus metrics to track reconciliation duration
- Optimize reconciliation loop (efficient caching, predicate filters)
- Add rate limiting if necessary

### Risk 3: Migration Bugs Affecting Production
**Description:** Controller bugs cause production order failures during rollout

**Impact:** High - Customer impact, revenue loss
**Probability:** Medium - New code path

**Mitigation:**
- Extensive testing (unit, integration, E2E)
- Gradual rollout with 24-hour monitoring windows
- Dual-mode support for instant rollback
- Feature flags to disable controller path
- On-call engineer monitoring during rollout
- Rollback runbook prepared in advance

### Risk 4: Storage Class Detection Fails
**Description:** Ansible auto-detects default storage class; Go logic may fail in edge cases

**Impact:** Medium - DataVolume creation fails
**Probability:** Low - Well-documented K8s API

**Mitigation:**
- Unit tests for storage class detection logic
- Support explicit override via env var `CLOUDKIT_VM_OPERATIONS_STORAGE_CLASS`
- Graceful error handling with clear error messages
- Test in multiple cluster environments (dev, staging, prod)

### Risk 5: Floating IP Logic Not Ported
**Description:** Initial implementation skips floating IP assignment (massopencloud.esi), breaking networking for some environments

**Impact:** Medium - VMs not accessible from external network
**Probability:** Low - Only affects environments using ESI floating IPs

**Mitigation:**
- Clearly document that floating IP assignment remains in Ansible Phase 1
- Keep AAP running for environments requiring floating IPs
- Plan Phase 2 to port floating IP logic to controller
- Or: Create separate FloatingIP controller

---

## Success Metrics

### Must-Have (Required for Production)
- ✅ Controller successfully creates VirtualMachines from cloudkit CRs
- ✅ All resources match AAP-created resources (byte-for-byte YAML equivalence for core resources)
- ✅ VMs boot successfully and are accessible via SSH
- ✅ Status updates correctly propagate to fulfillment-service
- ✅ Error handling and retries work correctly
- ✅ Cleanup/deletion removes all child resources (via OwnerReferences)
- ✅ Zero downtime migration (dual-mode operation)
- ✅ Success rate ≥99.9% (matching or exceeding AAP)

### Should-Have (Performance Targets)
- ⚡ Order-to-VM-creation latency <5 seconds (vs. AAP ~30s)
- 📊 Prometheus metrics and Grafana dashboards operational
- 🧪 Automated test coverage >80%
- 📖 Documentation complete (deployment, migration, troubleshooting)

### Nice-to-Have (Future Enhancements)
- 🎯 Template validation API (validate parameters before order submission)
- 🧰 CLI tool for debugging VM creation (`cloudkit-cli debug vm <name>`)
- 🔄 Support for custom user-defined templates
- 🧪 Dry-run mode for testing templates without actual resource creation

---

## Open Questions

### 1. Floating IP Assignment
**Question:** Should we port massopencloud.esi floating IP logic to controller in Phase 1?

**Options:**
- A) Keep in Ansible initially (simplify Phase 1 scope)
- B) Port to controller immediately (full feature parity)
- C) Create separate FloatingIP controller (better separation of concerns)

**Recommendation:** Option A - Keep in Ansible for Phase 1. The `massopencloud.esi` role is complex and environment-specific. Allows us to ship controller faster and migrate floating IP logic in Phase 2.

### 2. Storage Class Selection
**Question:** How should we handle storage class auto-detection?

**Current Ansible Logic:**
```yaml
- name: Get default storage class
  kubernetes.core.k8s_info:
    kind: StorageClass
    label_selectors:
      - storageclass.kubernetes.io/is-default-class=true
  register: default_sc

- set_fact:
    storage_class: "{{ lookup('env', 'CLOUDKIT_VM_OPERATIONS_STORAGE_CLASS') | default(default_sc.resources[0].metadata.name, true) }}"
```

**Proposed Go Logic:**
```go
func getStorageClass(ctx context.Context, client client.Client) (string, error) {
    // 1. Check env var
    if sc := os.Getenv("CLOUDKIT_VM_OPERATIONS_STORAGE_CLASS"); sc != "" {
        return sc, nil
    }

    // 2. Find default storage class
    var scList storagev1.StorageClassList
    if err := client.List(ctx, &scList); err != nil {
        return "", err
    }

    for _, sc := range scList.Items {
        if sc.Annotations["storageclass.kubernetes.io/is-default-class"] == "true" {
            return sc.Name, nil
        }
    }

    return "", fmt.Errorf("no default storage class found")
}
```

**Decision:** Approved - Matches Ansible logic

### 3. Repository Structure
**Question:** Should this be in cloudkit-operator or separate osac-controller repo?

**Options:**
- A) Extend cloudkit-operator (single binary, shared code)
- B) New osac-controller repo (clean separation, independent versioning)

**Recommendation:** Option A (extend cloudkit-operator)
- Reuse existing VirtualMachineReconciler
- No new deployment to manage
- Simpler dependency management

### 4. Error Handling Strategy
**Question:** How should we handle transient errors (API server unavailable, etc.)?

**Proposal:**
- Use controller-runtime's built-in retry with exponential backoff
- Max retries: 10 (controller-runtime default)
- Backoff: 5ms → 10ms → 20ms → ... → 1000ms (capped)
- After max retries, update VirtualMachine status with error condition
- Manual intervention required (or webhook fallback to AAP)

**Decision:** Approved

---

## Appendix

### A. Current Ansible Playbook Flow

**Playbook:** `playbook_cloudkit_create_vm.yml`

```yaml
---
- name: Create CloudKit VirtualMachine
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Get VirtualMachine CR from API
      kubernetes.core.k8s_info:
        api_version: cloudkit.openshift.io/v1alpha1
        kind: VirtualMachine
        name: "{{ vm_name }}"
        namespace: "{{ vm_namespace }}"
      register: vm_cr

    - name: Parse template parameters
      set_fact:
        template_params: "{{ vm_cr.resources[0].spec.templateParameters | from_json }}"

    - name: Call template role
      include_role:
        name: cloudkit.templates.ocp_virt_vm
        tasks_from: create
      vars:
        cpu_cores: "{{ template_params.cpu_cores }}"
        memory: "{{ template_params.memory }}"
        disk_size: "{{ template_params.disk_size }}"
        image_source: "{{ template_params.image_source }}"
        cloud_init_config: "{{ template_params.cloud_init_config }}"
        ssh_public_key: "{{ template_params.ssh_public_key | default('') }}"
        exposed_ports: "{{ template_params.exposed_ports }}"

    - name: Update VirtualMachine CR status
      kubernetes.core.k8s:
        api_version: cloudkit.openshift.io/v1alpha1
        kind: VirtualMachine
        name: "{{ vm_name }}"
        namespace: "{{ vm_namespace }}"
        definition:
          metadata:
            annotations:
              cloudkit.openshift.io/reconciled-config-version: "{{ vm_cr.resources[0].spec.desiredConfigVersion }}"
```

### B. References

**Repositories:**
- `cloudkit-operator`: https://github.com/innabox/cloudkit-operator
- `cloudkit-aap`: https://github.com/innabox/cloudkit-aap
- `fulfillment-service`: https://github.com/innabox/fulfillment-service

**Documentation:**
- KubeVirt API: https://kubevirt.io/api-reference/
- CDI API: https://github.com/kubevirt/containerized-data-importer
- controller-runtime: https://pkg.go.dev/sigs.k8s.io/controller-runtime

**Related Design Docs:**
- CloudKit Architecture Overview (link TBD)
- AAP to Controller Migration Strategy (this document)

---

## Document Revision History

| Date       | Version | Author       | Changes                                  |
|------------|---------|--------------|------------------------------------------|
| 2026-01-11 | 1.0     | CloudKit Team| Initial design document created          |
| 2026-01-11 | 1.1     | CloudKit Team| Phase 1 research complete, scope refined |

---

**Next Steps:**
1. ✅ Stakeholder review and approval
2. 🔄 Begin Phase 2: Core Controller Implementation
3. 🔄 Set up project tracking (GitHub Issues/Jira)

---
*This document is maintained in `/home/etabak/.claude/plans/osac-controller-migration-plan.md`*
