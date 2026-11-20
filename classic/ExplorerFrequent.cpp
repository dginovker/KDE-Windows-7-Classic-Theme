#include "ExplorerFrequent.h"

#include "ExplorerPrivacy.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QUuid>
#include <QSet>
#include <QStandardPaths>
#include <QThread>
#include <QUrl>

#include <algorithm>
#include <limits>
#include <optional>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
using Policy = ExplorerPrivacy::Status;
using Listing = ExplorerFrequent::Listing;
constexpr int maxEntries = 32;
constexpr int maxBytes = 1024 * 1024;
constexpr auto fileName = "frequent.json";

struct Visit {
    QString path;
    int count;
};

QString stateRoot()
{
    return QStandardPaths::writableLocation(QStandardPaths::GenericStateLocation);
}

struct Fd {
    int value;
    ~Fd() { if (value >= 0) close(value); }
};

bool checked(int fd, mode_t type, mode_t permissions, off_t size = 0)
{
    struct stat stat;
    return fd >= 0 && fstat(fd, &stat) == 0 && (stat.st_mode & S_IFMT) == type && stat.st_uid == geteuid()
        && (!permissions || (stat.st_mode & 07777) == permissions)
        && (!size || (stat.st_nlink == 1 && stat.st_size <= size));
}

QByteArray readInput(int fd, int limit)
{
    QFile file;
    return file.open(fd, QIODevice::ReadOnly) ? file.read(limit + 1) : QByteArray{};
}

bool pathShape(const QString &path)
{
    return path.startsWith(u'/') && !path.startsWith(QLatin1String("//")) && !path.contains(u'\0')
        && path == QDir::cleanPath(path);
}

std::optional<QList<Visit>> readVisits(int dir)
{
    const Fd fd{openat(dir, fileName, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK)};
    if (fd.value < 0 && errno == ENOENT)
        return QList<Visit>{};
    if (!checked(fd.value, S_IFREG, 0600, maxBytes))
        return std::nullopt;
    const auto bytes = readInput(fd.value, maxBytes);
    const auto json = QJsonDocument::fromJson(bytes);
    if (bytes.size() > maxBytes || !json.isArray() || json.array().size() > maxEntries)
        return std::nullopt;
    QList<Visit> visits;
    QSet<QString> paths;
    for (const auto &entry : json.array()) {
        const auto pair = entry.toArray();
        if (pair.size() != 2)
            return std::nullopt;
        const auto path = pair.at(0).toString();
        const int count = pair.at(1).toInt();
        if (!pathShape(path) || count < 1 || paths.contains(path))
            return std::nullopt;
        paths.insert(path);
        visits.append({path, count});
    }
    return visits;
}

QString historyDir()
{
    return stateRoot() + QStringLiteral("/win7-explorer");
}

int openHistory(bool create)
{
    const auto path = QFile::encodeName(historyDir());
    if (create && mkdir(path.constData(), 0700) != 0 && errno != EEXIST)
        return -1;
    return open(path.constData(), O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
}

std::optional<QList<Visit>> storedVisits()
{
    const Fd dir{openHistory(false)};
    if (dir.value < 0 && errno == ENOENT)
        return QList<Visit>{};
    auto visits = checked(dir.value, S_IFDIR, 0700) ? readVisits(dir.value) : std::nullopt;
    if (!visits)
        qWarning("win7-explorer: refusing to read invalid Frequent history");
    return visits;
}

}

bool ExplorerFrequent::available(const QString &path)
{
    if (!pathShape(path))
        return false;
    const QFileInfo info(path);
    return info.isDir() && info.isReadable() && info.isExecutable();
}

bool ExplorerFrequent::candidate(const QUrl &folder)
{
    return folder.isLocalFile() && folder.authority().isEmpty() && !folder.hasQuery() && !folder.hasFragment();
}

void ExplorerFrequent::record(const QUrl &folder)
{
    ExplorerPrivacy permit;
    if (candidate(folder) && permit.bindDestination(folder.toLocalFile()))
        record(folder, permit);
}

