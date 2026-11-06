# Verification boundaries

CI validates the existing application checks separately from source formatting, source publication allowlists and archive/package inspection. The packaging workflow produces checksums and source-commit provenance. Debian and RPM source/data packages have no service-start scripts; installation/removal validation does not establish native service compatibility.

RPMs target Rocky Linux 10 as previews. Native Mail, VPN and HTTP Boot setup remains unverified there. Media worker, FFmpeg, codecs and hardware acceleration are not exercised by packaging tests. No Client image or qualification VM is built for this work. Existing verification documents remain authoritative for previously recorded checks.
