# KagNode Account in the CLI

Run `kagnode login` (or `/login` in the keyboard interface) to log in with KagNode. The command opens the central KagNode sign-in and approval journey: compare the displayed code and approve only your own request. Signup and MFA remain on KagNode's account service. The CLI has no separate local password database and does not create a second profile-link authorization.

After approval, the CLI stores its account identifier and private credentials in its existing owner-only configuration directory. Its display name and photo refresh through the existing CLI account API. Browser examples use the same cached profile and shared Core account control; open its avatar to manage appearance, scrolling and profile synchronization. The name belongs inside that opened control rather than in a second header button.

## Synchronization and offline access

Use `kagnode account sync on|off|status`, or the equivalent browser preference. Set `KAGNODE_ACCOUNT_SYNC=off` in the CLI process environment to enforce disabled synchronization. An enforced installation policy cannot be re-enabled from the browser.

Turning profile synchronization off stops profile refresh and hides the synchronized presentation. It does **not** revoke the CLI's sign-in credentials or remove its existing permission to use fictional examples offline. Use `kagnode logout` to revoke the device when online, remove local credentials and end offline demo access. A failed online revocation is reported honestly so you can revoke the device in KagNode Account later.

Profile refresh is bounded and serialized. The browser state request refreshes a stale profile at most once per fifteen minutes; a manual refresh and online account commands can request a fresh profile. Network failures keep the last valid local account and explicitly fictional examples available. No cloud resources, billing or live provisioning are activated by a cached profile.

## Data and permissions

The CLI uses its existing `/api/cli/device`, `/api/cli/token` and `/api/cli/me` protocol. Its profile panel does not use the separate self-hosted-application sign-in proof or request a new `email.read` grant. It displays the name and photo actually authorized by the CLI grant; it never invents a verified email address or matches accounts by email.

The local browser receives profile presentation and an owner-authorized local demo session, never KagNode access or refresh tokens. KagNode credentials remain in owner-only server-side files. The operating-system owner controls the CLI's local preferences; a KagNode profile cannot grant root or permission to administer other installations.

Core's browser appearance connection remains separate from this server-side profile preference. Core scripts, styling and artwork are served by the local CLI, with an embedded fallback for offline startup. See [Core integration](CORE.md) and [security](SECURITY.md).
