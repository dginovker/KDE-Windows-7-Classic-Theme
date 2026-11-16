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

if [[ ${1:-} != --prefix && ! -f /usr/lib/qt6/plugins/styles/libwin7classicstyle.so ]]; then
    echo "win7-classic: system-wide Win7Classic Qt style is missing; run: cd packaging && makepkg -si" >&2
    exit 1
fi

# Wine's LGPL Tahoma is metric-compatible with the Windows UI font; Microsoft's own may not be redistributed.
for f in tahoma.ttf tahomabd.ttf; do
    [[ -f /usr/share/wine/fonts/$f ]] || { echo "missing /usr/share/wine/fonts/$f: install wine" >&2; exit 1; }
done

# Dependency/build failures must leave the previous installation intact.
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
if [[ ${1:-} == --prefix ]]; then prefix=/usr; else prefix=$(dirname "$data"); fi
cmake -S "$src/explorer" -B "$build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$prefix" >/dev/null
cmake --build "$build" --parallel 2 >/dev/null
if [[ ${1:-} != --prefix ]]; then
    QT_QPA_PLATFORM=offscreen "$build/classic/win7-classic-probe" --available || {
        echo "win7-classic: Win7Classic style cannot load; reinstall: cd packaging && makepkg -si" >&2
        exit 1
    }
fi

mkdir -p "$fonts" "$fontconf"
for f in tahoma.ttf tahomabd.ttf; do
    install -m644 /usr/share/wine/fonts/$f "$fonts/"
done
install -m644 "$src/fonts/70-win7-classic-tahoma.conf" "$fontconf/"

mkdir -p "$data/plasma/plasmoids" "$data/plasma/desktoptheme" "$data/kwin/decorations" "$data/themes" "$bin"
for applet in "$src"/plasma/org.win7classic.*; do
    rm -rf "${data:?}/plasma/plasmoids/$(basename "$applet")"
    cp -r "$applet" "$data/plasma/plasmoids/"
done
rm -rf "$data/plasma/desktoptheme/win7-classic" "$data/kwin/decorations/win7classic" "$data/themes/Win7-Classic" "$data/icons/Win7-Classic" "$data/icons/Win7-Classic-Cursors" "$data/win7-classic" "$data/color-schemes/Win7Classic.colors"
cp -r "$src/plasma/theme/win7-classic" "$data/plasma/desktoptheme/"
cp -r "$src/plasma/decoration/win7classic" "$data/kwin/decorations/"
cp -r "$src/plasma/gtk/Win7-Classic" "$data/themes/"
mkdir -p "$data/icons" "$data/color-schemes"
cp -r "$src/plasma/icons/Win7-Classic" "$src/plasma/cursors/Win7-Classic-Cursors" "$data/icons/"
# The named color scheme Windows mode selects, built from the same colors it swaps in (toggle/windows/keys).
python3 - "$src/toggle/windows/keys/kdeglobals" > "$data/color-schemes/Win7Classic.colors" <<'PY'
import sys
print('[General]\nName=Windows 7 Classic')
keep = False
for line in open(sys.argv[1]).read().splitlines():
    if line.startswith('['):
        keep = line.startswith(('[Colors:', '[WM]'))
    if keep and not line.startswith('#') and not line.startswith('activeFont'):
        print(line)
PY
mkdir -p "$data/win7-classic/lockscreen"
cp -r "$src/toggle/win7-classic" "$src/toggle/kconfig-keys" "$src/toggle/windows" "$data/win7-classic/"
cp "$src/plasma/lockscreen/LockScreen.qml" "$src/plasma/logon/LogonUi.qml" "$data/win7-classic/lockscreen/"
if [[ ${1:-} == --prefix ]]; then
    # The login screen is system-wide: installed here, selected by the administrator (see README).
    rm -rf "$data/sddm/themes/win7-classic"
    mkdir -p "$data/sddm/themes/win7-classic"
    cp "$src/plasma/sddm/Main.qml" "$src/plasma/sddm/metadata.desktop" "$src/plasma/logon/LogonUi.qml" "$data/sddm/themes/win7-classic/"
fi
ln -sfn "$(realpath -m --relative-to="$bin" "$data/win7-classic/win7-classic")" "$bin/win7-classic"

DESTDIR=${root:-} cmake --install "$build" >/dev/null

[[ ${1:-} == --prefix ]] || fc-cache "$fonts"
echo "installed; switch with: win7-classic windows"
