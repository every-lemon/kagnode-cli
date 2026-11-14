# KagNode Core Rust adapter

Framework-independent Linux/Unix server adapter. `Core::new(root, application)` provides `active()`, `asset(version, filename)` and `head(context)`. Hosts keep their own authorization, CSRF, identity and routing.

UI files are served from the application's own origin. A checksum-verified embedded fallback supports offline startup. Managed versions must be root-controlled, compatible 5.0.x UI API 1 bundles; asset sizes and checksums are validated before delivery. The existing signed Core manager owns downloads and activation. Ordinary page/asset requests never contact GitHub.

`manager_request` is only a transport: the application must enforce local administrator permission and CSRF before administrative calls, and isolate public update summaries from privileged status. Do not pass untrusted request bodies directly as manager parameters.

`fallback/bundle.json` is generated from canonical Core build output. Keep corresponding readable Core source and licenses with vendored copies. Automatic patches cannot install this Rust backend adapter or run application hooks.

`template(name, text, html)` renders the canonical Core login, sidebar and account templates. Text parameters are escaped. HTML parameters must contain only authorized host-authored fragments; never pass untrusted HTML. Templates are bundled with the reviewed adapter and are not executable update hooks.
