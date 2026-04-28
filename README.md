# FortiGate ADVPN Ansible Renderer (Lab Defaults Documented)

This repository renders FortiGate CLI snippets for a multi-site ADVPN lab using **Ansible + Jinja2**.
It is an **offline config renderer** (templates are rendered on localhost), not a push/deploy framework.

> Lab note: defaults in this repo are intentionally opinionated and should be reviewed before production use.

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
- **Important**: older examples that used branch site IDs `3/4/5` are stale for this repo snapshot; current branch defaults are `11/12/13/14`.

### Device defaults in this repo

| Inventory host | Role | `fgt_hostname` | `site_slug` |
|---|---|---|---|
| dallas | hub | Hub01 | dallas |
| chicago | hub | Hub02 | chicago |
| phoenix | branch | phoenix-az-branch1 | phoenix-az-branch1 |
| atlanta | branch | atlanta-ga-branch2 | atlanta-ga-branch2 |
| denver | branch | denver-co-branch3 | denver-co-branch3 |
| tampa | branch | tampa-fl-branch4 | tampa-fl-branch4 |

### Naming convention defaults

- Branch host identity now follows `city-state-branch#` for both `fgt_hostname` and `site_slug`.

### Underlay defaults

- Global SSH defaults are set in `inventory.yml` (`ansible_connection: ssh`, `ansible_user: admin`, etc.).
- Hub WAN gateway metadata exists under `all.vars.hubs` (used by templates such as branch phase1 remote-gw mapping).
- Host WAN interfaces default to `port1`/`port2` in all included `host_vars/*` files.

---

## How rendering works

1. Inventory groups hosts into `hub_devices` and `branch_devices`.
2. Vars are loaded with standard Ansible precedence (global → group → host).
3. `playbook.yml` validates required values in `pre_tasks`.
4. `playbook.yml` normalizes nested `advpn.*` values into template-friendly variables.
5. Templates are rendered in deterministic numbered order to `rendered/<normalized_hostname>/`.
6. All numbered sections are assembled into one full config:
   - `rendered/<normalized_hostname>-full-<timestamp>.conf`

Rendering is delegated to localhost, so you can run this without FortiGate API access.

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

- Loads an existing `host_vars/<template>.yml` file.
- Prompts for every key path recursively.
- Pressing Enter keeps each default.
- Writes `host_vars/<output>.yml`.

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

## Guardrails and consistency rules

- `host_vars/<name>.yml` filename must match inventory hostname.
- `device_role` must be `hub` or `branch`.
- Hub-only required keys (e.g., `hub_overlay_interfaces`, `interhub`, `hub_community_lists[...]`) are validated before rendering.
- Branch-only required keys (LAN subnet + DHCP ranges + loopbacks) are validated before rendering.
- Keep addressing data in `host_vars` authoritative; templates are intentionally thin.

---

## Web front end (dashboard UI + render in browser)

You can launch a local web UI that lets you:

- pick a host
- edit variables in a **dark-mode dashboard** with section cards, network tabs, and preview panel
- choose render mode:
  - **Ansible (exact)**: runs playbook like before
  - **Browser Jinja (experimental)**: renders templates in-browser using Nunjucks
- use **Preview Configuration** to generate output and update the right-side preview panel

Run:

```bash
python3 scripts/web_frontend.py
```

The server now serves frontend assets from `webui/index.html`, `webui/app.css`, and `webui/app.js`.

Then open:

```text
http://127.0.0.1:8080
```

Notes:

- The UI does **not** overwrite files unless you copy/paste changes back yourself.
- In **Ansible (exact)** mode, it calls `ansible-playbook -i inventory.yml playbook.yml --limit <host>` with temporary extra vars.
- In **Browser Jinja (experimental)** mode, templates are rendered in the browser (no Ansible run), which is useful for GitHub Pages/static hosting scenarios.
- Browser mode may not exactly match playbook output if templates rely on facts derived inside Ansible tasks.

## GitHub Pages compatibility

GitHub Pages is static hosting, so it **cannot run Ansible** directly.

You can still publish the front-end on Pages if you pair it with a backend renderer (for example, a GitHub Action, self-hosted API, or serverless function) that executes `ansible-playbook` and returns the output.
