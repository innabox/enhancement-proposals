---
title: bmaas-networking-ui
authors:
  - lberkovi@redhat.com
creation-date: 2026-09-07
last-updated: 2026-09-07
tracking-link:
  - https://redhat.atlassian.net/browse/OSAC-1437
prd: "prd.md"
see-also:
  - "/enhancements/OSAC-1437-bmaas-networking/design.md"
  - "/enhancements/OSAC-1433-unified-networking/ui-design.md"
  - "/enhancements/OSAC-1433-default-networking"
replaces:
superseded-by:
---

# BMaaS Networking — UI Design Addendum

## Summary

Extends the accepted backend design in [design.md](design.md) with the remaining `osac-ui`
work for OSAC-1437: a **Networking** step in the BareMetalInstance catalog provisioning
wizard (network attachments with physical interface mapping, default-networking mode, and
required External IP pool selection for auto external access), a Review-step summary of
those choices, and read-only networking visibility on the instance detail page. Existing
BareMetalInstance provisioning (catalog → general → configuration → review) is unchanged
except for inserting the new step and extending the create payload. Cloud Provider Admin
ExternalIPPool management and tenant External IP list/create flows are covered by
[OSAC-1433 unified networking ui-design](/enhancements/OSAC-1433-unified-networking/ui-design.md)
and are not repeated here.

## Proposal

### Tenant User and Admin

#### BareMetalInstance Provisioning Wizard — Networking Step

The bare metal adapter currently returns `NetworkingStep: () => null` and omits
`networkAttachments` / `autoExternalIpAttachment` from the create payload
[Codebase: `catalogProvision/wizard/adapters/bareMetalInstanceAdapter.ts`]. This design
adds a real step between **Configuration** and **Review**:

- Update `BARE_METAL_WIZARD_STEPS` to
  `catalog → general → configuration → networking → review`
  [Codebase: `catalogProvision/wizard/stepIds.ts`].
- New component **`BareMetalNetworkingStep`**
  (`catalogProvision/wizard/adapters/bareMetalInstance/BareMetalNetworkingStep.tsx`),
  Formik fields under `spec.networking` in wizard values, step-scoped Yup validation in
  `schemas.ts`, and payload mapping in `payload.ts`.

**Network attachments**

- **Use tenant default network** checkbox — checked by default. When checked, the UI hides
  the attachment editor and the create payload omits `networkAttachments`; the backend
  attaches the tenant's default subnet and security group and selects the host type's
  default fabric interface [PRD: FR-5].
- When unchecked, show a repeatable attachment editor (`FieldArray`, same interaction
  pattern as `ClusterNodeSetsArrayField`). Each row has:
  - **Physical interface** — required when more than one row exists; options from the
    resolved `HostType.interfaces` list, excluding interfaces with role `lifecycle`
    [design.md: Interface Role Convention].
  - **Virtual network** — `SelectField`, READY filter (`VIRTUAL_NETWORK_READY_LIST_FILTER`),
    same as `VmNetworkingStep`.
  - **Subnet** — `SelectField`, filtered by the row's virtual network.
  - **Security groups** — `MultiSelectField`, filtered by the row's virtual network.
  - **Primary (default gateway)** — checkbox; exactly one row must be primary when the row
    count is greater than one [PRD: FR-4].
- Add/remove row actions; at least one row when custom mode is enabled.
- Option labels for physical interfaces include role and description, e.g.
  `data-0 (fabric — 100GbE fabric interface)` [PRD: FR-2].
- Client-side validation before Next/Create: no duplicate interfaces across rows; all subnets
  belong to the same virtual network; row count does not exceed attachable interfaces;
  when row count > 1, every row has an explicit interface and exactly one primary
  [PRD: FR-3, FR-4].
- Changing a row's virtual network clears that row's subnet and security group selections
  (same dependent-reset behavior as `VmNetworkingStep`).

**HostType resolution**

- Resolve the host type ID from the selected catalog item's template `host_type` field
  [design.md: How BMaaS Uses HostType].
- Fetch the host type via existing `useHostType(id)` (`api/v1/host-types.ts`).
- If the host type cannot be loaded, or it has no tenant-attachable interfaces, show an
  inline error with **Retry** and block wizard progression on the networking step.

**External access**

- **Attach external IP at creation** checkbox maps to `spec.auto_external_ip_attachment`.
  Helper text states that the system auto-creates an ExternalIP and ExternalIPAttachment
  bound to the server's primary attachment, and that auto-created resources are deleted
  when the instance is deleted [PRD: FR-6, FR-11].
- When checked, show a required **External IP pool** `SelectField`. Options come from
  `useExternalIPPools()` with label format
  ``${name} (${available} available)`` — same as `AttachExternalIpModal`
  [Codebase: `vm/DetailsPage/AttachExternalIpModal.tsx`].
- When unchecked, hide the pool field and omit `autoExternalIpAttachment` from the payload.
- If no pools are available, show the same warning alert as the VM attach modal and block
  Next/Create while external access is enabled.

**Backend prerequisite — pool on create**

The current `BareMetalInstanceSpec` proto exposes only `bool auto_external_ip_attachment`;
the backend auto-selects a READY pool with the most available capacity when the flag is
set [PRD: FR-6]. The UI requires an optional immutable `external_ip_pool` reference on
`BareMetalInstanceSpec` so the tenant's pool choice is honored at create time
[User]. Until that field lands in `@osac/types`, pool selection in the wizard is blocked;
implementing checkbox-only auto-select without pool choice is out of scope for this design.

