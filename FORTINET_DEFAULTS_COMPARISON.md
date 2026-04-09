# Fortinet 7.0 Hub Routing Defaults vs This Repo

This note compares the Fortinet 7.0 "BGP on Loopback" defaults (as provided) with this repository's hub BGP/routing defaults.

## Key differences

| Area | Fortinet template default (provided) | Repo default | Impact |
|---|---|---|---|
| Keepalive / Hold timers | `15 / 45` | `1 / 3` | Repo converges faster but can be less stable on high-jitter/CPU-constrained links. |
| eBGP multipath | `enable` | `disable` | Repo is optimized for single-AS iBGP ADVPN lab design, not eBGP underlay symmetry. |
| Additional-path knobs | Not shown in your snippet | `additional-path enable`, `additional-path-select 4`, advertise up to 8 | Repo favors path diversity in ADVPN overlays; higher control-plane load. |
| Route-tag policy model | `LOCAL_REGION` route-map sets `no-export` | Community-list/route-tag route-maps (`RM-HUB-*`) | Repo steers SD-WAN route-services with tags, not regional no-export suppression. |
| Neighbor-range strategy | Single loopback summary | Per-branch /32 in loopback mode | Repo is explicit and deterministic per spoke. |
| Static blackhole routes | Corporate summaries blackholed to avoid leaks/recursion | Loopback blackhole support is variable-driven, but no fixed `lan_summary` + `lo_summary` pair exactly as in snippet | Fortinet snippet has stronger explicit leak-guard posture. |

## Repo values currently in use

- Hub BGP template renders from variables (`ebgp_multipath`, `ibgp_multipath`, timers, additional-path, etc.).
- Global defaults set aggressive fast-fail timers (`keep_alive_timer: 1`, `holdtime_timer: 3`).
- Design explicitly indicates loopback peering as preferred mode (`session_mode: loopback`).

## Suggested changes (ranked)

1. **Add a profile switch for timer posture (lab vs production).**
   - Keep current `1/3` as `lab_fast` profile.
   - Add `production_stable` profile using `15/45` as a safer baseline.

2. **Keep `ebgp_multipath: disable` unless you truly run eBGP between regions/providers.**
   - Your current single-AS iBGP defaults are aligned with this repo's design intent.

3. **Retain additional-path, but tune scale knobs per site count.**
   - For smaller deployments, reduce `additional_path_select` and `adv_additional_path` to lower churn and memory.

4. **Introduce optional `LOCAL_REGION` no-export policy for inter-region deployments.**
   - If you add multi-region hubs later, make this a toggleable route-map stage.

5. **Harden leak prevention to match Fortinet snippet behavior.**
   - Ensure explicit static blackhole protection exists for both LAN and loopback aggregate summaries in all rendering paths.

6. **Consider adding `advertisement-interval 1` as a variableized default if absent in some peer modes.**
   - Your templates already variableize this, which is good; verify consistency across all session modes.

## Practical recommendation for your current repo

If this remains a **lab/demo ADVPN single-AS fabric**, your current defaults are mostly intentional and reasonable. The biggest improvement is not wholesale alignment to Fortinet defaults, but introducing **environment profiles** (lab vs production) so operators can safely move from test to real WAN conditions without hand-editing many knobs.
