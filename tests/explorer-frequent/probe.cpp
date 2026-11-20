#include "ExplorerFrequent.h"
#include <QCoreApplication>
#include <QFile>
#include <QSaveFile>
#include <QUrl>
#include <cstdio>
#include <fcntl.h>
#include <unistd.h>

static void beforeSave()
{
    const auto history = qgetenv("TEST_SWAP_HISTORY");
    if (!history.isEmpty()) {
        const auto fixture = qgetenv("TEST_SWAP_FIXTURE");
        if (unlink(history.constData()) || symlink(fixture.constData(), history.constData()))
            qFatal("could not replace the disposable history entry after reading it");
    }
    const auto path = qEnvironmentVariable("TEST_BEFORE_COMMIT");
    if (!path.isEmpty()) {
        QFile policy(path);
        if (!policy.open(QIODevice::Append)
            || policy.write("what-to-remember=2\n") != 19 || !policy.flush())
            qFatal("could not flip test policy before the history commit");
    }
}

extern "C" bool __real__ZN9QSaveFile4openE6QFlagsIN13QIODeviceBase12OpenModeFlagEE(QSaveFile *, QIODevice::OpenMode);
extern "C" bool __wrap__ZN9QSaveFile4openE6QFlagsIN13QIODeviceBase12OpenModeFlagEE(QSaveFile *file, QIODevice::OpenMode mode)
{
    beforeSave();
    return __real__ZN9QSaveFile4openE6QFlagsIN13QIODeviceBase12OpenModeFlagEE(file, mode);
}

// The legacy save and the directory-relative save each reach this fixture after readVisits.
#define WRAP_OPENAT(name) \
extern "C" int __real_##name(int dir, const char *path, int flags, ...); \
extern "C" int __wrap_##name(int dir, const char *path, int flags, ...) \
{ \
    if (!(flags & O_CREAT) && (flags & O_TMPFILE) != O_TMPFILE) \
        return __real_##name(dir, path, flags); \
    beforeSave(); \
    return __real_##name(dir, path, flags, 0600); \
}
WRAP_OPENAT(openat)
WRAP_OPENAT(openat64)

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    const auto args = app.arguments();
    if (args.size() != 3)
        return 2;
    const auto path = args[2];
    if (args[1] == QLatin1String("record"))
        ExplorerFrequent::record(QUrl::fromLocalFile(path));
    else if (args[1] == QLatin1String("rows"))
        for (const auto &row : ExplorerFrequent::folders(10).value_or(QStringList{}))
            puts(qPrintable(row));
    else if (args[1] == QLatin1String("activate"))
        puts(ExplorerFrequent::listing({path}) == ExplorerFrequent::Listing::Valid ? "yes" : "no");
    else
        return 2;
}
