# KagNode Account sign-in

`kagnode login` opens same-browser KagNode authorization using client `kagnode-cli-profile`, S256 PKCE and a random state/nonce. A listener binds only literal `127.0.0.1` on an ephemeral port and the fixed `/auth/kagnode/callback` path. It validates the original state, exact issuer, peer, Host and unique callback parameters. Codes are exchanged over the authenticated backchannel; access/refresh tokens never appear in a browser URL.

The first exchange requires a fresh proof bound to issuer, subject, client, loopback installation, sign-in purpose, nonce and bounded time. The subsequent profile must match the same subject. Only then does an atomic private-file replacement store credentials. Legacy device credentials remain usable with their original endpoints until explicit successful new sign-in replaces them. Failed, denied or offline login does not overwrite them. There is no email-based account merging or local privilege grant.

`kagnode login --headless` retains the explicit legacy device-code flow. Optional `--server` accepts an HTTPS origin, with literal loopback HTTP allowed for isolated tests. HTTP redirects are never followed by the token client.

`kagnode account sync on|off|status` controls display name/photo refresh; installation administrators can set `KAGNODE_ACCOUNT_SYNC=off`. It does not revoke sign-in or gate local application setup. `kagnode logout` attempts online revocation, reports uncertainty and removes local credentials. It preserves application data and old example files.

Credentials remain at the established XDG config path with mode0600. The keyboard TUI renders only sanitized profile text. No account requirement is imposed on application installation or local administration. Tests use fictional isolated issuers; they do not log in to production.