void ExplorerFrequent::record(const QUrl &folder, ExplorerPrivacy &permit)
{
    const QString path = folder.toLocalFile();
    if (!candidate(folder) || permit.check() != Policy::Allowed || !permit.allowsVisit(path) || !available(path))
        return;

    const Fd dir{openHistory(true)};
    if (!checked(dir.value, S_IFDIR, 0700)) {
        qWarning("win7-explorer: Frequent state directory must be owned by you and mode 0700");
        return;
    }
    // Lock the private directory so there is no separate lock artefact to follow or clean up.
    int retries = 20;
    while (flock(dir.value, LOCK_EX | LOCK_NB) != 0) {
        if (errno != EWOULDBLOCK || --retries == 0) {
            qWarning("win7-explorer: cannot lock Frequent history");
            return;
        }
        QThread::msleep(10);
    }
    auto visits = readVisits(dir.value);
    if (!visits) {
        qWarning("win7-explorer: invalid Frequent history; not modified");
        return;
    }
    auto old = std::ranges::find(*visits, path, &Visit::path);
    int count = 1;
    if (old != visits->end()) {
        count = old->count + (old->count < std::numeric_limits<int>::max());
        visits->erase(old);
    }
    // Keep aggregate counts in last-used order, not an event log.
    visits->prepend({path, count});
    if (visits->size() > maxEntries)
        visits->resize(maxEntries);
    QJsonArray json;
    for (const auto &visit : *visits)
        json.append(QJsonArray{visit.path, visit.count});
    const QByteArray data = QJsonDocument(json).toJson(QJsonDocument::Compact);
    // Give the staging file an exclusive name in the locked directory; renameat never resolves the destination entry.
    const QByteArray temp = ".frequent-" + QUuid::createUuid().toByteArray(QUuid::Id128);
    if (data.size() > maxBytes) {
        qWarning("win7-explorer: Frequent history exceeds its size limit");
        return;
    }
    const Fd fd{openat(dir.value, temp.constData(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600)};
    if (fd.value < 0) {
        qErrnoWarning("win7-explorer: cannot create Frequent history staging file");
        return;
    }
    QFile file;
    if (fchmod(fd.value, 0600) != 0 || !file.open(fd.value, QIODevice::WriteOnly)
        || file.write(data) != data.size() || !file.flush() || fsync(fd.value) != 0) {
        qWarning("win7-explorer: cannot write Frequent history staging file");
    } else if (permit.allowsVisit(path) && permit.check() == Policy::Allowed) {
        if (renameat(dir.value, temp.constData(), dir.value, fileName) == 0)
            return;
        qErrnoWarning("win7-explorer: cannot commit Frequent history");
    }
    if (unlinkat(dir.value, temp.constData(), 0) != 0)
        qErrnoWarning("win7-explorer: cannot remove Frequent history staging file");
}

std::optional<QStringList> ExplorerFrequent::folders(int limit)
{
    ExplorerPrivacy permit;
    const auto status = permit.check();
    if (status == Policy::Denied || limit <= 0)
        return QStringList{};
    if (status == Policy::Unavailable)
        return std::nullopt;
    auto visits = storedVisits();
    if (!visits)
        return std::nullopt;
    std::stable_sort(visits->begin(), visits->end(), [](const Visit &a, const Visit &b) { return a.count > b.count; });
    QStringList paths;
    for (const auto &visit : *visits) {
        if (visit.count >= 2 && available(visit.path) && permit.allows(visit.path))
            paths.append(visit.path);
        if (paths.size() == limit)
            break;
    }
    if (permit.check() != Policy::Allowed)
        return std::nullopt;
    return paths;
}

ExplorerFrequent::Listing ExplorerFrequent::listing(const QStringList &paths)
{
    ExplorerPrivacy permit;
    const auto status = permit.check();
    if (status == Policy::Denied)
        return Listing::Hidden;
    if (status == Policy::Unavailable)
        return Listing::Unavailable;
    const auto visits = storedVisits();
    if (!visits)
        return Listing::Unavailable;
    const bool listed = std::ranges::all_of(paths, [&visits, &permit](const QString &path) {
        return available(path) && permit.allows(path) && std::ranges::any_of(*visits, [&path](const Visit &visit) { return visit.count >= 2 && visit.path == path; });
    });
    if (permit.check() != Policy::Allowed)
        return Listing::Unavailable;
    return listed ? Listing::Valid : Listing::Hidden;
}
