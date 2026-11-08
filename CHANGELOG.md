# 1.2.0-beta.1 — ecosystem preview

## Consolidation/update coordination preview

Share native and application locks between consolidation and updates, including separate destination roots on the same host. Persist migration recovery markers before moving files, block updates after interrupted migrations, and allow only the recorded migration journal to resume or roll back. Preview remains read-only; retained originals and post-migration writes are preserved.

## Application activation recovery preview

Persist an activation journal before managed/native code changes. Interrupted updates and failed metadata writes now require recovery review, including inactive installations; status disables further apply operations. Setup and CLI activation also respect the recovery block. Preserve data and backups without automatically rolling back databases.

## Account panel recovery preview

Show retry controls on initial profile failures and ignore late status responses after a profile or sync-policy action. The CLI continues using its existing sign-in flow; server-style device-link cancellation is not introduced.

## Interrupted Core operation recovery preview

Bundle reviewed Core manager 1.2.1 with lock-proven operation recovery, offline signed-cache verification and conservative scratch cleanup. Preserve existing activation and automatic-update policy; the browser fallback stays on 1.0.5.

## Declared Core binding preview

Refresh the separately reviewed manager to Core 1.2.0 with explicit application declarations, atomic baseline adoption and verified UI rollback. The browser fallback remains on 1.0.5.

Document the pinned Core baseline explicitly for new server bindings and the reviewed application-upgrade workflow. Existing application data and stable release selections remain unchanged.

## Reviewed Core manager repair preview

Refresh the embedded manager to Core 1.1.5 for safe background-lock handling and structured invalid-request errors. Record the helper’s exact source commit and checksum independently from the 1.0.5 browser fallback.

## Shared loading spinner preview

Use KagNode Core 1.0.5 for the shared split-orbit loading mark, with reduced-motion support and existing status/recovery controls retained. This changes web presentation without resetting data or provisioning native services.

## Core integration preview

Shared local UI components, manual animated navigation, natural scrolling rails and icon account menus. Added separate appearance-only account connections and signed UI patch controls. Existing storage, native services and prior release records are retained.

## 1.2.0-beta.1 packaging.2

- Follow the renamed kagnode-passwords repository for Passwords releases and updates.

- Add a keyboard-only install/setup wizard with scriptable `apps` operations.
- Manage application code, configuration, data and backups under one chosen root.
- Add reviewed GitHub updates, local app-specific sockets, native guards and retained backups.
- Add explicit native path consolidation with inventories, journals and compatibility links.
- Add digest-pinned Vaultwarden setup for Bitwarden clients alongside KagNode Passwords.
- Existing native services and client images are not automatically provisioned or migrated.

# 1.0.0

## 1.1.0

- Added the Linux terminal interface with product selection, command history, completion, scrollback, cancellation, resize handling and plain-output support.
- Applied the shared KagNode UI to embedded browser examples and added minified, fingerprinted delivery assets.
- Kept real account actions separate from fictional cloud examples.

First stable release for KagNode account authorization, profile access and the thirteen isolated product examples. The terminal and local browser share the same example catalog. Education and Business names are written in full, and README artwork follows the system theme.

Linux amd64 and arm64 archives and Debian packages include checksums. Live cloud provisioning, billing and model inference are outside this release.

## Account profile integration preview

Added optional KagNode Account display-name/photo linking, local administrator disable controls and private credential storage. Existing local account authentication and data remain independent.