**Catalog overlay**

When the catalog item defines `field_definitions` wire paths for networking fields, apply
the existing overlay pattern (`catalogOverlay.ts`): label, editable, default, and required
behavior for:

- `spec.network_attachments` (custom-mode toggle and attachment rows)
- `spec.auto_external_ip_attachment`
- `spec.external_ip_pool` (once added to proto)

**Review step**

Extend `BareMetalReviewStep` to summarize:

- Default networking vs custom attachments (interface, virtual network, subnet, security
  groups, primary per row).
- External access enabled/disabled and selected pool name when enabled.

**Create payload mapping**

When custom networking is enabled, map each wizard row to:

```text
networkAttachments[]: { subnet: { id }, securityGroups: [{ id }], interface, primary }
```

When external access is enabled:

```text
autoExternalIpAttachment: true
externalIpPool: { id }   // once proto field exists
```

### Tenant User and Admin — Instance Detail (read-only)

Add a **Networking** tab on the BareMetalInstance detail page (mirror `VmNetworkingTab`):

- Table columns: **Interface**, **Virtual network**, **Subnet**, **Security groups**,
  **Internal IP** (from `status.networkAttachmentStatuses[].ipAddress`), **Primary**.
- When the instance has auto-provisioned external access, show the allocated **External IP**
  address and an indicator that the IP and attachment were auto-created (labels described in
  [design.md](design.md)).
- Resolve virtual network and subnet display names via the same networking list hooks used
  on the VM detail page (`useVmDetailsDisplay` pattern).

No new tenant routes; detail changes live under the existing `/bare-metal/:id` page.

## Failure Handling

| Scenario | UI behavior |
|---|---|
| HostType Get failure on networking step | Inline danger alert with **Retry**; **Next** disabled. |
| HostType has no tenant-attachable interfaces | Inline warning; custom attachments blocked; default-networking-only path still allowed if backend defaults apply. |
| Virtual network / subnet / security group list failure | Inline danger alert with **Retry** (same pattern as `VmNetworkingStep`). |
| Duplicate interface, missing interface on multi-row, or multiple primaries | Yup field errors on the networking step before **Next** / **Create**. |
| External access enabled but no pools available | Warning alert; **Next** and **Create** disabled while the checkbox remains checked. |
| External IP pool list load failure | Inline danger alert with **Retry**; pool select disabled. |
| Create: pool exhausted (`RESOURCE_EXHAUSTED` / `FAILED_PRECONDITION`) | Server error shown at wizard **Create**; user remains on Review with alert. |
| Create: invalid interface or default networking unavailable | Server validation message shown verbatim at **Create**. |
| Detail: networking status not yet populated | Internal IP column shows `—` until `networkAttachmentStatuses` is populated [PRD: FR-8]. |
| Any other List/Get failure | Existing `QueryErrorState` / inline retry handling. |

## Implementation details

- **Wizard adapter** (`bareMetalInstanceAdapter.ts`): replace `NetworkingStep: () => null`
  with `BareMetalNetworkingStep`; extend `getStepValidationSchema` and
  `buildCreatePayload` for the networking step.
- **Wizard values** (`bareMetalInstance/fields.ts`): add `spec.networking`:
  `{ useDefaults, attachments[], attachExternalIp, externalIpPool }` with
  `createEmptyBareMetalInstanceValues()` defaults (`useDefaults: true`,
  `attachExternalIp: false`, one empty attachment row for custom mode).
- **Validation** (`bareMetalInstance/schemas.ts`): networking-step Yup schema only (per-step
  scoping convention documented in existing `schemas.ts` header comment).
- **Payload** (`bareMetalInstance/payload.ts`): map wizard values to
  `networkAttachments`, `autoExternalIpAttachment`, and `externalIpPool` (gated on proto).
- **Review** (`BareMetalReviewStep.tsx`): networking and external-access summary groups.
- **Detail** (new `BareMetalNetworkingTab.tsx`, wired from `BareMetalDetailsPage.tsx`):
  read-only table from `spec.networkAttachments` + `status.networkAttachmentStatuses`.
- **Hooks reused (no new API surface required for networking resources):**
  `useHostType`, `useVirtualNetworks`, `useSubnets`, `useSecurityGroups`,
  `useExternalIPPools` from `api/v1/host-types.ts`, `api/v1/networking.ts`, and
  `api/v1/external-ip.ts`.
- **Backend dependency:** add optional immutable `external_ip_pool` on
  `BareMetalInstanceSpec` in fulfillment-service proto and regenerate `@osac/types` before
  shipping pool selection.
- **Test fixtures:** extend `createMockConnectTransport.ts` with HostType interfaces,
  networking resources, and ExternalIPPools for bare metal wizard tests.
- **Tests** (Vitest + RTL, mock Connect transport — no fetch mocks):
  - `BareMetalNetworkingStep`: default vs custom payload, multi-row primary validation,
    interface filtering, external IP + pool required when enabled, HostType error blocks
    progression.
  - `CatalogProvisionWizard.test.tsx`: bare metal wizard includes networking step and
    builds expected create payload.
  - `BareMetalReviewStep`: renders networking summary.
  - `BareMetalNetworkingTab`: renders attachment rows and status IPs.
