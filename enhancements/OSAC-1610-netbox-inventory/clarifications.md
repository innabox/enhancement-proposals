# Clarification Log — OSAC-1610

## Status

- Rounds completed: 1
- Open gaps: 0
- Exit criteria met: Yes

## Round 1 — Scope & Configuration

### R1.Q1: Primary Goal

When a Cloud Infrastructure Admin configures a NetBox backend for OSAC, what measurable outcome defines success?

#### Answer

Tenant can allocate and deallocate hosts when OSAC uses NetBox as inventory. The admin infrastructure admin configures the backend and makes the prerequisites, then OSAC uses NetBox as inventory transparently.

#### Impact

Defines two personas: Cloud Infrastructure Admin (configuration, prerequisites) and Tenant User (transparent allocation/deallocation). No NetBox-specific UX exposed to tenant.

#### Decision (D1)

Tenant allocates/deallocates hosts transparently via NetBox as inventory backend. Cloud Infrastructure Admin configures backend + prerequisites; OSAC handles allocation internally.

---

### R1.Q2: In-Tree vs. Out-of-Tree

Is this in-tree, now (NetBox backend ships compiled in the operator, like BCM v1)? Or OSAC-3806 out-of-tree direction (gRPC sidecar) upfront?

#### Answer

Like BCM — in-tree now.

#### Impact

NetBox backend is a compiled-in `inventory.Client` implementation, self-registered in the operator binary. No gRPC sidecar in this milestone.

#### Decision (D2)

In-tree backend, like BCM. Compiled into the operator; structured for future OSAC-3806 out-of-tree extraction (keep types private, BMH creation extractable).

---

### R1.Q3: OS Provisioning Scope

OSAC provisioning (RHCOS, image selection) is entirely orthogonal to NetBox. NetBox supplies hardware inventory; power management is via Metal3/BMH; image comes from elsewhere. NetBox-specific OS config is out of scope. Confirm?

#### Answer

Exactly.

#### Impact

NetBox is purely an inventory backend — no OS provisioning concerns in this feature. BMH readiness and power are handled by existing Metal3 integration.

#### Decision (D3)

NetBox is inventory-only. OS provisioning, BMH readiness, and power management are orthogonal and handled by existing Metal3/BMH integration.

---

### R1.Q4: Configuration Mechanism

How does Cloud Infrastructure Admin configure NetBox backend — Helm values.yaml, API, or CRD?

#### Answer

Also right — Helm values + Enclave Wizard pipeline.

#### Impact

Installation dimension applies. Backend config flows through Helm values, processed by Enclave Wizard for Cloud Infrastructure Admin control plane setup.

#### Decision (D4)

Cloud Infrastructure Admin configures NetBox backend via Helm values (osac-installer), processed through Enclave Wizard pipeline.

---

### R1.Q5: NetBox Field Mapping Strategy

To design the NetBox field mapping: NetBox version, label source (tags vs. custom fields), and "assigned" marker. If unknowns, what's the decision path?

#### Answer

Version unknown — will ask Telefónica. Use NetBox native `status` field (active/staged/planned/failed) for free/assigned state where they exist; no custom `osac_claimed_by` duplication. Custom labels for selector filtering.

#### Impact

No custom-field duplication; reuse NetBox's native status semantics. Selector key=value mapping uses custom fields (design-time decision, not PRD-level).

#### Decision (D5)

Use NetBox native `status` field directly for free/assigned host state (active/staged/planned/failed). Custom labels for selector filtering. Telefónica version/schema to be confirmed during design; design document will specify field mapping.

---

## Summary

Five locked decisions:
- **D1:** Transparent allocation/deallocation for Tenant User; admin configuration for Cloud Infrastructure Admin.
- **D2:** In-tree backend like BCM.
- **D3:** NetBox inventory-only; OS provisioning orthogonal.
- **D4:** Helm values + Enclave Wizard for config.
- **D5:** Reuse NetBox native `status` for state; custom labels for selectors (design-time detail).

No remaining gaps blocking `/draft`.
