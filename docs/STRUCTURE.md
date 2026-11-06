# Repository map

| Area | Edit here | Notes |
| --- | --- | --- |
| Application / canonical source | main.go, tui.go and web_assets.go | Human-editable source |
| Generated output | assets/ examples and dist/ release output | Rebuild with the existing generator; do not hand edit |
| Tests | tests/ | Existing project checks; Logos uses scripts/verify.py |
| Packaging | packaging/ and scripts/release.py | Explicit source allowlist, version resolver and reproducible payloads |
| Documentation | README.md and docs/ | Shared README order; detailed setup in OPERATIONS.md |
| CI | .github/workflows/ | Separate application, format/package and release gates |

`packaging/release.json` reads the product version from `main.go`. Its revision adds a packaging prerelease suffix without relabeling the product as stable. `packaging/source-files.json` is the reviewed publication allowlist; update it after adding/removing committed files. Source/data package payloads preserve this layout.

Do not publish .git, runtime data, private directories, credentials, caches or local build scratch. Existing generated installers, minified web assets, checksums and compatibility artwork paths are intentionally retained.

Use `python3 scripts/format_web.py --check` for first-party CSS/JavaScript and plain HTML source (Node.js is a build-time tool only). Prettier 3.7.4 is pinned. Generated HTML/bundles and template expression whitespace are preserved separately.
