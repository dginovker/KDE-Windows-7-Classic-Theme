#pragma once
#include <QObject>

class QQuickWindow;

void openNotifierMenu(QObject *lifetime, QQuickWindow *parent, const QString &address, const QString &path, int x, int y);
