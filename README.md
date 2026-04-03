# FortiGate ADVPN (BGP over Loopback Preferred) - Ansible Renderer

This repository renders FortiGate CLI snippets for a multi-site ADVPN lab using **Ansible + Jinja2**.
It is an **offline config renderer** (templates are rendered on localhost), not a push/deploy framework.

> Scope: lab/reference automation. Validate output in your own environment before production rollout.

The design pattern is:
- ADVPN overlays over IPsec
- iBGP peering over tunnel interfaces **or** loopbacks (selectable, with **loopback preferred**)
- SD-WAN policy steering
- Hub/branch role-specific templates

---

## What is currently configured by default (source-of-truth snapshot)

The default inventory and vars currently describe:

- **2 hubs**: `dallas`, `chicago`
- **4 branches**: `phoenix`, `atlanta`, `denver`, `tampa`
- **BGP session mode**: `loopback` (default)
- **ASN**: `65152`
- **Tunnel matrix**: 8 branch→hub overlays (`network_id` 1-8)
- **Site IDs**:
  - `dallas: 1`
  - `chicago: 2`
  - `phoenix: 11`
  - `atlanta: 12`
  - `denver: 13`
  - `tampa: 14`

### Device defaults in this repo

| Inventory host | Role | `fgt_hostname` | `site_slug` |
|---|---|---|---|
| dallas | hub | Hub01 | dallas |
| chicago | hub | Hub02 | chicago |
| phoenix | branch | Branch01 | phoenix |
| atlanta | branch | atlanta-ga-branch2 | atlanta |
| denver | branch | Branch03 | denver |
| tampa | branch | tampa-fl-b4 | tampa-fl-b4 |

### Underlay defaults

- Global SSH defaults are set in `inventory.yml` (`ansible_connection: ssh`, `ansible_user: admin`, etc.).
- Hub WAN gateway metadata exists under `all.vars.hubs` (used by templates such as branch phase1 remote-gw mapping).
- Host WAN interfaces default to `port1`/`port2` in all included `host_vars/*` files.

---

## 2) Repository layout and what each module does

### Core playbooks

- `playbook.yml`
  - Main orchestration entrypoint.
  - Creates output directories.
  - Validates required vars (common + hub-specific + branch-specific).
  - Renders each template section.
  - Assembles final merged config in section order.
- `playbook-render.yml`
  - Thin wrapper that imports `playbook.yml`.

### Inventory and variable model

- `inventory.yml`
  - Device list, group membership, and Ansible login settings.
- `group_vars/all.yml`
  - Global ADVPN/IPsec/SD-WAN/BGP/route-map defaults used by all hosts.
  - Recommended structure is now nested under `advpn.*` (for example: `advpn.phase1`, `advpn.phase2`, `advpn.tunnels`, `advpn.sdwan`, `advpn.branch`, `advpn.interhub_ipsec`) so related overlay settings stay grouped.
- `group_vars/hub_devices.yml`
  - Hub role marker and hub-only defaults.
- `group_vars/branch_devices.yml`
  - Branch role marker and branch-only defaults.
- `host_vars/*.yml`
  - Per-site addressing and overrides (LAN, WAN mode/IP, hostnames, etc.).
  - ADVPN 2.0 style loopback separation:
    - `lo_hc` => SD-WAN/health-check loopback (`lo.hc`)
    - `lo_bgp` => BGP peering/update-source loopback (`lo.bgp`)

### Template modules (`templates/*.j2`)

- `musthaves.j2`
  - System baseline (hostname, admin timeout/password, RFC1918 objects, static blackhole routes).
- `interfaces.j2`
  - LAN/WAN interface config, loopbacks (`lo.hc` and `lo.bgp`), and DHCP server block (when LAN DHCP range is set).
- `advpn.j2`
  - Consolidated ADVPN template (hub + branch) used to render:
    - IPsec phase1-interface overlays
    - tunnel allowaccess/interface behavior
    - IPsec phase2 selectors
- `sdwan_hub.j2` / `sdwan_branch.j2`
  - SD-WAN zones/members/health-checks/services and firewall policies tied to SD-WAN traffic flows.
  - Includes loopback-mode control-plane policies for both `lo.hc` and `lo.bgp` (`vpnsdwan -> loopback`) so BGP-over-loopback sessions are permitted.
  - Supports per-service SD-WAN mode tuning (`manual`, `sla`, etc.), tie-break behavior, and minimum SLA member controls via vars.
- `bgp_hub.j2` / `bgp_branch.j2`
  - BGP policy and peering model:
    - `session_mode: loopback` (recommended/current default): loopback-based neighbor definitions with update-source from `lo.bgp`.
    - `session_mode: per_overlay` (legacy compatibility): per-overlay interface-neighbor style peering.
    - hubs: neighbor-groups + neighbor-ranges
    - branches: route-map driven neighbor handling and network advertisement
  - Router-ID is set from `lo_bgp` automatically in loopback mode.
- `community_lists.j2`
  - Hub community lists used by routing policy.
- `route_maps_hub.j2` / `route_maps_branch.j2`
  - Route-map policy for route tagging, preference, and fail handling.
- `hub_interhub_ipsec.j2`
  - Direct hub-to-hub IPsec link and policy.

### Utility scripts

- `scripts/host_vars_wizard.py`
  - Interactive/non-interactive helper to create a new `host_vars/<site>.yml` from an existing template.
- `scripts/add_spoke_wizard.py`
  - One-shot spoke onboarding helper that can:
    - generate `host_vars/<spoke>.yml` from a template
    - add the spoke to `inventory.yml` under `branch_devices`
    - insert a new `advpn.site_identifiers.<spoke>` entry in `group_vars/all.yml`

---

