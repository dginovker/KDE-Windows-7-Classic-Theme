#include "ExplorerPrivacy.h"

#include <QDataStream>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusReply>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QProcess>
#include <QStandardPaths>
#include <fcntl.h>
#include <sys/inotify.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr int maxInput = 1024 * 1024;
constexpr int maxSnapshot = 16 * maxInput;
constexpr uint32_t changes = IN_ATTRIB | IN_MODIFY | IN_DELETE_SELF | IN_MOVE_SELF;
constexpr uint32_t children = IN_CREATE | IN_DELETE | IN_MOVED_FROM | IN_MOVED_TO;
struct Fd {
    int value;
    ~Fd() { if (value >= 0) close(value); }
};

QString currentActivity()
{
    const QDBusReply<QString> reply = QDBusConnection::sessionBus().call(ExplorerPrivacy::activityQuery(), QDBus::Block, 100);
    return reply.isValid() ? reply.value() : QString{};
}
}

QDBusMessage ExplorerPrivacy::activityQuery()
{
    return QDBusMessage::createMethodCall(QStringLiteral("org.kde.ActivityManager"),
        QStringLiteral("/ActivityManager/Activities"), QStringLiteral("org.kde.ActivityManager.Activities"),
        QStringLiteral("CurrentActivity"));
}

ExplorerPrivacy::ExplorerPrivacy() : events(inotify_init1(IN_NONBLOCK | IN_CLOEXEC))
{
    const auto state = QStandardPaths::writableLocation(QStandardPaths::GenericStateLocation);
    if (events < 0 || state.isEmpty())
        return;
    mode = state + QStringLiteral("/win7-classic/mode");
    const auto initialMode = observe({mode});
    if (!initialMode || !unchanged())
        return;
    const auto marker = initialMode->value(mode).bytes;
    if (!initialMode->contains(mode) || marker == "current\n") {
        policy = Status::Denied;
        return;
    }
    if (marker != "windows\n")
        return;
    // Preserve the real absolute XDG paths: KF distinguishes layers by their literal writable prefix.
    roots = QStandardPaths::standardLocations(QStandardPaths::GenericConfigLocation);
    if (roots.isEmpty() || roots.size() > 32)
        return;
    for (const auto &dir : roots) {
        for (auto name : {"kactivitymanagerd-pluginsrc", "kdeglobals", "system.kdeglobals"})
            sources.append(dir + u'/' + QLatin1StringView(name));
    }
    if (!qEnvironmentVariableIsSet("KDE_SKIP_KDERC"))
        sources.append(QStringLiteral("/etc/kde5rc"));
    sources.removeDuplicates();
    const auto observed = observe(QStringList{mode} + sources);
    if (!observed) {
        qWarning("win7-explorer: cannot observe Frequent privacy inputs");
        return;
    }
    // Capture the activity before queueing: reading it during parsing could grant a private visit later.
    activity = currentActivity();
    if (observed->value(mode) == initialMode->value(mode) && unchanged())
        snapshot = observed;
}

ExplorerPrivacy::Status ExplorerPrivacy::readPolicy()
{
    QMap<QString, QByteArray> inputs;
    for (auto i = snapshot->cbegin(); i != snapshot->cend(); ++i) {
        if (i.key() != mode && i->inode)
            inputs.insert(i.key(), i->bytes);
    }
    QByteArray request;
    QDataStream writer(&request, QIODevice::WriteOnly);
    writer << roots << inputs;
    QProcess helper;
    helper.setWorkingDirectory(QStringLiteral("/"));
    helper.start(QStringLiteral(WIN7_EXPLORER_POLICY), {});
    if (!helper.waitForStarted(250) || helper.write(request) != request.size()) {
        qWarning("win7-explorer: cannot start Frequent privacy reader");
        return Status::Unavailable;
    }
    helper.closeWriteChannel();
    if (!helper.waitForFinished(500) || helper.exitStatus() != QProcess::NormalExit || helper.exitCode() != 0
        || !helper.readAllStandardError().isEmpty()) {
        if (helper.state() != QProcess::NotRunning) {
            helper.kill();
            helper.waitForFinished(250);
        }
        qWarning("win7-explorer: Frequent privacy snapshot was not accepted");
        return Status::Unavailable;
    }
    const auto response = helper.readAllStandardOutput();
    QDataStream reader(response);
    bool allowed = false;
    QStringList privateActivities, patterns;
    reader >> allowed >> privateActivities >> patterns;
    if (reader.status() != QDataStream::Ok || !reader.atEnd())
        return Status::Unavailable;
    if (!allowed)
        return Status::Denied;
    checkActivity = !privateActivities.isEmpty();
    if (checkActivity && activity.isEmpty())
        return Status::Unavailable;
    if (privateActivities.contains(activity))
        return Status::Denied;
    // Plasma's scoring plug-in uses *, without path-component or case-folding rules.
    for (const auto &pattern : patterns) {
        QString regex;
        qsizetype start = 0;
        for (qsizetype i = 0; i < pattern.size(); ++i) {
            if (pattern[i] == u'\\') {
                ++i;
            } else if (pattern[i] == u'*') {
                regex += QRegularExpression::escape(pattern.mid(start, i - start)) + QStringLiteral(".*");
                start = i + 1;
            }
        }
        regex += QRegularExpression::escape(pattern.mid(start));
        filters.append(QRegularExpression(QRegularExpression::anchoredPattern(regex)));
    }
    return Status::Allowed;
}

