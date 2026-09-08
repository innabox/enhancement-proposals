---

## title: bmaas-networking-ui authors:   - [lberkovi@redhat.com](mailto:lberkovi@redhat.com) creation-date: 2026-09-07 last-updated: 2026-09-08 tracking-link:   - [https://redhat.atlassian.net/browse/OSAC-1437](https://redhat.atlassian.net/browse/OSAC-1437) prd: "prd.md" see-also:   - "/enhancements/OSAC-1437-bmaas-networking/design.md"   - "/enhancements/OSAC-1433-unified-networking/ui-design.md"   - "/enhancements/OSAC-1433-default-networking" replaces: superseded-by:

# BMaaS Networking — UI Design Addendum

## Summary

Extends the accepted backend design in [design.md](design.md) with the remaining `osac-ui` work for OSAC-1437: a **Networking** step in the BareMetalInstance catalog provisioning wizard (network attachments with physical interface mapping, default-networking mode, and auto external access), a Review-step summary of those choices, and read-only networking visibility on the instance detail page. Existing BareMetalInstance provisioning (catalog → general → configuration → review) is unchanged except for inserting the new step and extending the create payload. Cloud Provider Admin ExternalIPPool management and tenant External IP list/create flows are covered by [OSAC-1433 unified networking ui-design](/enhancements/OSAC-1433-unified-networking/ui-design.md) and are not repeated here.

## Proposal



### Tenant User and Admin



#### BareMetalInstance Provisioning Wizard — Networking Step

The bare metal adapter currently returns `NetworkingStep: () => null` and omits `networkAttachments` / `autoExternalIpAttachment` from the create payload [Codebase: `catalogProvision/wizard/adapters/bareMetalInstanceAdapter.ts`]. This design adds a real step between **Configuration** and **Review**:

- Update `BARE_METAL_WIZARD_STEPS` to `catalog → general → configuration → networking → review` [Codebase: `catalogProvision/wizard/stepIds.ts`].
- New component `BareMetalNetworkingStep` (`catalogProvision/wizard/adapters/bareMetalInstance/BareMetalNetworkingStep.tsx`), Formik fields under `spec.networking` in wizard values, step-scoped Yup validation in `schemas.ts`, and payload mapping in `payload.ts`.

**Network attachments**

- **Use tenant default network** checkbox — checked by default. When checked, the UI hides the attachment editor and the create payload omits `networkAttachments` entirely; the backend applies tenant default networking (see [Default Networking PRD](/enhancements/OSAC-1433-default-networking)) [PRD: FR-5].
- When unchecked, show a repeatable attachment editor (`FieldArray`, same interaction pattern as `ClusterNodeSetsArrayField`). Each row has:
  - **Physical interface** — required when more than one row exists; options from the resolved `HostType.interfaces` list, excluding interfaces with role `lifecycle` [design.md: Interface Role Convention].
  - **Virtual network** — `SelectField`, READY filter (`VIRTUAL_NETWORK_READY_LIST_FILTER`), same as `VmNetworkingStep`.
  - **Subnet** — `SelectField`, filtered by the row's virtual network.
  - **Security groups** — `MultiSelectField`, filtered by the row's virtual network.
  - **Primary (default gateway)** — checkbox; exactly one row must be primary when the row count is greater than one [PRD: FR-4].
- Add/remove row actions; at least one row when custom mode is enabled.
- Option labels for physical interfaces include role and description, e.g. `data-0 (fabric — 100GbE fabric interface)` [PRD: FR-2].
- Client-side validation before Next/Create: no duplicate interfaces across rows; all subnets belong to the same virtual network; row count does not exceed attachable interfaces; when row count > 1, every row has an explicit interface and exactly one primary [PRD: FR-3, FR-4].
- Changing a row's virtual network clears that row's subnet and security group selections (same dependent-reset behavior as `VmNetworkingStep`).

**Validation strategy**

- **Client-side validation (fast feedback):** Add networking step case to existing `buildBareMetalInstanceStepSchema()` for duplicate interfaces, missing primary, subnet mismatch. Follows the same per-step Yup pattern used by general/configuration steps.
- **Backend validation (authoritative):** fulfillment-service performs authoritative validation ([design.md](design.md) lines 228-236). When validation fails, the wizard's existing `provisionError` mechanism displays the server error message verbatim on the Review step.
- **Resource loading errors:** HostType/VN/Subnet/SG loading failures use the same inline danger Alert + Retry button pattern as `VmNetworkingStep` (no new error handling code required).
- **No custom error handling:** The UI does not retry, interpret, or special-case backend validation errors—existing wizard infrastructure surfaces them directly to the user.

**HostType resolution**

- The catalog item's template `host_type` field references the HostType resource [design.md: How BMaaS Uses HostType].
- **UI display only:** Fetch the HostType via `useHostType(id)` (`api/v1/host-types.ts`) to populate the physical interface dropdown with available interfaces.
- **Authoritative resolution:** HostType resolution and validation happen at the backend during BMI creation.
- If the HostType cannot be loaded by the UI, show inline danger Alert with **Retry** button (same pattern as `VmNetworkingStep` resource loading errors). User can still proceed with default networking mode (custom attachments disabled only).

**External access**

- **Attach external IP at creation** checkbox maps to `spec.auto_external_ip_attachment`. Helper text states that the system auto-creates an ExternalIP and ExternalIPAttachment bound to the server's primary attachment, and that auto-created resources are deleted when the instance is deleted [PRD: FR-6, FR-11].
- When unchecked, omit `autoExternalIpAttachment` from the payload.
- **Backend pool selection:** The backend auto-selects an ExternalIPPool (READY, most available capacity, matching IP family) when `auto_external_ip_attachment == true` ([design.md](design.md) line 237). The UI does not expose pool selection.
- **Atomic creation:** If auto External IP is enabled and pool allocation fails, the entire BMI create fails atomically—no partial resources are created. The backend returns an error (e.g., `RESOURCE_EXHAUSTED` for pool exhaustion), which the wizard's existing `provisionError` mechanism displays on the Review step.

