#pragma once

class KFileItemList;
class QUrl;
class QWidget;

void showExplorerProperties(const KFileItemList &items, QWidget *parent);
void showExplorerProperties(const QUrl &url, QWidget *parent);
