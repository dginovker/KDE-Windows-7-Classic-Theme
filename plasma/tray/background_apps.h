#pragma once

#include <QObject>
#include <QHash>
#include <QVariantList>

class QQuickItem;
class QDBusMessage;

class BackgroundApps : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList items READ items NOTIFY itemsChanged)
public:
    explicit BackgroundApps(QObject *parent);
    QVariantList items() const { return m_items; }
    Q_INVOKABLE void open(const QString &id, QQuickItem *anchor);
    Q_INVOKABLE void menu(const QString &id, QQuickItem *anchor);

Q_SIGNALS:
    void itemsChanged();

private Q_SLOTS:
    void propertiesChanged(const QString &interface, const QVariantMap &changed, const QStringList &invalidated);

private:
    void refresh();
    void read(const QVariant &value);
    void stop(const QString &id);
    QVariantList m_items;
    QHash<QString, QStringList> m_instances;
    quint64 m_revision = 0;
};
