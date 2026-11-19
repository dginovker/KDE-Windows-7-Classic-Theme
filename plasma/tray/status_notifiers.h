#pragma once

#include <QDBusMessage>
#include <QHash>
#include <QQuickItem>
#include <QPointer>
#include <QObject>
#include <QVariantMap>

class KIconLoader;

class StatusNotifiers : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList items READ items NOTIFY itemsChanged)
public:
    explicit StatusNotifiers(QObject *parent);
    QVariantList items() const;
    Q_INVOKABLE void trigger(const QString &address, const QString &method, QQuickItem *anchor);
    Q_INVOKABLE void scroll(const QString &address, int delta, const QString &orientation);

Q_SIGNALS:
    void itemsChanged();
    void menuRequested(const QString &address, const QString &path, QQuickItem *anchor, int x, int y);

private Q_SLOTS:
    void registered(const QString &address);
    void unregistered(const QString &address);
    void updateItem(const QDBusMessage &signal);

private:
    void attach(const QString &owner);
    void readItem(const QString &address);
    QHash<QString, QVariantMap> m_items;
    QString m_owner;
    quint64 m_generation = 0;
    quint64 m_revision = 0;
    QHash<QString, quint64> m_reads;
    QHash<QString, QPointer<KIconLoader>> m_loaders;
};
