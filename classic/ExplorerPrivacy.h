#pragma once

#include <QByteArray>
#include <QHash>
#include <QMap>
#include <QSet>
#include <QStringList>
#include <QRegularExpression>
#include <optional>

class QDBusMessage;

// The permit covers an observation, not a lock on Plasma's configuration writers.
class ExplorerPrivacy
{
public:
    ExplorerPrivacy();
    ~ExplorerPrivacy();
    ExplorerPrivacy(const ExplorerPrivacy &) = delete;
    ExplorerPrivacy &operator=(const ExplorerPrivacy &) = delete;
    enum class Status { Allowed, Denied, Unavailable };
    Status check();
    bool allows(const QString &path) const;
    bool bindDestination(const QString &path);
    bool allowsVisit(const QString &path) const;
    QString visitActivity() const { return activity; }
    static QDBusMessage activityQuery();

private:
    struct Input {
        QByteArray bytes;
        quint64 device = 0, inode = 0;
        bool operator==(const Input &) const = default;
    };
    using Snapshot = QMap<QString, Input>;
    std::optional<Snapshot> observe(const QStringList &paths);
    bool unchanged() const;
    bool watch(const QString &path, const QByteArray &child);
    Status readPolicy();
    int events;
    QHash<int, QSet<QByteArray>> watched;
    QStringList sources, roots;
    bool checkActivity = false;
    std::optional<Status> policy;
    QList<QRegularExpression> filters;
    QString mode, activity, destination;
    bool unfiltered(const QString &path) const;
    std::optional<Snapshot> snapshot;
};
