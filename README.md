# FortiGate ADVPN (BGP on Interface) - Ansible Renderer

This repository renders FortiGate ADVPN configuration snippets using Ansible + Jinja2.

The design here is **ADVPN with eBGP neighbors configured directly on tunnel interfaces** ("BGP on interface").

---

## What this project generates

Per device in `inventory.yml`, the playbook renders CLI snippets into `rendered/`:

- baseline / must-have settings
- interface IP and allowaccess settings
- ADVPN IPsec phase1 + phase2
- SD-WAN members/services
- BGP configuration (neighbor-group on hubs, per-neighbor interface binding on branches)
- hub community lists and route-maps
- branch route-maps
- hub inter-hub IPsec

Output files are named like:

- `rendered/<HOST>-baseline.conf`
- `rendered/<HOST>-phase1.conf`
- `rendered/<HOST>-phase2.conf`
- `rendered/<HOST>-sdwan.conf`
- `rendered/<HOST>-bgp.conf`

---

## Fixed issues (from previous audit)

The following errors were corrected:

1. **Broken template references in playbooks**
   - corrected baseline template path to `templates/musthaves.j2`
   - added missing hub templates:
     - `templates/hub_phase1.j2`
     - `templates/hub_tunnel_allowaccess.j2`
     - `templates/hub_phase2.j2`

2. **Group var filename mismatch**
   - renamed:
     - `group_vars/hubs.yml` -> `group_vars/hub_devices.yml`
     - `group_vars/branches.yml` -> `group_vars/branch_devices.yml`
   - now aligns with inventory groups `hub_devices` and `branch_devices`

3. **Host var filename mismatch with inventory hostnames**
   - renamed host var files to match case-sensitive inventory names:
     - `Hub01.yml`, `Hub02.yml`, `Kingsgate.yml`, `Frisco.yml`

4. **Missing host vars for `Abilene`**
   - added `host_vars/Abilene.yml`

5. **Incorrect YAML nesting in `group_vars/all.yml`**
   - moved these to correct top-level keys:
     - `hub_sdwan_inet_service`
     - `interhub_ipsec`
     - `branch_route_maps`
     - `branch_bgp_route_maps`

6. **Undefined vars in branch phase2 template**
   - updated `templates/branch_phase2.j2` to use `phase2.*` structure

7. **Undefined BGP vars in branch BGP template**
   - added required keys under `bgp` in `group_vars/all.yml`

8. **Route-map templates not rendered**
   - added playbook tasks for:
     - `templates/route_maps_hub.j2`
     - `templates/route_maps_branch.j2`

9. **`rendered/` directory assumed to exist**
   - added a `pre_tasks` step to create `rendered/` on localhost

10. **Duplicate playbook drift risk**
   - `playbook-render.yml` now imports `playbook.yml` to keep a single source of truth

---

## Inventory and variable model

### Inventory groups

- `hub_devices`
- `branch_devices`

### Variable files

- Global: `group_vars/all.yml`
- Hubs role: `group_vars/hub_devices.yml`
- Branch role: `group_vars/branch_devices.yml`
- Per-host: `host_vars/<InventoryHost>.yml`

---

## Run

```bash
ansible-playbook -i inventory.yml playbook.yml
```

Optional dry checks:

```bash
ansible-inventory -i inventory.yml --graph
ansible-playbook -i inventory.yml playbook.yml --syntax-check
```

---

## Notes for BGP on interface design

- Branch BGP neighbors are rendered per ADVPN tunnel and bound with `set interface "<tunnel_name>"`.
- Hub BGP uses neighbor-groups + neighbor-ranges tied to overlay prefixes.
- Route-maps and community-lists are rendered to support route-tag/community policy per tunnel/network-id.

