<p align="center"><img src="assets/kagnode-wordmark.svg" width="440" alt="KagNode. CLI"></p>

# KagNode CLI

A Linux command line interface for your KagNode account and **fictional cloud demos**. Sign in through your browser, then explore all 13 products in a terminal or a local web interface. There is no live provisioning, inference or billing API in this release.

Source version **1.1.0** adds a keyboard-driven terminal interface. Version 1.0.0 remains the existing stable release until new packages are published. Cloud resource commands remain fictional until their services and APIs are implemented.

## Install

Download the matching Linux `amd64` or `arm64` archive or Debian package from [Releases](https://github.com/every-lemon/kagnode-cli/releases). Verify it against `SHA256SUMS`. Extract the archive and put `kagnode` on your PATH, or install the `.deb` with your package manager. The binary includes the demo assets and needs no Node.js installation.

```sh
kagnode login
kagnode whoami
kagnode demo install
kagnode demo start
```

The first command prints a verification address and a short code. Open the address, sign in to KagNode, compare the code and approve the request you started. The CLI never asks for your password. It receives only profile/demo access; enrollment, Operator access and Team membership remain separate choices.

The browser demo listens on a random **loopback-only** port and prints a local access link. It does not send your account token to the browser. Run `kagnode demo stop` when finished. Web examples reset on refresh. Terminal example changes persist locally until reset. Both use the same starting fictional fixtures.

```sh
kagnode                         # Terminal interface
kagnode demo list                # All 13 product examples
kagnode demo vps list
kagnode demo vps create "Design review"
kagnode demo ai prompt "Example request"
kagnode demo q1 settings
kagnode demo reset
kagnode logout
```

The catalog covers Console, VPS, Q1 storage, CDN, Cloud PC, AI, VPN, Cloud Browser, Education, Business, Enterprise, Tunnel and Status. Terminal resource commands are deliberately generic sample operations; the browser examples provide the richer product-specific flows. AI replies are predefined sample output.

## Terminal interface

Run `kagnode` or `kagnode tui` in a Linux terminal. A product rail, command prompt and scrollable activity pane share the screen. Narrow terminals use a compact layout.

Use `/products`, `/use vps`, `/list`, `/create "Example"`, `/login`, `/whoami`, `/logout` and `/help`. Up/Down recall commands, Tab completes a command, Page Up/Down scroll output, Ctrl+U clears the prompt, Ctrl+C cancels an operation, and `/quit` exits. Terminal settings are restored on exit. Commands call the existing CLI directly without a shell. The numeric menu remains available when a raw terminal is unavailable.

Account actions are real. Product resources and AI responses are explicitly fictional examples; the TUI does not provision cloud services.

## Account and local data

First sign-in is required by the standard CLI workflow. Installed fictional demos then work offline. Online account actions always validate credentials. Access tokens expire; refresh tokens rotate and can be revoked in **Account → CLI devices**. Offline copies cannot be remotely erased by account revocation. Local logout clears credentials and offline access, and attempts online revocation; it reports when revocation could not be confirmed.

Credentials: `${XDG_CONFIG_HOME:-~/.config}/kagnode/cli/account.json` (0600). Demo data: `${XDG_DATA_HOME:-~/.local/share}/kagnode/cli/` (0700 directory). Avoid sharing these directories. The larger ASCII banner follows your terminal width. Redirected output stays plain; `NO_COLOR=1` or `TERM=dumb` disables terminal color. An HTTPS account origin is required; loopback HTTP is available solely for development with `login --server`.

## Build and test

Go 1.24 or later, standard library only:

```sh
go test ./...
go build -trimpath -o kagnode .
bash scripts/build.sh
```

To regenerate browser assets after editing their readable source, install esbuild 0.28.2 as a build tool and run `ESBUILD=/path/to/esbuild python3 scripts/build-web.py`. The binary embeds minified pages and fingerprinted CSS/JS, with no public source maps. Source and licenses remain available; hashes aid caching and identification and cannot prevent inspection or licensed reuse.

The release script creates Linux amd64/arm64 archives, Debian packages and checksums. The `assets` directory contains only fictional demo source and artwork, never private plans or account data. No installer script is downloaded and executed at runtime.

## Source and license

AGPL-3.0-only; see [LICENSE](LICENSE). [Brand policy](BRAND-POLICY.md) is separate from software rights. Forks and modifications are allowed under the license. Identify independent deployments clearly; do not imply KagNode operates them.

[KagNode](https://nebulacoder.com) · [Developer](https://developer.nebulacoder.com) · [Logo assets](https://github.com/every-lemon/kagnode-logos)