ExplorerPrivacy::~ExplorerPrivacy()
{
    if (events >= 0)
        close(events);
}

bool ExplorerPrivacy::watch(const QString &path, const QByteArray &child)
{
    const int wd = inotify_add_watch(events, QFile::encodeName(path).constData(),
        changes | (child.isEmpty() ? 0 : (children | IN_ONLYDIR)) | IN_DONT_FOLLOW | IN_MASK_ADD);
    if (wd < 0)
        return false;
    watched[wd].insert(child);
    return true;
}

bool ExplorerPrivacy::unchanged() const
{
    alignas(inotify_event) char buffer[4096];
    for (;;) {
        const ssize_t n = read(events, buffer, sizeof(buffer));
        if (n < 0)
            return errno == EAGAIN;
        if (!n)
            return false;
        for (ssize_t pos = 0; pos < n;) {
            const auto *ev = reinterpret_cast<const inotify_event *>(buffer + pos);
            if (!ev->len || ev->mask & IN_Q_OVERFLOW || watched.value(ev->wd).contains(QByteArray(ev->name)))
                return false;
            pos += sizeof(inotify_event) + ev->len;
        }
    }
}

std::optional<ExplorerPrivacy::Snapshot> ExplorerPrivacy::observe(const QStringList &paths)
{
    Snapshot result;
    qsizetype total = 0;
    for (const auto &path : paths) {
        if (!path.startsWith(u'/') || path != QDir::cleanPath(path) || path.contains(u'\0'))
            return std::nullopt;
        const auto parts = path.mid(1).split(u'/');
        QString parent = QStringLiteral("/");
        struct stat info;
        bool absent = false;
        for (const auto &part : parts) {
            if (!watch(parent, QFile::encodeName(part)))
                return std::nullopt;
            if (parent.size() > 1)
                parent += u'/';
            parent += part;
            if (lstat(QFile::encodeName(parent).constData(), &info) != 0) {
                if (errno != ENOENT)
                    return std::nullopt;
                absent = true;
                break;
            }
            // Do not synthesize a different canonical layer or treat a dangling link as absence.
            if (S_ISLNK(info.st_mode))
                return std::nullopt;
        }
        if (absent)
            continue;
        if (!S_ISREG(info.st_mode) || !watch(path, {}))
            return std::nullopt;
        const Fd fd{open(QFile::encodeName(path).constData(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)};
        struct stat opened;
        QFile file;
        if (fd.value < 0 || fstat(fd.value, &opened) != 0 || !S_ISREG(opened.st_mode)
            || info.st_dev != opened.st_dev || info.st_ino != opened.st_ino || !opened.st_ino
            || opened.st_size > maxInput || (path == mode && opened.st_uid != geteuid())
            || !file.open(fd.value, QIODevice::ReadOnly))
            return std::nullopt;
        auto bytes = file.read(maxInput + 1);
        total += bytes.size();
        if (file.error() != QFileDevice::NoError || bytes.size() != opened.st_size || total > maxSnapshot)
            return std::nullopt;
        result.insert(path, {std::move(bytes), opened.st_dev, opened.st_ino});
    }
    return result;
}

ExplorerPrivacy::Status ExplorerPrivacy::check()
{
    if (!snapshot)
        return policy.value_or(Status::Unavailable);
    if (!policy)
        policy = readPolicy();
    if ((checkActivity && *policy == Status::Allowed && currentActivity() != activity)
        || !unchanged() || observe(QStringList{mode} + sources) != snapshot || !unchanged()) {
        snapshot.reset();
        policy = Status::Unavailable;
    }
    return *policy;
}

bool ExplorerPrivacy::unfiltered(const QString &path) const
{
    return std::ranges::none_of(filters, [&](const auto &filter) {
        return !filter.isValid() || filter.match(path).hasMatch();
    });
}

bool ExplorerPrivacy::allows(const QString &path) const
{
    if (!snapshot || policy != Status::Allowed || !unfiltered(path))
        return false;
    const auto canonical = QFileInfo(path).canonicalFilePath();
    return !canonical.isEmpty() && unfiltered(canonical);
}

bool ExplorerPrivacy::bindDestination(const QString &path)
{
    if (!snapshot || !path.startsWith(u'/') || path.startsWith(QLatin1String("//"))
        || path.contains(u'\0') || path != QDir::cleanPath(path))
        return false;
    // Only record paths we can witness through the listing. A symlink may resolve to a
    // different folder by the time KIO lists it; never defer that decision to the writer.
    QString parent = QStringLiteral("/");
    for (const auto &part : path.mid(1).split(u'/', Qt::SkipEmptyParts)) {
        if (!watch(parent, QFile::encodeName(part)))
            return false;
        if (parent.size() > 1)
            parent += u'/';
        parent += part;
        struct stat info;
        if (lstat(QFile::encodeName(parent).constData(), &info) != 0 || !S_ISDIR(info.st_mode))
            return false;
    }
    if (check() != Status::Allowed || !unfiltered(path))
        return false;
    destination = path;
    return true;
}

bool ExplorerPrivacy::allowsVisit(const QString &path) const
{
    return snapshot && policy == Status::Allowed && !destination.isEmpty() && path == destination;
}