## Template/render order (actual playbook behavior)

### Always rendered

1. `01-baseline.conf` ← `templates/musthaves.j2`
2. `02-interfaces.conf` ← `templates/interfaces.j2`
3. `11-set-allowaccess.conf` ← `templates/port_allowaccess_reenable.j2`

### Hub-only rendered sections

3. `03-phase1.conf` ← `templates/hub_phase1.j2`
4. `04-tunnel-allowaccess.conf` ← `templates/hub_tunnel_allowaccess.j2`
5. `05-phase2.conf` ← `templates/hub_phase2.j2`
6. `06-community-lists.conf` ← `templates/community_lists.j2`
7. `07-route-maps.conf` ← `templates/route_maps_hub.j2`
8. `08-sdwan.conf` ← `templates/sdwan_hub.j2`
9. `09-bgp.conf` ← `templates/bgp_hub.j2`
10. `10-interhub-ipsec.conf` ← `templates/hub_interhub_ipsec.j2`

### Branch-only rendered sections

3. `03-phase1.conf` ← `templates/branch_phase1.j2`
4. `04-tunnel-allowaccess.conf` ← `templates/branch_tunnel_allowaccess.j2`
5. `05-phase2.conf` ← `templates/branch_phase2.j2`
6. `06-route-maps.conf` ← `templates/route_maps_branch.j2`
7. `07-sdwan.conf` ← `templates/sdwan_branch.j2`
8. `08-bgp.conf` ← `templates/bgp_branch.j2`

### Why `port_allowaccess_reenable.j2` is last

That template re-applies `allowaccess ping http https ssh snmp` to **physical `port*` interfaces only** (LAN/WAN), intentionally excluding loopback/tunnel interfaces.

---

## Repository layout

- `playbook.yml` - main renderer and variable normalization logic.
- `playbook-render.yml` - thin wrapper importing `playbook.yml`.
- `inventory.yml` - hosts, groups, SSH settings, and hub underlay metadata.
- `group_vars/all.yml` - global ADVPN/BGP/SD-WAN defaults in nested `advpn.*` structure.
- `group_vars/hub_devices.yml` - hub role marker and hub community-list defaults.
- `group_vars/branch_devices.yml` - branch role marker.
- `host_vars/*.yml` - site-specific interfaces, loopbacks, LAN/DHCP, overlay/hub extras.
- `templates/*.j2` - FortiGate CLI fragments rendered per role.
- `scripts/host_vars_wizard.py` - helper to clone and prompt through a `host_vars` template.

---

## Variable model (current design)

Primary defaults live in nested keys under `advpn`:

- `advpn.site_identifiers`
- `advpn.phase1`
- `advpn.phase2`
- `advpn.tunnels`
- `advpn.sdwan.branch`
- `advpn.sdwan.hub`
- `advpn.bgp`
- `advpn.branch.route_maps`
- `advpn.interhub_ipsec`

`playbook.yml` maps these into legacy/template variable names with `set_fact`, allowing compatibility with older flat keys where present.

### Derived behavior implemented in playbook

- Branch preferred route-maps are auto-derived from effective tunnel matrix (`advpn.tunnels` or per-branch `branch_tunnels`) with community format `<asn>:<network_id>`.
- `branch_bgp_route_maps` is derived from `advpn.branch.route_maps.fail` unless explicitly overridden.
- `site_id` is validated to be `1..254`; branches must be `>=3`; `dallas` is pinned to `1`; `chicago` pinned to `2`.

---

## Running the renderer

```bash
ansible-playbook -i inventory.yml playbook.yml
```

Useful checks:

```bash
ansible-inventory -i inventory.yml --graph
ansible-playbook -i inventory.yml playbook.yml --syntax-check
```

---

## Creating new site host vars

Interactive mode:

```bash
python3 scripts/host_vars_wizard.py
```

Non-interactive template/output:

```bash
python3 scripts/host_vars_wizard.py --template phoenix --output newsite
```

Behavior:
- Reads `host_vars/<template>.yml` as defaults.
- Prompts for every key path.
- Enter keeps default values.
- Writes `host_vars/<output>.yml`.

---


### Recommended next step as the repo grows: automate spoke onboarding

Yes—at this size, automating spoke onboarding is worth it.

Use the new helper to reduce missed steps when adding a branch:

```bash
python3 scripts/add_spoke_wizard.py \
  --name miami \
  --ansible-host 192.168.122.25 \
  --site-id 15 \
  --template phoenix \
  --site-name "miami, fl" \
  --lo-bgp-ip 10.250.0.15 \
  --lo-hc-ip 10.250.1.15
```

This command updates three places in one run:
1. `host_vars/miami.yml`
2. `inventory.yml` (`all.children.branch_devices.hosts.miami`)
3. `group_vars/all.yml` (`advpn.site_identifiers.miami`)

Tip: keep using `host_vars_wizard.py` when you want to answer every field interactively. Use `add_spoke_wizard.py` when you want faster, safer bulk onboarding.

---

## 7) Guardrails and validation

`playbook.yml` asserts required keys before rendering so invalid host definitions fail early.

- Loads an existing `host_vars/<template>.yml` file.
- Prompts for every key path recursively.
- Pressing Enter keeps each default.
- Writes `host_vars/<output>.yml`.

---

## Guardrails and consistency rules

- `host_vars/<name>.yml` filename must match inventory hostname.
- `device_role` must be `hub` or `branch`.
- Hub-only required keys (e.g., `hub_overlay_interfaces`, `interhub`, `hub_community_lists[...]`) are validated before rendering.
- Branch-only required keys (LAN subnet + DHCP ranges + loopbacks) are validated before rendering.
- Keep addressing data in `host_vars` authoritative; templates are intentionally thin.

