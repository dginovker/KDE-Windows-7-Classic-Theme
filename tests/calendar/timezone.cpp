#include <QtQuickTest/quicktest.h>
#include <QQmlContext>
#include <QQmlEngine>
#include <ctime>

class TimeZoneSetup : public QObject {
    Q_OBJECT
public:
    Q_INVOKABLE void setZone(const QByteArray &ianaId)
    {
        qputenv("TZ", ianaId);
        tzset();
    }
public slots:
    void qmlEngineAvailable(QQmlEngine *engine)
    {
        engine->rootContext()->setContextProperty("testTimeZone", this);
    }
};
QUICK_TEST_MAIN_WITH_SETUP(calendar, TimeZoneSetup)
#include "timezone.moc"
