# Verification scope

## CLI 5.0.1

The terminal manager, PKCE protocol, private credential migration and typed installer orchestration are checked with isolated fixtures. Browser tests exercise actual native CLI callback listeners with a fictional local issuer in Chromium/WebKit; production KagNode account login is not performed. Native adapters are tested through mocked runners and capability checks, without provisioning live systems. No HTTP Boot images, network hardware qualification, Media transcoding, Entropy deployment or live native service installation is part of these checks.

Fictional browser examples were removed. Existing runtime data is preserved. The previous verification record below describes historical versions and does not imply current native qualification.

# Verification boundaries

CI validates the existing application checks separately from source formatting, source publication allowlists and archive/package inspection. The packaging workflow produces checksums and source-commit provenance. Debian and RPM source/data packages have no service-start scripts; installation/removal validation does not establish native service compatibility.

RPMs target Rocky Linux 10 as previews. Native Mail, VPN and HTTP Boot setup remains unverified there. Media worker, FFmpeg, codecs and hardware acceleration are not exercised by packaging tests. No Client image or qualification VM is built for this work. Existing verification documents remain authoritative for previously recorded checks.
