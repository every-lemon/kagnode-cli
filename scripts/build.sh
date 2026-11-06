#!/usr/bin/env bash
set -euo pipefail
umask 022
cd "$(dirname "$0")/.."
version=$(sed -n 's/^const version = "\([^"]*\)"/\1/p' main.go)
mkdir -p dist
for arch in amd64 arm64; do
  out="dist/kagnode-cli_${version}_linux_${arch}"
  mkdir -p "$out"
  CGO_ENABLED=0 GOOS=linux GOARCH="$arch" go build -trimpath -ldflags='-s -w' -o "$out/kagnode" .
  cp README.md LICENSE BRAND-POLICY.md ARTWORK-LICENSE "$out/"
  mkdir -p "$out/assets"
  cp assets/kagnode-wordmark.svg "$out/assets/"
  chmod 755 "$out" "$out/kagnode"
  chmod 644 "$out/"*.md "$out/LICENSE" "$out/ARTWORK-LICENSE"
  tar -C "$out" -czf "$out.tar.gz" .
  deb="dist/deb-$arch"
  mkdir -p "$deb/DEBIAN" "$deb/usr/bin" "$deb/usr/share/doc/kagnode-cli"
  cp "$out/kagnode" "$deb/usr/bin/"
  cp LICENSE README.md BRAND-POLICY.md ARTWORK-LICENSE "$deb/usr/share/doc/kagnode-cli/"
  mkdir -p "$deb/usr/share/doc/kagnode-cli/assets"
  cp assets/kagnode-wordmark.svg "$deb/usr/share/doc/kagnode-cli/assets/"
  cat > "$deb/DEBIAN/control" <<CONTROL
Package: kagnode-cli
Version: $version
Architecture: $arch
Maintainer: KagNode contributors
Description: KagNode account sign-in and fictional cloud demos
Section: utils
Priority: optional
CONTROL
  find "$deb" -type d -exec chmod 755 {} +
  find "$deb" -type f -exec chmod 644 {} +
  chmod 755 "$deb/usr/bin/kagnode"
  dpkg-deb --root-owner-group --build "$deb" "dist/kagnode-cli_${version}_${arch}.deb"
done
(cd dist && sha256sum "kagnode-cli_${version}_"*.tar.gz "kagnode-cli_${version}_"*.deb > SHA256SUMS)
