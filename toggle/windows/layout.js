// Seeds Windows mode the first time it is used; afterwards the saved profile is reused.
for (const p of panels()) p.remove();
for (const d of desktops()) {
    d.wallpaperPlugin = "org.kde.color";
    d.currentConfigGroup = ["Wallpaper", "org.kde.color", "General"];
    d.writeConfig("Color", "#3a6ea5");
}
const panel = new Panel;
panel.location = "bottom";
panel.height = 44;
panel.floating = false;
const taskbar = panel.addWidget("org.win7classic.taskbar");
taskbar.currentConfigGroup = ["General"];
taskbar.writeConfig("launchers", ["applications:firefox.desktop", "applications:org.kde.dolphin.desktop", "applications:org.kde.konsole.desktop"]);
panel.addWidget("org.win7classic.trayframe");
panel.addWidget("org.kde.plasma.systemtray");
panel.addWidget("org.win7classic.clock");
