# KagNode Core integration preview

This application uses [KagNode Core](https://github.com/every-lemon/kagnode-core) for its sidebar, controls, scrolling, loading and account presentation. Its committed `core.lock.json` records the baseline and compatible stable UI patch line. Editable corresponding Core source is retained under `vendor/core-source/`; generated pinned fallbacks let the interface start offline.

Application servers serve Core assets from their own origin. Browsers never fetch Core scripts from GitHub. Local accounts retain local sign-in and permissions. Appearance can connect directly to KagNode Account using a separate browser-only appearance grant; profile linking remains a distinct administrator setting.

Only stable compatible UI patches may install automatically. Backend helpers, prereleases, minor/major versions and application updates require review. A Core patch cannot restart a service or run a backend hook. The local administrator sees status, update policy and rollback in settings. Use `sudo kagnode core bind cli --user SERVICE_USER --baseline 1.0.5` to bind the service and run the manager described in [Core operations](https://github.com/every-lemon/kagnode-core/blob/main/docs/OPERATIONS.md). Ordinary users cannot manage updates.

This preview upgrades web presentation. It does not qualify native services, codecs, HTTP Boot images, network hardware or a new stable application release. Keep application databases and deployment configuration in their existing locations. No data reset or native provisioning is part of Core integration.

## Shared loading mark

Core 1.0.5 supplies KagNode’s split-orbit spinner. The canonical logo stays still while its separated accent orbits. Reduced-motion settings stop the animation. Existing loading labels, retries and dismissal controls remain available. The server serves the spinner and artwork locally; no browser Core connection to GitHub is required.

## Reviewed manager helper

The bundled `kagnode core` helper is reviewed separately from browser assets. `assets/core-manager-manifest.json` records its exact public Core commit and checksum; corresponding source is retained under `vendor/core-source/packages/python/manager.py`. Manager 1.2.1 includes locking, request validation, explicit reviewed baseline-adoption controls and offline recovery of abandoned operation journals. Recovery preserves activation and policy and only removes ownership-marked staging files. The browser fallback and automatic UI patch policy remain on the compatible 1.0.x line. Updating UI assets cannot replace this helper or restart services.

## Binding and reviewed application upgrades

The explicit baseline above matches this source’s pinned fallback; do not rely on an older manager’s implicit 1.0.x default. With Core manager 1.2.0 or newer, prefer `--lock-file /path/to/app/core.lock.json` instead of `--baseline` to read the adapter version and automatic-update preference from the reviewed application declaration. Existing bindings are retained by `bind`. Follow the [reviewed application upgrade workflow](https://github.com/every-lemon/kagnode-core/blob/main/docs/OPERATIONS.md#reviewed-application-upgrades) to adopt a changed baseline explicitly after verifying current UI rollback assets and retaining the app’s source/data backup. Web UI patch controls cannot perform that minor-version adoption.
