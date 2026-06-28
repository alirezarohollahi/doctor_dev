# Phase 2 — Core Collapsible Cards Fix

This hotfix adds expand/collapse controls to all main cards inside the Core editor:

- Inbound cards
- Routing cards
- Balancer cards
- Endpoint cards inside balancers
- Dependency cards

Behavior:

- Cards are open by default.
- Each card has a chevron button next to its title.
- Collapsed state is kept while the editor re-renders in the current session.
- Adding an endpoint automatically keeps its parent balancer open.
- The visual style matches the existing endpoint tree controls.

Validation/build checks performed:

```bash
python3 -m compileall -q doctor_dev_panel doctor_dev_node main.py
node --check doctor_dev_panel/web/assets/js/app.js
node --check doctor_dev_panel/web/assets/js/login.js
bash -n scripts/doctor_dev.sh
```
