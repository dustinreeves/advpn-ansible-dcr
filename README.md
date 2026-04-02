# FortiGate ADVPN (BGP on Interface) - Ansible Renderer

This repository renders FortiGate CLI configuration snippets for a multi-site ADVPN topology using **Ansible + Jinja2**.

The design pattern is:
- ADVPN overlays over IPsec
- eBGP peering over tunnel interfaces
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
- `group_vars/hub_devices.yml`
  - Hub role marker and hub-only defaults.
- `group_vars/branch_devices.yml`
  - Branch role marker and branch-only defaults.
- `host_vars/*.yml`
  - Per-site addressing and overrides (LAN, WAN mode/IP, loopbacks, hostnames, etc.).

### Template modules (`templates/*.j2`)

- `musthaves.j2`
  - System baseline (hostname, admin timeout/password, RFC1918 objects, static blackhole routes).
- `interfaces.j2`
  - LAN/WAN interface config, branch `lo.hc` loopback, and DHCP server block (when LAN DHCP range is set).
- `hub_phase1.j2` / `branch_phase1.j2`
  - IPsec phase1-interface for ADVPN overlays.
- `hub_phase2.j2` / `branch_phase2.j2`
  - IPsec phase2 selectors for each overlay.
- `hub_tunnel_allowaccess.j2` / `branch_tunnel_allowaccess.j2`
  - Tunnel interface allowaccess behavior.
- `sdwan_hub.j2` / `sdwan_branch.j2`
  - SD-WAN zones/members/health-checks/services and firewall policies tied to SD-WAN traffic flows.
- `bgp_hub.j2` / `bgp_branch.j2`
  - BGP policy and peering model:
    - hubs: neighbor-groups + neighbor-ranges
    - branches: per-neighbor interface binding, network advertisement
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
- Branch `lo.hc` loopback is defined per branch and can be advertised in branch BGP.

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
