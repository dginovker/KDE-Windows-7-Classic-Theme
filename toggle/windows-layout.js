// Seeds the Windows layout the first time it is used; afterwards the saved profile is reused.
for (const p of panels()) p.remove();
const panel = new Panel;
panel.location = "bottom";
panel.height = 44;
panel.floating = false;
panel.addWidget("org.kde.plasma.kickoff");
const tasks = panel.addWidget("org.kde.plasma.taskmanager");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("groupingStrategy", 0);
panel.addWidget("org.kde.plasma.systemtray");
panel.addWidget("org.kde.plasma.digitalclock");
panel.addWidget("org.kde.plasma.showdesktop");
