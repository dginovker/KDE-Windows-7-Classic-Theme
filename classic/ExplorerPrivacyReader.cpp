#include <KConfig>
#include <KConfigGroup>
#include <QCoreApplication>
#include <QDataStream>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QMap>
#include <QStandardPaths>
#include <sched.h>
#include <sys/mount.h>
#include <unistd.h>

namespace {
bool write(const QString &path, const QByteArray &bytes)
{
    QFile file(path);
    return file.open(QIODevice::WriteOnly) && file.write(bytes) == bytes.size() && file.flush();
}
}

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QFile in, out;
    if (!in.open(stdin, QIODevice::ReadOnly) || !out.open(stdout, QIODevice::WriteOnly))
        return 1;
    QDataStream reader(&in);
    QStringList roots;
    QMap<QString, QByteArray> inputs;
    reader >> roots >> inputs;
    if (reader.status() != QDataStream::Ok)
        return 1;
    // The new mount is private to this short-lived process; no snapshot is written to disk.
    const auto uid = geteuid(), gid = getegid();
    const auto mapping = [](auto id) { return QByteArray::number(id) + ' ' + QByteArray::number(id) + " 1\n"; };
    if (!uid || unshare(CLONE_NEWUSER | CLONE_NEWNS) != 0
        || !write(QStringLiteral("/proc/self/uid_map"), mapping(uid))
        || !write(QStringLiteral("/proc/self/setgroups"), "deny")
        || !write(QStringLiteral("/proc/self/gid_map"), mapping(gid))
        || mount(nullptr, "/", nullptr, MS_REC | MS_PRIVATE, nullptr) != 0
        || mount("tmpfs", "/tmp", "tmpfs", MS_NODEV | MS_NOEXEC | MS_NOSUID, "size=24m,mode=0700") != 0
        || chroot("/tmp") != 0 || chdir("/") != 0)
        return 2;
    for (auto i = inputs.cbegin(); i != inputs.cend(); ++i) {
        const auto path = i.key();
        if (!path.startsWith(u'/') || path != QDir::cleanPath(path)
            || !QDir().mkpath(QFileInfo(path).path()) || !write(path, *i))
            return 3;
    }
    if (roots != QStandardPaths::standardLocations(QStandardPaths::GenericConfigLocation))
        return 3;
    const KConfig config(QStringLiteral("kactivitymanagerd-pluginsrc"));
    const auto policy = config.group(QStringLiteral("Plugin-org.kde.ActivityManager.Resources.Scoring"));
    // Use KDE's integer conversion, but do not turn a malformed setting into permission.
    const int remember = policy.hasKey("what-to-remember") ? policy.readEntry("what-to-remember", -1) : 0;
    bool allowed = remember == 0;
    if (remember == 1) {
        const auto spelling = policy.readEntry("blocked-by-default", QByteArray("false")).toLower();
        // KDE treats any non-false token as true; unknown tokens must not enable an allowlist.
        const QByteArrayList booleans{"false", "no", "off", "0", "true", "yes", "on", "1"};
        if (!booleans.contains(spelling))
            return 4;
        const auto app = QStringLiteral("org.win7classic.explorer");
        if (policy.readEntry("blocked-by-default", false))
            allowed = policy.readEntry("allowed-applications", QStringList{}).contains(app);
        else {
            const auto apps = policy.readEntry("blocked-applications", QStringList{});
            allowed = !apps.contains(app) && !apps.contains(app + QStringLiteral(".desktop"));
        }
    } else if (remember != 0 && remember != 2) {
        return 4;
    }
    const auto patterns = policy.readEntry("url-filters", QStringList{QStringLiteral("about:*"),
        QStringLiteral("*/.*"), QStringLiteral("/"), QStringLiteral("/tmp/*")});
    QDataStream writer(&out);
    writer << allowed << policy.readEntry("off-the-record-activities", QStringList{}) << patterns;
    return writer.status() == QDataStream::Ok && out.flush() ? 0 : 4;
}
