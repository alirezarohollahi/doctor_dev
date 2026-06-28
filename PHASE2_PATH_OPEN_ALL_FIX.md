# Phase 2 Hotfix: Clean URLs + Core Section Open/Close Controls

## Changes

- Added browser History API routing for clean paths instead of hash routes.
- Supported direct paths:
  - `/dashboard`
  - `/nodes`
  - `/cores`
  - `/logs`
  - `/cores/<core_id>/<tab>` where `<tab>` is one of `inbounds`, `routing`, `balancers`, `dependencies`, `advanced`.
- Added FastAPI SPA fallback so refresh/deep links return the panel UI.
- Added Open All / Close All controls in core editor sections:
  - Inbounds
  - Routing
  - Balancers, including nested endpoints
  - Dependencies
- Prevented the Cores breadcrumb link from writing `#` to the URL.

## Update target

Panel only. The node runtime is unchanged.
