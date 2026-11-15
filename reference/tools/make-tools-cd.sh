#!/usr/bin/env bash
# Builds native-bench.exe and attaches it to the Windows reference VM as a read-only CD (drive D:).
set -euo pipefail
cd "$(dirname "$0")"
media=$HOME/.local/share/libvirt/images/win7-reference-media
bash build-bench.sh
rm -f native-bench-res.o
stage=$(mktemp -d)
cp native-bench.exe "$stage/"
iso=$media/tools-$(sha256sum native-bench.exe | cut -c1-12).iso
xorriso -as mkisofs -quiet -V W7TOOLS -J -o "$iso" "$stage"
rm -r "$stage"
virsh -c qemu:///session change-media win7-classic-reference hdc "$iso" --update --live --config >/dev/null
echo "attached $iso"
