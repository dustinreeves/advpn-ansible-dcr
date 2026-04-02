# FortiGate ADVPN (BGP over Loopback Preferred) - Ansible Renderer
Be advised this is for labbing only, this is mostly chatgpt ai slop, but its pretty good at writing ansible crap. but YMMV.

This repository renders FortiGate CLI configuration snippets for a multi-site ADVPN topology using **Ansible + Jinja2**.

The design pattern is:
- ADVPN overlays over IPsec
- eBGP peering over tunnel interfaces **or** loopbacks (selectable, with **loopback preferred**)
- SD-WAN policy steering
- Hub/branch role-specific templates

---

## 1) How the whole workflow works

1. Inventory defines devices and groups (`hub_devices`, `branch_devices`).
2. Ansible loads variable layers in this order:
   - `group_vars/all.yml` (global defaults)
   - `group_vars/<group>.yml` (role defaults)
   - `host_vars/<host>.yml` (site-specific overrides)
3. `playbook.yml` validates required inputs in `pre_tasks`.
4. `playbook.yml` renders templates in deterministic numeric order (`01-*`, `02-*`, ...).
5. Ansible assembles rendered sections into a single full config per host in `rendered/`.

The output is rendered locally (via `delegate_to: localhost`), so this repo can be used as an offline config generator.

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
- `hub_phase1.j2` / `branch_phase1.j2`
  - IPsec phase1-interface for ADVPN overlays.
- `hub_phase2.j2` / `branch_phase2.j2`
  - IPsec phase2 selectors for each overlay.
- `hub_tunnel_allowaccess.j2` / `branch_tunnel_allowaccess.j2`
  - Tunnel interface allowaccess behavior.
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
  - Interactive/non-interactive helper to create new `host_vars/<site>.yml` from an existing template.

---

## 3) Render sequence (per host)

The renderer writes numbered sections under `rendered/<normalized_hostname>/`:

1. `01-baseline.conf`
2. `02-interfaces.conf`
3. `03-phase1.conf`
4. `04-tunnel-allowaccess.conf`
5. `05-phase2.conf`
6. `06-community-lists.conf` (hub) or `06-route-maps.conf` (branch)
7. `07-route-maps.conf` (hub) or `07-sdwan.conf` (branch)
8. `08-sdwan.conf` (hub) or `08-bgp.conf` (branch)
9. `09-bgp.conf` (hub)
10. `10-interhub-ipsec.conf` (hub)

Then Ansible assembles all numbered files into:

- `rendered/<normalized_hostname>-full-<timestamp>.conf`

---

## Overlay variable layout recommendation

For maintainability, keep overlay values grouped by function instead of top-level flat keys:

- `advpn.phase1` => IKE/phase1 profile defaults.
- `advpn.phase2` => phase2 selectors and timers.
- `advpn.tunnels` => overlay matrix (`name`, hub, WAN mapping, `network_id`).
- `advpn.sdwan.branch` and `advpn.sdwan.hub` => role-specific SD-WAN behavior.
- `advpn.branch` => branch-only route-map and BGP route-map naming.
- `advpn.interhub_ipsec` => hub interconnect profile.
- `advpn.bgp.session_mode` => BGP peering method: `loopback` (current default/recommended) or `per_overlay` (legacy compatibility mode).

`playbook.yml` normalizes these nested keys back into the template variables used throughout the repo. This also keeps backward compatibility with older flat variable names while encouraging the cleaner nested model.
To avoid double maintenance, branch `preferable` route-maps are auto-derived from `advpn.tunnels` (community format: `<bgp.asn>:<network_id>`) and `branch_bgp_route_maps` is derived from `advpn.branch.route_maps.fail` when not explicitly provided.

---

## 4) Current default topology/profile in this repo

- Hubs
  - `dallas` => `fgt_hostname: Hub01`
  - `chicago` => `fgt_hostname: Hub02`
- Branches
  - `phoenix` => `fgt_hostname: Branch01`
  - `atlanta` => `fgt_hostname: Branch02`
  - `denver` => `fgt_hostname: Branch03`
- WAN interfaces default to DHCP mode when no static WAN IP is defined in host vars.
- LAN and DHCP pools are defined per site in host vars.
- `lo.hc` is reserved for health-check use.
- `lo.bgp` is the preferred control-plane/BGP loopback and is used for BGP peering, update-source, and router-id.

---

## 5) How to run

```bash
ansible-playbook -i inventory.yml playbook.yml
```

Optional checks:

```bash
ansible-inventory -i inventory.yml --graph
ansible-playbook -i inventory.yml playbook.yml --syntax-check
```

---

## 6) Creating/updating site host vars

Interactive mode:

```bash
python3 scripts/host_vars_wizard.py
```

Non-interactive template/output selection:

```bash
python3 scripts/host_vars_wizard.py --template phoenix --output newsite
```

Behavior:
- Reads `host_vars/<template>.yml` as defaults.
- Prompts for every key path.
- Enter keeps default values.
- Writes `host_vars/<output>.yml`.

---

## 7) Guardrails and validation

`playbook.yml` asserts required keys before rendering so invalid host definitions fail early.

Important conventions:
- `host_vars/<name>.yml` filename must match inventory hostname exactly.
- Role-specific fields must exist for the matching device role.
- Keep addressing inputs in host vars authoritative; templates are designed to render directly from those values.

---

## 8) Multi-hub / multi-overlay planning checklist alignment

This repo now directly supports the following recommended ADVPN controls (loopback-first):

- BGP loopback peering with `lo.bgp` update-source and router-id on both hubs and branches.
- Default BGP session mode set to loopback in `group_vars/all.yml` (`advpn.bgp.session_mode: loopback`).
- Branch SD-WAN health-check source defaults to branch `lo.bgp` (override per check if needed).
- Optional SD-WAN health-check `detect_mode` (for example `remote`) on branch and hub.
- Hub SD-WAN route services configurable from vars (including manual mode + FIB tie-break).
- Branch SD-WAN services configurable for SLA-driven pathing (`mode`, `tie_break`, `minimum_sla_meet_members`).
- Explicit branch policy for `lo.bgp -> vpnsdwan` in addition to `vpnsdwan -> lo.bgp`.

### Recommended operating mode

For new deployments, use BGP-over-loopback as the standard pattern:

- Keep `advpn.bgp.session_mode: loopback` (default).
- Assign unique `/32` loopback addresses per site for `lo.bgp`.
- Keep SD-WAN and policy controls allowing both directions between overlay zone(s) and loopbacks.
- Treat `per_overlay` mode as migration/compatibility fallback only.

Items still operator-defined by design (must be planned in your inventory/vars):

- Site ID numbering conventions (for example 3-254) and how they map into your own naming/address plan.
- Exact BGP peering subnet plan and per-site /32 allocations.
- Overlay count/topology design decisions between hubs and spokes.
