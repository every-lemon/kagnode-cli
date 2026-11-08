# KagNode Core integration preview

This application uses [KagNode Core](https://github.com/every-lemon/kagnode-core) for its sidebar, controls, scrolling, loading and account presentation. Its committed `core.lock.json` records the baseline and compatible stable UI patch line. Editable corresponding Core source is retained under `vendor/core-source/`; generated pinned fallbacks let the interface start offline.

Application servers serve Core assets from their own origin. Browsers never fetch Core scripts from GitHub. Local accounts retain local sign-in and permissions. Appearance can connect directly to KagNode Account using a separate browser-only appearance grant; profile linking remains a distinct administrator setting.

Only stable compatible UI patches may install automatically. Backend helpers, prereleases, minor/major versions and application updates require review. A Core patch cannot restart a service or run a backend hook. The local administrator sees status, update policy and rollback in settings. Use `sudo kagnode core bind cli --user SERVICE_USER` to bind the service and run the manager described in [Core operations](https://github.com/every-lemon/kagnode-core/blob/main/docs/OPERATIONS.md). Ordinary users cannot manage updates.

This preview upgrades web presentation. It does not qualify native services, codecs, HTTP Boot images, network hardware or a new stable application release. Keep application databases and deployment configuration in their existing locations. No data reset or native provisioning is part of Core integration.

## Shared loading mark

Core 1.0.5 supplies KagNode’s split-orbit spinner. The canonical logo stays still while its separated accent orbits. Reduced-motion settings stop the animation. Existing loading labels, retries and dismissal controls remain available. The server serves the spinner and artwork locally; no browser Core connection to GitHub is required.
