#!/usr/bin/env bash
# Installs Windows 7 Classic mode. Nothing on screen changes until `win7-classic windows`.
#   ./install.sh                 for the current user (development)
#   ./install.sh --prefix DIR    system layout under DIR, used by packaging/PKGBUILD
set -euo pipefail
src=$(dirname "$(readlink -f "$0")")

if [[ ${1:-} == --prefix ]]; then
    root=${2:?usage: install.sh --prefix DIR}
    data=$root/usr/share
    bin=$root/usr/bin
    fonts=$data/fonts/win7-classic
    fontconf=$data/fontconfig/conf.avail
else
    data=${XDG_DATA_HOME:-$HOME/.local/share}
    bin=$HOME/.local/bin
    fonts=$data/fonts/win7-classic
    fontconf=${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d
fi

# Wine's LGPL Tahoma is metric-compatible with the Windows UI font; Microsoft's own may not be redistributed.
mkdir -p "$fonts" "$fontconf"
for f in tahoma.ttf tahomabd.ttf; do
    [[ -f /usr/share/wine/fonts/$f ]] || { echo "missing /usr/share/wine/fonts/$f: install wine" >&2; exit 1; }
    install -m644 /usr/share/wine/fonts/$f "$fonts/"
done
install -m644 "$src/fonts/70-win7-classic-tahoma.conf" "$fontconf/"

mkdir -p "$data/plasma/plasmoids" "$data/plasma/desktoptheme" "$data/kwin/decorations" "$data/themes" "$bin"
for applet in "$src"/plasma/org.win7classic.*; do
    rm -rf "${data:?}/plasma/plasmoids/$(basename "$applet")"
    cp -r "$applet" "$data/plasma/plasmoids/"
done
rm -rf "$data/plasma/desktoptheme/win7-classic" "$data/kwin/decorations/win7classic" "$data/themes/Win7-Classic" "$data/win7-classic"
cp -r "$src/plasma/theme/win7-classic" "$data/plasma/desktoptheme/"
cp -r "$src/plasma/decoration/win7classic" "$data/kwin/decorations/"
cp -r "$src/plasma/gtk/Win7-Classic" "$data/themes/"
mkdir -p "$data/win7-classic"
cp -r "$src/toggle/win7-classic" "$src/toggle/kconfig-keys" "$src/toggle/windows" "$data/win7-classic/"
ln -sfn "$(realpath -m --relative-to="$bin" "$data/win7-classic/win7-classic")" "$bin/win7-classic"

[[ ${1:-} == --prefix ]] || fc-cache "$fonts"
echo "installed; switch with: win7-classic windows"
