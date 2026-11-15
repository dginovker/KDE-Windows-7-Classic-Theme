#!/usr/bin/env bash
# Installs the Windows 7 Classic mode for the current user. Nothing changes until `win7-classic windows`.
set -euo pipefail
src=$(dirname "$(readlink -f "$0")")
data=${XDG_DATA_HOME:-$HOME/.local/share}

# Wine's LGPL Tahoma is metric-compatible with the Windows UI font; Microsoft's own may not be redistributed.
fonts=$data/fonts/win7-classic
mkdir -p "$fonts"
for f in tahoma.ttf tahomabd.ttf; do
    [[ -f /usr/share/wine/fonts/$f ]] || { echo "missing /usr/share/wine/fonts/$f: install wine" >&2; exit 1; }
    cp /usr/share/wine/fonts/$f "$fonts/"
done
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"
cp "$src/fonts/70-win7-classic-tahoma.conf" "${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d/"
fc-cache "$fonts"

mkdir -p "$data/plasma/plasmoids" "$data/plasma/desktoptheme"
for applet in "$src"/plasma/org.win7classic.*; do
    rm -rf "$data/plasma/plasmoids/$(basename "$applet")"
    cp -r "$applet" "$data/plasma/plasmoids/"
done
rm -rf "$data/plasma/desktoptheme/win7-classic"
cp -r "$src/plasma/theme/win7-classic" "$data/plasma/desktoptheme/"
mkdir -p "$data/themes"
rm -rf "$data/themes/Win7-Classic"
cp -r "$src/plasma/gtk/Win7-Classic" "$data/themes/"
mkdir -p "$data/kwin/decorations"
rm -rf "$data/kwin/decorations/win7classic"
cp -r "$src/plasma/decoration/win7classic" "$data/kwin/decorations/"

rm -rf "$data/win7-classic"
mkdir -p "$data/win7-classic" "$HOME/.local/bin"
cp -r "$src/toggle/win7-classic" "$src/toggle/kconfig-keys" "$src/toggle/windows" "$data/win7-classic/"
ln -sfn "$data/win7-classic/win7-classic" "$HOME/.local/bin/win7-classic"
echo "installed; switch with: win7-classic windows"
