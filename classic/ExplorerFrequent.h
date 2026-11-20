#pragma once

#include <QStringList>
#include <optional>

class QUrl;
class ExplorerPrivacy;

namespace ExplorerFrequent {
bool available(const QString &path);
bool candidate(const QUrl &folder);
void record(const QUrl &folder);
void record(const QUrl &folder, ExplorerPrivacy &permit);
std::optional<QStringList> folders(int limit);
enum class Listing { Valid, Hidden, Unavailable };
Listing listing(const QStringList &paths);
}
