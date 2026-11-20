#include <QQmlExtensionPlugin>
#include "ClassicItem.h"
#include "ClassicColors.h"
#include "ExplorerFrequent.h"
#include <KIO/Global>
#include <QDir>
#include <QFileInfo>
#include <QFutureWatcher>
#include <QProcess>
#include <QVariantMap>
#include <QtConcurrentRun>

class ExplorerLocations : public QObject {
    Q_OBJECT
public:
    explicit ExplorerLocations(QObject *parent = nullptr) : QObject(parent)
    {
        connect(&check, &QFutureWatcher<Rows>::finished, this, [this] {
            checking = false;
            const auto result = check.result();
            emit checked(result.ticket, result.status == Listing::Valid, result.status == Listing::Unavailable, result.rows);
        });
        connect(&launch, &QFutureWatcher<QString>::finished, this, [this] {
            opening = false;
            emit opened(launch.result());
        });
    }

    Q_INVOKABLE bool query(int ticket, int limit, const QStringList &visible)
    {
        // A stuck mount must not accumulate work on successive timer ticks or menu openings.
        if (checking)
            return false;
        checking = true;
        check.setFuture(QtConcurrent::run([ticket, limit, visible]() -> Rows {
            if (!visible.isEmpty())
                return {ticket, ExplorerFrequent::listing(visible), {}};
            const auto paths = ExplorerFrequent::folders(limit);
            if (!paths)
                return {ticket, Listing::Unavailable, {}};
            if (paths->isEmpty())
                return {ticket, Listing::Hidden, {}};
            QVariantList rows;
            for (const auto &path : *paths) {
                const QString name = path == QLatin1String("/") ? QStringLiteral("Computer") : QFileInfo(path).fileName();
                rows.append(QVariantMap{{QStringLiteral("path"), path}, {QStringLiteral("name"), name},
                                        {QStringLiteral("icon"), KIO::iconNameForUrl(QUrl::fromLocalFile(path))}});
            }
            // Icon discovery can touch the filesystem; check policy and availability again after it.
            const auto status = ExplorerFrequent::listing(*paths);
            return {ticket, status, status == Listing::Valid ? rows : QVariantList{}};
        }));
        return true;
    }

    Q_INVOKABLE void open(const QString &path)
    {
        if (opening) {
            emit opened(tr("A Frequent folder is already being checked."));
            return;
        }
        opening = true;
        launch.setFuture(QtConcurrent::run([path]() -> QString {
            if (!ExplorerFrequent::available(path))
                return tr("This folder is no longer available.");
            if (ExplorerFrequent::listing({path}) != Listing::Valid)
                return tr("This folder is no longer in Explorer Frequent history.");
            // KDE's ApplicationLauncherJob adds URLs to its shared recent documents.
            if (!QProcess::startDetached(QStringLiteral(WIN7_EXPLORER), {QStringLiteral("--frequent-folder"), path}, QDir::homePath()))
                return tr("The installed Windows Explorer could not be started.");
            return {};
        }));
    }

signals:
    void checked(int ticket, bool valid, bool unavailable, const QVariantList &rows);
    void opened(const QString &error);

private:
    using Listing = ExplorerFrequent::Listing;
    struct Rows {
        int ticket;
        Listing status;
        QVariantList rows;
    };
    bool checking = false;
    bool opening = false;
    QFutureWatcher<Rows> check;
    QFutureWatcher<QString> launch;
};

void registerTaskWindowIcon(const char *uri);
void registerPopupMenuShadow(const char *uri);
class ClassicPluginV2 : public QQmlExtensionPlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override { qmlRegisterType<ClassicV2::ClassicItem>(uri,1,0,"Raster");
        qmlRegisterSingletonType<ClassicV2::ClassicColors>(uri,1,0,"Palette",[](QQmlEngine *,QJSEngine *) -> QObject * { return new ClassicV2::ClassicColors; });
        registerTaskWindowIcon(uri);
        registerPopupMenuShadow(uri);
        qmlRegisterType<ExplorerLocations>(uri, 1, 0, "ExplorerLocations");
    }
};
#include "Plugin.moc"