**Catalog overlay**

When the catalog item defines `field_definitions` wire paths for networking fields, apply the existing overlay pattern (`catalogOverlay.ts`): label, editable, default, and required behavior for:

- `spec.network_attachments` (custom-mode toggle and attachment rows)
- `spec.auto_external_ip_attachment`

**Review step**

Extend `BareMetalReviewStep` to summarize:

- Default networking vs custom attachments (interface, virtual network, subnet, security groups, primary per row).
- External access enabled/disabled.

**Create payload mapping**

When custom networking is enabled, map each wizard row to:

```text
networkAttachments[]: { subnet: { id }, securityGroups: [{ id }], interface, primary }
```

When external access is enabled:

```text
autoExternalIpAttachment: true
```



### Tenant User and Admin — Instance Detail (read-only)

Add a **Networking** tab on the BareMetalInstance detail page (mirror `VmNetworkingTab`):

- Table columns: **Interface**, **Virtual network**, **Subnet**, **Security groups**, **Internal IP** (from `status.networkAttachmentStatuses[].ipAddress`), **Primary**.
- When the instance has auto-provisioned external access, show the allocated **External IP** address and an indicator that the IP and attachment were auto-created. Data path:
  - Query `ExternalIPAttachments` filtered by `target.id == bareMetalInstanceId`
  - Query `ExternalIPs` filtered by label `osac.openshift.io/auto-created-for: <id>`
  - Display the IP address and show "Auto-provisioned" indicator based on the `osac.openshift.io/auto-created: "true"` label
- Resolve virtual network and subnet display names via the same networking list hooks used on the VM detail page (`useVmDetailsDisplay` pattern).

No new tenant routes; detail changes live under the existing `/bare-metal/:id` page.

## Failure Handling

The BMaaS networking feature uses existing wizard error handling patterns. The table below maps each scenario to the corresponding pattern:


| Scenario                                                                     | UI behavior                                                                                                         | Pattern                                                     |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| HostType Get failure on networking step                                      | Inline danger alert with **Retry**; custom attachments disabled (default mode still available).                     | Resource loading error pattern (VmNetworkingStep)           |
| HostType has no tenant-attachable interfaces                                 | Custom attachments disabled; user can proceed with default networking mode.                                         | Resource loading error pattern                              |
| Virtual network / subnet / security group list failure                       | Inline danger alert with **Retry** (same pattern as `VmNetworkingStep`).                                            | Resource loading error pattern (VmNetworkingStep)           |
| Duplicate interface, missing interface on multi-row, or multiple primaries   | Yup field errors on the networking step before **Next** / **Create**.                                               | Client-side validation (per-step Yup schema)                |
| Create: pool exhausted, invalid interface, or default networking unavailable | Server error message displayed verbatim on Review step via existing `provisionError` Alert. User remains on Review. | Backend validation error pattern (provisionError mechanism) |
| Detail: networking status not yet populated                                  | Internal IP column shows `—` until `networkAttachmentStatuses` is populated [PRD: FR-8].                            | Status field initialization                                 |
| Any other List/Get failure                                                   | Existing `QueryErrorState` / inline retry handling.                                                                 | Standard query error handling                               |




## Implementation details

- **Wizard adapter** (`bareMetalInstanceAdapter.ts`): replace `NetworkingStep: () => null` with `BareMetalNetworkingStep`; extend `getStepValidationSchema` and `buildCreatePayload` for the networking step.
- **Wizard values** (`bareMetalInstance/fields.ts`): add `spec.networking`: `{ useDefaults, attachments[], attachExternalIp }` with `createEmptyBareMetalInstanceValues()` defaults (`useDefaults: true`, `attachExternalIp: false`, one empty attachment row for custom mode).
- **Validation** (`bareMetalInstance/schemas.ts`): networking-step Yup schema only (per-step scoping convention documented in existing `schemas.ts` header comment).
- **Payload** (`bareMetalInstance/payload.ts`): map wizard values to `networkAttachments` and `autoExternalIpAttachment`.
- **Review** (`BareMetalReviewStep.tsx`): networking and external-access summary (enabled/disabled only, no pool name).
- **Detail** (new `BareMetalNetworkingTab.tsx`, wired from `BareMetalDetailsPage.tsx`): read-only table from `spec.networkAttachments` + `status.networkAttachmentStatuses`.
- **Hooks reused (no new API surface required for networking resources):** `useHostType`, `useVirtualNetworks`, `useSubnets`, `useSecurityGroups` from `api/v1/host-types.ts` and `api/v1/networking.ts`. External IP hooks (`useExternalIPs`, `useExternalIPAttachments`) are used only on the detail page for displaying auto-created resources.
- **Test fixtures:** extend `createMockConnectTransport.ts` with HostType interfaces and networking resources for bare metal wizard tests.
- **Tests** (Vitest + RTL, mock Connect transport — no fetch mocks):
  - `BareMetalNetworkingStep`: default vs custom payload, multi-row primary validation, interface filtering, external IP checkbox behavior, HostType error handling.
  - `CatalogProvisionWizard.test.tsx`: bare metal wizard includes networking step and builds expected create payload.
  - `BareMetalReviewStep`: renders networking summary.
  - `BareMetalNetworkingTab`: renders attachment rows and status IPs.

