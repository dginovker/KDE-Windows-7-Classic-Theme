// Windows 7 Classic Explorer: Explorer's chrome, laid out to the pixel geometry of reference/screenshots/w7-explorer*.png
// and drawn with Windows' own art (explorer/assets, see reference/tools/extract-assets.py), around KDE's KIO file
// widgets, which do the actual file management.
#include "ClassicPrimitives.h"
#include <KConfig>
#include <KConfigGroup>
#include <KDirModel>
#include <KDirOperator>
#include <KFileItemActions>
#include <KFileItemListProperties>
#include <KIO/FileUndoManager>
#include <KIO/Global>
#include <KIO/JobUiDelegateFactory>
#include <KIO/OpenUrlJob>
#include <KIO/Paste>
#include <KIO/PasteJob>
#include <KIO/SimpleJob>
#include <KIO/CopyJob>
#include <KPropertiesDialog>
#include <KUrlMimeData>
#include <KUser>

#include <QAbstractItemView>
#include <QActionGroup>
#include <QApplication>
#include <QClipboard>
#include <QCommandLineParser>
#include <QCryptographicHash>
#include <QDir>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QListView>
#include <QMainWindow>
#include <QMenu>
#include <QMimeData>
#include <QMouseEvent>
#include <QPainter>
#include <QSortFilterProxyModel>
#include <QScrollBar>
#include <QSignalBlocker>
#include <QSplitter>
#include <QStandardPaths>
#include <QTimer>
#include <QTreeView>
#include <QVBoxLayout>

namespace classic {
const auto &face=Classic::Face, &shadow=Classic::Shadow3D, &darkShadow=Classic::DarkShadow3D,
           &light=Classic::Highlight3D, &highlight=Classic::Selection, &text=Classic::Text;
}

static QPixmap asset(const QString &name)
{
    QPixmap pixmap(QStringLiteral(":/explorer/%1.png").arg(name));
    if (pixmap.isNull())
        qFatal("missing Explorer asset %s", qPrintable(name));
    return pixmap;
}

// Every size Windows ships, so scaled screens get real pixels instead of an upscaled 16px icon.
static QIcon assetIcon(const QString &name)
{
    QIcon icon;
    for (int size : {16, 20, 22, 24, 32, 48, 64, 96, 128, 256}) {
        const QString file = QStringLiteral(":/explorer/%1-%2.png").arg(name).arg(size);
        if (QFile::exists(file))
            icon.addFile(file);
    }
    if (icon.isNull())
        qFatal("missing Explorer icon %s", qPrintable(name));
    return icon;
}

// Solid downward triangle, `width` pixels wide at the top, as Explorer draws its menu arrows.
static void arrow(QPainter &p, int x, int y, int width, const QColor &color = classic::text)
{
    Classic::drawArrow(p, QPoint(x,y), width, color);
}

static void etched(QPainter &p, const QRect &r) { Classic::drawEdge(p,r,Classic::Etched); }
static void edge(QPainter &p, const QRect &r, const QColor &topLeft, const QColor &bottomRight)
{
    if(topLeft==Classic::Shadow3D && bottomRight==Classic::Highlight3D)
        Classic::drawEdge(p,r,Classic::SunkenOuter);
    else if(topLeft==Classic::Highlight3D && bottomRight==Classic::Shadow3D)
        Classic::drawEdge(p,r,Classic::RaisedInner);
    else if(topLeft==Classic::DarkShadow3D && bottomRight==Classic::Face)
        Classic::drawEdge(p,r,Classic::SunkenInner);
    else
        qFatal("unsupported Explorer edge color pair");
}

// KDirOperator's file-dialog menu needs separate Explorer background and item actions.
class Files : public KDirOperator
{
public:
    using KDirOperator::KDirOperator;
    std::function<void(const KFileItem &, const QPoint &)> onMenu;

protected:
    void activatedMenu(const KFileItem &item, const QPoint &pos) override
    {
        // KDirModel returns the directory itself for an invalid (background) index, not a null item.
        const bool background = item.url().matches(url(), QUrl::StripTrailingSlash);
        updateSelectionDependentActions();
        onMenu(background ? KFileItem() : item, pos);
    }
};

// A row of clickable parts painted by the widget itself; parts report hover and press so they can be drawn per state.
class Painted : public QWidget
{
public:
    struct Part {
        QRect rect;
        std::function<void()> click;
        bool enabled = true;
    };

    Painted()
    {
        setMouseTracking(true);
        setAttribute(Qt::WA_OpaquePaintEvent);
    }

protected:
    QList<Part> parts;
    int hovered = -1, pressed = -1;

    int partAt(const QPoint &pos) const
    {
        for (int i = 0; i < parts.size(); ++i)
            if (parts[i].enabled && parts[i].rect.contains(pos))
                return i;
        return -1;
    }
    void mouseMoveEvent(QMouseEvent *e) override
    {
        if (int part = partAt(e->position().toPoint()); part != hovered) {
            hovered = part;
            update();
        }
    }
    void leaveEvent(QEvent *) override
    {
        hovered = -1;
        update();
    }
    void mousePressEvent(QMouseEvent *e) override
    {
        pressed = e->button() == Qt::LeftButton ? partAt(e->position().toPoint()) : -1;
        update();
        // Menus open on press, as Windows' do.
        if (pressed >= 0 && pressOpens(pressed)) {
            const int part = std::exchange(pressed, -1);
            parts[part].click();
            update();
        }
    }
    void mouseReleaseEvent(QMouseEvent *e) override
    {
        const int part = std::exchange(pressed, -1);
        update();
        if (part >= 0 && part == partAt(e->position().toPoint()))
            parts[part].click();
    }
    virtual bool pressOpens(int) const { return false; }
};

// Back/Forward, the breadcrumb address bar with Refresh, and the search box: rows 1-36 of the reference client area.
class NavigationBand : public Painted
{
public:
    std::function<void(const QUrl &)> go;
    std::function<void()> back, forward, refresh;
    std::function<QList<QUrl>()> history;
    std::function<QList<std::pair<QString, QUrl>>()> places;
    QLineEdit *search = new QLineEdit(this);

    NavigationBand()
    {
        setFixedHeight(36);
        search->setFrame(false);
        search->setTextMargins(5, 0, 0, 0);
        // Windows draws the cue text in the window text color, not greyed.
        QPalette palette = search->palette();
        palette.setColor(QPalette::PlaceholderText, classic::text);
        search->setPalette(palette);
        address->setFrame(false);
        address->hide();
        connect(address, &QLineEdit::returnPressed, this, [this] {
            go(QUrl::fromUserInput(address->text(), QDir::currentPath(), QUrl::AssumeLocalFile));
            address->hide();
        });
        connect(address, &QLineEdit::editingFinished, address, &QWidget::hide);
    }

    void setState(const QUrl &url, bool canBack, bool canForward)
    {
        location = url;
        backEnabled = canBack;
        forwardEnabled = canForward;
        address->hide();
        layoutParts();
    }

    void editAddress()
    {
        address->setText(location.isLocalFile() ? location.toLocalFile() : location.toDisplayString());
        address->setGeometry(addressBox().adjusted(2, 2, -23, -1));
        address->show();
        address->selectAll();
        address->setFocus();
    }

protected:
    void resizeEvent(QResizeEvent *) override
    {
        search->setGeometry(width() - 244, 9, 219, 18);
        layoutParts();
    }

    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.fillRect(rect(), classic::face);
        etched(p, QRect(0, 0, width(), 36));
        const bool hasHistory = backEnabled || forwardEnabled;
        p.drawPixmap(2, 2, asset(state(BackPart, backEnabled, QStringLiteral("back"))));
        p.drawPixmap(32, 2, asset(forwardEnabled ? state(ForwardPart, true, QStringLiteral("forward"))
                                                 : hasHistory ? QStringLiteral("forward-disabled-history") : QStringLiteral("forward-disabled")));

        const QRect box = addressBox();
        edge(p, box, classic::shadow, classic::light);
        p.drawPixmap(box.left() + 2, 9, QIcon::fromTheme(QStringLiteral("folder")).pixmap(16));
        for (int i = 0; i < crumbs.size(); ++i) {
            arrow(p, crumbs[i].arrow.left(), 16, 5);
            if (i)
                p.drawText(QPoint(crumbs[i].text.left(), 21), crumbs[i].label);
        }
        arrow(p, box.right() - 39, 16, 7);  // recent locations
        p.drawPixmap(box.right() - 21, 8, asset(QStringLiteral("refresh")));

        const QRect field(width() - 246, 7, 223, 22);
        edge(p, field, classic::shadow, classic::light);
        edge(p, field.adjusted(1, 1, -1, -1), classic::darkShadow, classic::face);
        p.drawPixmap(width() - 23, 7, asset(hovered == SearchPart ? QStringLiteral("search-hot") : QStringLiteral("search-normal")));
    }

    bool pressOpens(int part) const override { return part >= HistoryPart; }

private:
    enum { BackPart, ForwardPart, SearchPart, RefreshPart, EditPart, HistoryPart };  // crumb parts follow HistoryPart
    struct Crumb {
        QString label;
        QUrl url;
        QRect text, arrow;
    };
    QUrl location;
    bool backEnabled = false, forwardEnabled = false;
    QList<Crumb> crumbs;
    QLineEdit *address = new QLineEdit(this);

    QRect addressBox() const { return QRect(74, 7, width() - 324, 22); }

    QString state(int part, bool enabled, const QString &name) const
    {
        if (!enabled)
            return name + QStringLiteral("-disabled");
        return name + (pressed == part ? QStringLiteral("-pressed") : hovered == part ? QStringLiteral("-hot") : QStringLiteral("-normal"));
    }

    // Windows names the home folder after the user and everything else from "Computer" down.
    QList<Crumb> crumbsFor(const QUrl &url) const
    {
        QList<Crumb> list;
        if (!url.isLocalFile()) {
            list.append({url.toDisplayString(), url, {}, {}});
            return list;
        }
        const QString path = QDir::cleanPath(url.toLocalFile());
        QString base = QDir::homePath();
        if (path == base || path.startsWith(base + QLatin1Char('/'))) {
            const KUser user;
            const QString name = user.property(KUser::FullName).toString();
            list.append({name.isEmpty() ? user.loginName() : name, QUrl::fromLocalFile(base), {}, {}});
        } else {
            base = QStringLiteral("/");
            list.append({QStringLiteral("Computer"), QUrl::fromLocalFile(base), {}, {}});
        }
        QString built = base;
        for (const QString &part : QStringView(path).mid(base.size()).toString().split(QLatin1Char('/'), Qt::SkipEmptyParts)) {
            built = QDir(built).filePath(part);
            list.append({part, QUrl::fromLocalFile(built), {}, {}});
        }
        return list;
    }

    void layoutParts()
    {
        const QRect box = addressBox();
        const QFontMetrics metrics(font());
        crumbs.clear();
        crumbs.append({QString(), QUrl(), {}, QRect(box.left() + 25, 13, 9, 11)});  // the places menu after the icon
        int x = box.left() + 36;
        for (Crumb crumb : crumbsFor(location)) {
            crumb.text = QRect(x, 10, metrics.horizontalAdvance(crumb.label), 15);
            crumb.arrow = QRect(crumb.text.right() + 8, 13, 9, 11);
            x = crumb.arrow.left() + 11;
            crumbs.append(crumb);
        }
        parts = {
            {QRect(2, 2, 30, 32), [this] { back(); }, backEnabled},
            {QRect(32, 2, 28, 32), [this] { forward(); }, forwardEnabled},
            {QRect(width() - 23, 7, 21, 21), [this] { search->setFocus(); }},
            {QRect(box.right() - 21, 8, 21, 20), [this] { refresh(); }},
            {box.adjusted(0, 0, -41, 0), [this] { editAddress(); }},
            {QRect(box.right() - 41, 8, 19, 20), [this, box] { menuOf(history(), QRect(box.left(), box.bottom(), 0, 0)); }, backEnabled || forwardEnabled},
        };
        for (int i = 0; i < crumbs.size(); ++i) {
            const Crumb crumb = crumbs[i];
            if (i)
                parts.insert(HistoryPart + 1, {crumb.text.adjusted(-3, -2, 3, 2), [this, crumb] { go(crumb.url); }});
            parts.insert(HistoryPart + 1, {crumb.arrow, [this, i, crumb] {
                                               if (!i) {
                                                   QMenu menu;
                                                   for (const auto &[name, url] : places())
                                                       menu.addAction(name, this, [this, url] { go(url); });
                                                   menu.exec(mapToGlobal(QPoint(crumb.arrow.left(), 28)));
                                                   return;
                                               }
                                               subfolderMenu(crumb.url, QPoint(crumb.arrow.left(), 28));
                                           }});
        }
        update();
    }

    void menuOf(const QList<QUrl> &urls, const QRect &at)
    {
        QMenu menu;
        for (const QUrl &url : urls)
            menu.addAction(url.isLocalFile() ? url.toLocalFile() : url.toDisplayString(), this, [this, url] { go(url); });
        menu.exec(mapToGlobal(at.topLeft()));
    }

    void subfolderMenu(const QUrl &url, const QPoint &at)
    {
        QMenu menu;
        if (!url.isLocalFile()) {
            menu.addAction(QStringLiteral("(not a local folder)"))->setEnabled(false);
        } else {
            for (const QFileInfo &dir : QDir(url.toLocalFile()).entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name | QDir::IgnoreCase))
                menu.addAction(dir.fileName(), this, [this, dir] { go(QUrl::fromLocalFile(dir.filePath())); });
        }
        menu.exec(mapToGlobal(at));
    }
};

// Organize, Include in library, Share with, New folder; view, preview pane and help on the right: rows 37-67.
class CommandBar : public Painted
{
public:
    struct Command {
        QString text;
        QIcon icon;
        QMenu *menu = nullptr;
        std::function<void()> act;
    };
    QList<Command> left, right;

    CommandBar() { setFixedHeight(31); }
    void relayout()
    {
        parts.clear();
        int x = 2;
        const QFontMetrics metrics(font());
        for (const Command &command : left) {
            const int width = 11 + metrics.horizontalAdvance(command.text) + (command.menu ? 15 : 0) + 10;
            parts.append({QRect(x, 2, width, 27), [this, command, x] { trigger(command, x); }});
            x += width;
        }
        // Right-aligned like the reference: view split button, preview pane, help.
        const int offsets[] = {115, 64, 36};
        for (int i = 0; i < right.size(); ++i) {
            const int x = width() - offsets[i];
            parts.append({QRect(x, 2, right[i].menu ? 47 : 26, 27), [this, i, x] { trigger(right[i], x); }});
        }
        update();
    }

protected:
    void resizeEvent(QResizeEvent *) override { relayout(); }
    bool pressOpens(int part) const override { return command(part).menu && !command(part).act; }

    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.fillRect(rect(), classic::face);
        for (int i = 0; i < parts.size(); ++i) {
            const Command &c = command(i);
            const QRect r = parts[i].rect;
            if (i == pressed)
                edge(p, r, classic::shadow, classic::light);
            else if (i == hovered)
                edge(p, r, classic::light, classic::shadow);
            if (c.icon.isNull()) {
                p.drawText(QPoint(r.left() + 11, 19), c.text);
                if (c.menu)
                    arrow(p, r.right() - 16, 13, 7);
            } else {
                p.drawPixmap(r.left() + 5, 7, c.icon.pixmap(16));
                if (c.menu)
                    arrow(p, r.left() + 34, 13, 7);
            }
        }
    }

private:
    const Command &command(int part) const { return part < left.size() ? left[part] : right[part - left.size()]; }
    void trigger(const Command &command, int x)
    {
        // A split button (icon and arrow): the icon acts, the arrow opens the menu.
        const QPoint cursor = mapFromGlobal(QCursor::pos());
        if (command.menu && (!command.act || cursor.x() >= x + 26))
            command.menu->exec(mapToGlobal(QPoint(x, 29)));
        else
            command.act();
    }
};

// Favorites, Libraries, Computer and Network with Windows' icons, rows and indents.
class NavigationPane : public Painted
{
public:
    struct Row {
        QString text, icon;
        QUrl url;
        bool child = false;
    };
    std::function<void(const QUrl &)> go;

    NavigationPane()
    {
        auto path = [](QStandardPaths::StandardLocation l) { return QUrl::fromLocalFile(QStandardPaths::writableLocation(l)); };
        rows = {
            {QStringLiteral("Favorites"), QStringLiteral("favorites"), QUrl()},
            {QStringLiteral("Desktop"), QStringLiteral("desktop"), path(QStandardPaths::DesktopLocation), true},
            {QStringLiteral("Downloads"), QStringLiteral("downloads"), path(QStandardPaths::DownloadLocation), true},
            {QStringLiteral("Recent Places"), QStringLiteral("recent-places"), QUrl(QStringLiteral("recentlyused:/locations")), true},
            {},
            {QStringLiteral("Libraries"), QStringLiteral("libraries"), path(QStandardPaths::HomeLocation)},
            {QStringLiteral("Documents"), QStringLiteral("library-documents"), path(QStandardPaths::DocumentsLocation), true},
            {QStringLiteral("Music"), QStringLiteral("library-music"), path(QStandardPaths::MusicLocation), true},
            {QStringLiteral("Pictures"), QStringLiteral("library-pictures"), path(QStandardPaths::PicturesLocation), true},
            {QStringLiteral("Videos"), QStringLiteral("library-videos"), path(QStandardPaths::MoviesLocation), true},
            {},
            {QStringLiteral("Computer"), QStringLiteral("computer"), QUrl::fromLocalFile(QStringLiteral("/"))},
            {},
            {QStringLiteral("Network"), QStringLiteral("network"), QUrl(QStringLiteral("remote:/"))},
        };
        setFocusPolicy(Qt::ClickFocus);
    }

    QList<std::pair<QString, QUrl>> places() const
    {
        QList<std::pair<QString, QUrl>> list;
        for (const Row &row : rows)
            if (row.url.isValid())
                list.append({row.text, row.url});
        return list;
    }

    // Windows keeps the matching place selected and otherwise Favorites, as in the reference.
    void setLocation(const QUrl &url)
    {
        selected = 0;
        for (int i = 0; i < rows.size(); ++i)
            if (rows[i].url.isValid() && rows[i].url.adjusted(QUrl::StripTrailingSlash) == url.adjusted(QUrl::StripTrailingSlash))
                selected = i;
        layoutRows();
    }

protected:
    void resizeEvent(QResizeEvent *) override { layoutRows(); }
    void focusInEvent(QFocusEvent *) override { update(); }
    void focusOutEvent(QFocusEvent *) override { update(); }

    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.fillRect(rect(), classic::light);
        for (int i = 0; i < rows.size(); ++i) {
            const Row &row = rows[i];
            if (row.text.isEmpty())
                continue;
            const int y = 9 + 19 * i;
            const bool active = i == selected && hasFocus();
            if (i == selected)
                p.fillRect(0, y, width(), 19, active ? classic::highlight : classic::face);
            const int indent = row.child ? 30 : 20;
            p.drawPixmap(indent, y + 1, assetIcon(row.icon).pixmap(16));
            p.setPen(active ? classic::light : classic::text);
            p.drawText(QPoint(indent + 20, y + 14), row.text);
        }
    }

private:
    QList<Row> rows;
    int selected = 0;

    void layoutRows()
    {
        parts.clear();
        for (int i = 0; i < rows.size(); ++i) {
            const Row row = rows[i];
            parts.append({QRect(0, 9 + 19 * i, width(), 19), [this, row, i] {
                              if (!row.url.isValid())
                                  return;
                              selected = i;
                              go(row.url);
                          },
                          !row.text.isEmpty()});
        }
        update();
    }
};

// The item count under the file view, with the folder's own icon: rows 486-533 of the reference client area.
class DetailsPane : public QWidget
{
public:
    QString text;
    QIcon icon;
    DetailsPane() { setFixedHeight(48); }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.fillRect(rect(), classic::light);
        p.drawPixmap(17, -2, icon.pixmap(48));  // Windows lets the top two rows run under the bar above
        p.drawText(QPoint(79, 16), text);
    }
};

class Explorer : public QMainWindow
{
public:
    explicit Explorer(const QUrl &start)
    {
        auto *central = new QWidget;
        auto *column = new QVBoxLayout(central);
        column->setContentsMargins(0, 0, 0, 0);
        column->setSpacing(0);
        setCentralWidget(central);

        files = new Files(start, this);
        files->onMenu = [this](const KFileItem &item, const QPoint &pos) { contextMenu(item, pos); };
        files->setFollowNewDirectories(false);
        files->setInlinePreviewShown(true);  // thumbnails, as Explorer shows by default
        // KDirOperator remembers its preview panel from file dialogs; Explorer starts without one.
        if (files->action(KDirOperator::ShowPreviewPanel)->isChecked())
            files->action(KDirOperator::ShowPreviewPanel)->trigger();

        nav->go = [this](const QUrl &url) { files->setUrl(url, true); };
        nav->back = [this] { step(-1); };
        nav->forward = [this] { step(1); };
        nav->refresh = [this] { files->action(KDirOperator::Reload)->trigger(); };
        nav->history = [this] { return QList<QUrl>(history.rbegin(), history.rend()); };
        nav->places = [this] { return pane->places(); };
        column->addWidget(nav);
        commands();
        column->addWidget(bar);

        pane->go = [this](const QUrl &url) { files->setUrl(url, true); };
        auto *splitter = new QSplitter;
        splitter->setHandleWidth(3);
        splitter->setStyleSheet(QStringLiteral("QSplitter::handle { background: rgb(212, 208, 200); }"));
        splitter->addWidget(pane);
        splitter->addWidget(files);
        splitter->setStretchFactor(1, 1);
        splitter->setSizes({157, 600});
        column->addWidget(splitter, 1);
        auto *gap = new QWidget;  // the 5px ButtonFace bar above the details pane
        gap->setFixedHeight(5);
        gap->setAutoFillBackground(true);
        QPalette palette = gap->palette();
        palette.setColor(QPalette::Window, classic::face);
        gap->setPalette(palette);
        column->addWidget(gap);
        column->addWidget(details);

        empty = new QLabel(QStringLiteral("This folder is empty."), files);
        empty->hide();

        connect(files, &KDirOperator::urlEntered, this, &Explorer::entered);
        connect(files, &KDirOperator::fileSelected, this, &Explorer::open);
        connect(files, &KDirOperator::finishedLoading, this, &Explorer::updateDetails);
        connect(files, &KDirOperator::finishedLoading, this, &Explorer::hideFocus);
        connect(files, &KDirOperator::viewChanged, this, [this](QAbstractItemView *view) {
            view->setFrameShape(QFrame::NoFrame);
            // With the scroll bar "as needed", QListView always reserves its width, which costs Windows' fifth column.
            // Windows reflows only once the bar appears, so the bar is switched off until there is something to scroll.
            view->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
            connect(view->verticalScrollBar(), &QScrollBar::rangeChanged, view, [view](int, int max) {
                view->setVerticalScrollBarPolicy(max > 0 ? Qt::ScrollBarAlwaysOn : Qt::ScrollBarAlwaysOff);
            });
            view->installEventFilter(this);
            if (auto *tree = qobject_cast<QTreeView *>(view)) {
                explorerColumns(tree);
                connect(tree->header(), &QHeaderView::sortIndicatorChanged, this, [this](int column, Qt::SortOrder order) {
                    auto sort = files->sorting();
                    // KDirOperator's Reversed flag means oldest-first for dates, unlike the header's order.
                    if (column == KDirModel::ModifiedTime) {
                        sort.setFlag(QDir::Reversed, order == Qt::AscendingOrder);
                        files->setSorting(sort);
                    }
                    rememberSort();
                });
            }
            connect(view->selectionModel(), &QItemSelectionModel::selectionChanged, this, &Explorer::updateDetails);
            connect(view->selectionModel(), &QItemSelectionModel::selectionChanged, this, &Explorer::updateActions);
        });
        connect(QApplication::clipboard(), &QClipboard::dataChanged, this, &Explorer::updateActions);
        connect(KIO::FileUndoManager::self(), &KIO::FileUndoManager::undoAvailable, this, &Explorer::updateActions);
        // Filtering the view's model rather than KDirLister's name filter, which always shows folders.
        connect(nav->search, &QLineEdit::textChanged, this, [this](const QString &text) {
            proxy()->setFilterCaseSensitivity(Qt::CaseInsensitive);
            proxy()->setFilterFixedString(text);
            updateDetails();
        });
        // Explorer's Delete moves to the Recycle Bin; Shift+Delete deletes.
        files->action(KDirOperator::Trash)->setShortcut(QKeySequence::Delete);
        files->action(KDirOperator::Delete)->setShortcut(Qt::SHIFT | Qt::Key_Delete);
        files->action(KDirOperator::Reload)->setShortcut(Qt::Key_F5);
        auto *close = action(QStringLiteral("&Close"), QKeySequence(Qt::CTRL | Qt::Key_W), QString(), [this] { QWidget::close(); });
        auto *address = action(QStringLiteral("Address"), QKeySequence(Qt::ALT | Qt::Key_D), QString(), [this] { nav->editAddress(); });
        auto *find = action(QStringLiteral("Search"), QKeySequence(Qt::CTRL | Qt::Key_E), QString(), [this] { nav->search->setFocus(); });
        // KDirOperator's Back/Forward report enabled with no history, so Explorer keeps its own (as Windows' recent pages).
        files->action(KDirOperator::Back)->setShortcut({});
        files->action(KDirOperator::Forward)->setShortcut({});
        auto *back = action(QStringLiteral("Back"), QKeySequence(Qt::ALT | Qt::Key_Left), QString(), [this] { step(-1); });
        auto *forward = action(QStringLiteral("Forward"), QKeySequence(Qt::ALT | Qt::Key_Right), QString(), [this] { step(1); });
        addActions({files->action(KDirOperator::Trash), files->action(KDirOperator::Delete), files->action(KDirOperator::Rename),
                    files->action(KDirOperator::Properties), files->action(KDirOperator::Up), files->action(KDirOperator::Reload),
                    back, forward, cut, copy, paste, undo, selectAll, close, address, find});

        for (auto mode : {KDirOperator::SortByName, KDirOperator::SortByDate, KDirOperator::SortByType, KDirOperator::SortBySize,
                          KDirOperator::SortAscending, KDirOperator::SortDescending}) {
            connect(files->action(mode), &QAction::triggered, this, [this] { rememberSort(); });
        }
        entered(files->url());
        resize(760, 534);
        files->view()->setFocus();  // Windows starts with the keyboard in the file list
    }

protected:
    // KDirOperator's icon view sizes its grid from the font after every resize; Explorer's grid is reapplied after it.
    bool eventFilter(QObject *watched, QEvent *event) override
    {
        if (watched != files->view())
            return false;
        if (event->type() == QEvent::Resize)
            QTimer::singleShot(0, this, &Explorer::applyGrid);
        else if (event->type() == QEvent::FocusIn)
            hideFocus();
        else if (event->type() == QEvent::KeyPress)
            keyboardUsed = true;
        return false;
    }

private:
    Files *files;
    NavigationBand *nav = new NavigationBand;
    CommandBar *bar = new CommandBar;
    NavigationPane *pane = new NavigationPane;
    DetailsPane *details = new DetailsPane;
    QLabel *empty;
    QActionGroup *views = new QActionGroup(this);
    int viewIndex = -1;
    int iconSize = 96;
    bool keyboardUsed = false;
    QList<QUrl> history;
    qsizetype position = -1;
    bool stepping = false;
    KFileItemActions openWith;
    QAction *cut = action(QStringLiteral("Cu&t"), QKeySequence::Cut, QStringLiteral("edit-cut"), [this] { toClipboard(true); });
    QAction *copy = action(QStringLiteral("&Copy"), QKeySequence::Copy, QStringLiteral("edit-copy"), [this] { toClipboard(false); });
    QAction *paste = action(QStringLiteral("&Paste"), QKeySequence::Paste, QStringLiteral("edit-paste"), [this] { pasteInto(files->url()); });
    QAction *undo = action(QStringLiteral("&Undo"), QKeySequence::Undo, QStringLiteral("edit-undo"), [] { KIO::FileUndoManager::self()->undo(); });
    QAction *selectAll = action(QStringLiteral("Select &all"), QKeySequence::SelectAll, QString(), [this] { files->view()->selectAll(); });

    QAction *action(const QString &text, QKeySequence key, const QString &icon, std::function<void()> slot)
    {
        auto *a = new QAction(QIcon::fromTheme(icon), text, this);
        a->setShortcut(key);
        connect(a, &QAction::triggered, this, slot);
        return a;
    }

    void commands()
    {
        auto *organize = new QMenu(this);
        organize->addActions({cut, copy, paste, undo});
        organize->addSeparator();
        organize->addAction(selectAll);
        organize->addSeparator();
        auto *layout = organize->addMenu(QStringLiteral("&Layout"));
        auto toggle = [layout](const QString &text, QWidget *target) {
            auto *a = layout->addAction(text);
            a->setCheckable(true);
            a->setChecked(true);
            QObject::connect(a, &QAction::toggled, target, &QWidget::setVisible);
        };
        toggle(QStringLiteral("&Details pane"), details);
        layout->addAction(files->action(KDirOperator::ShowPreviewPanel));
        toggle(QStringLiteral("&Navigation pane"), pane);
        organize->addSeparator();
        organize->addActions({files->action(KDirOperator::Trash), files->action(KDirOperator::Rename), files->action(KDirOperator::Properties)});
        files->action(KDirOperator::Trash)->setText(QStringLiteral("&Delete"));
        organize->addSeparator();
        organize->addAction(QStringLiteral("&Close"), this, &QWidget::close);
        connect(organize, &QMenu::aboutToShow, this, &Explorer::updateActions);

        // Windows libraries collect folders; here a library is the XDG folder, and including adds a link to it.
        auto *library = new QMenu(this);
        for (auto [name, icon, location] : {std::tuple{"Documents", "library-documents", QStandardPaths::DocumentsLocation},
                                            {"Music", "library-music", QStandardPaths::MusicLocation},
                                            {"Pictures", "library-pictures", QStandardPaths::PicturesLocation},
                                            {"Videos", "library-videos", QStandardPaths::MoviesLocation}})
            library->addAction(assetIcon(QString::fromLatin1(icon)), QString::fromLatin1(name), this, [this, location] {
                const KFileItemList selection = files->selectedItems();
                auto *job = KIO::link(selection.isEmpty() ? QList<QUrl>{files->url()} : selection.urlList(),
                                      QUrl::fromLocalFile(QStandardPaths::writableLocation(location)));
                job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
            });
        auto *share = new QMenu(this);
        share->addAction(QStringLiteral("Specific people..."), this, [this] {
            const KFileItemList selection = files->selectedItems();
            KPropertiesDialog::showDialog(selection.isEmpty() ? files->url() : selection.first().url(), this);
        });

        auto *viewMenu = new QMenu(this);
        const QList<std::pair<QString, QString>> names = {{QStringLiteral("Extra Large Icons"), QStringLiteral("view-extra-large")},
                                                          {QStringLiteral("Large Icons"), QStringLiteral("view-large")},
                                                          {QStringLiteral("Medium Icons"), QStringLiteral("view-medium")},
                                                          {QStringLiteral("Small Icons"), QStringLiteral("view-small")},
                                                          {QStringLiteral("List"), QStringLiteral("view-list")},
                                                          {QStringLiteral("Details"), QStringLiteral("view-details")}};
        for (int i = 0; i < names.size(); ++i) {
            auto *a = viewMenu->addAction(assetIcon(names[i].second), names[i].first, this, [this, i] { chooseView(i); });
            a->setCheckable(true);
            views->addAction(a);
        }
        bar->left = {{QStringLiteral("Organize"), {}, organize, {}},
                     {QStringLiteral("Include in library"), {}, library, {}},
                     {QStringLiteral("Share with"), {}, share, {}},
                     {QStringLiteral("New folder"), {}, nullptr, [this] { files->mkdir(); }}};
        bar->right = {{QStringLiteral("View"), assetIcon(QStringLiteral("view-large")), viewMenu,
                       [this] { chooseView((viewIndex + 1) % views->actions().size()); }},
                      {QStringLiteral("Preview pane"), assetIcon(QStringLiteral("preview-pane")), nullptr,
                       [this] { files->action(KDirOperator::ShowPreviewPanel)->trigger(); }},
                      {QStringLiteral("Help"), assetIcon(QStringLiteral("help")), nullptr, [this] { openUrl(QUrl(QStringLiteral("help:/"))); }}};
    }

    KConfigGroup folderView(KConfig &config) const
    {
        // Use the URL, not a marker in the folder: non-local and read-only locations work too.
        const auto current = files->url();
        const auto url = (current.isLocalFile() ? QUrl::fromLocalFile(QDir::cleanPath(current.toLocalFile())) : current)
                             .adjusted(QUrl::NormalizePathSegments | QUrl::StripTrailingSlash | QUrl::RemovePassword);
        return config.group(QCryptographicHash::hash(url.toEncoded(), QCryptographicHash::Sha256).toHex());
    }

    void rememberViewProperty(const char *key, int value)
    {
        KConfig config(QStringLiteral("win7-explorer-viewsrc"), KConfig::SimpleConfig);
        auto group = folderView(config);
        if (group.readEntry(key, -1) == value)
            return;
        group.writeEntry(key, value);
        if (!config.sync())
            qWarning("Explorer: cannot save %s to win7-explorer-viewsrc", key);
    }

    void chooseView(int index)
    {
        setView(index);
        rememberViewProperty("View", index);
    }

    void syncSortHeader()
    {
        if (auto *tree = qobject_cast<QTreeView *>(files->view())) {
            const QSignalBlocker block(tree->header());
            tree->header()->setSortIndicator(proxy()->sortColumn(), proxy()->sortOrder());
        }
    }

    void rememberSort()
    {
        syncSortHeader();
        rememberViewProperty("Sort", int(files->sorting()));
    }

    void restoreFolderView()
    {
        constexpr int defaultSort = QDir::Name | QDir::DirsFirst;
        KConfig config(QStringLiteral("win7-explorer-viewsrc"), KConfig::SimpleConfig);
        const auto group = folderView(config);
        bool validView, validSort;
        int index = group.readEntry("View", QStringLiteral("1")).toInt(&validView);
        int sort = group.readEntry("Sort", QString::number(defaultSort)).toInt(&validSort);
        if (!validView || index < 0 || index >= views->actions().size()) {
            qWarning("Explorer: invalid View in win7-explorer-viewsrc");
            index = 1;
        }
        const int role = sort & ~int(QDir::DirsFirst | QDir::Reversed);
        if (!validSort || (role != QDir::Name && role != QDir::Time && role != QDir::Size && role != QDir::Type)) {
            qWarning("Explorer: invalid Sort in win7-explorer-viewsrc");
            sort = defaultSort;
        }
        setView(index);
        files->setSorting(QDir::SortFlags::fromInt(sort));
        syncSortHeader();
    }

    void setView(int index)
    {
        if (viewIndex == index)
            return;
        viewIndex = index;
        static const int sizes[] = {256, 96, 48, 16, 16, 16};
        static const char *icons[] = {"view-extra-large", "view-large", "view-medium", "view-small", "view-list", "view-details"};
        const auto mode = index < 3 ? KDirOperator::ViewIconsView : index < 5 ? KDirOperator::ViewCompactView : KDirOperator::ViewDetailsView;
        files->action(mode)->trigger();
        files->setIconSize(sizes[index]);
        // A new KIO view can start with the preview size despite a matching cached zoom.
        files->view()->setIconSize(QSize(sizes[index], sizes[index]));
        iconSize = index < 3 ? sizes[index] : 0;
        views->actions()[index]->setChecked(true);
        bar->right[0].icon = assetIcon(QString::fromLatin1(icons[index]));
        bar->relayout();
        applyGrid();
    }

    // Explorer's icon cells: 117px for Large Icons, starting 7px in from the top-left, as in Windows.
    void applyGrid()
    {
        if (auto *list = qobject_cast<QListView *>(files->view()); list && iconSize) {
            list->setStyleSheet(QStringLiteral("QListView { padding: 7px 0 0 7px; background: white; }"));
            list->setGridSize(QSize(iconSize + 21, iconSize + 40));
        }
    }

    // Explorer's Details columns: Name, Date modified, Type, Size.
    static void explorerColumns(QTreeView *tree)
    {
        for (int column : {KDirModel::Permissions, KDirModel::Owner, KDirModel::Group})
            tree->setColumnHidden(column, true);
        tree->setColumnHidden(KDirModel::Type, false);
        QHeaderView *header = tree->header();
        header->moveSection(header->visualIndex(KDirModel::ModifiedTime), 1);
        header->moveSection(header->visualIndex(KDirModel::Type), 2);
        header->setStretchLastSection(false);
        for (auto [column, width] : {std::pair{KDirModel::Name, 270}, {KDirModel::ModifiedTime, 120}, {KDirModel::Type, 120}, {KDirModel::Size, 80}}) {
            header->setSectionResizeMode(column, QHeaderView::Interactive);
            header->resizeSection(column, width);
        }
    }

    void entered(const QUrl &url)
    {
        restoreFolderView();
        const QString file = url.adjusted(QUrl::StripTrailingSlash).fileName();
        const QString name = url.path() == QLatin1String("/") && url.isLocalFile() ? QStringLiteral("Computer") : file.isEmpty() ? url.toDisplayString() : file;
        setWindowTitle(name);
        const QIcon icon = QIcon::fromTheme(KIO::iconNameForUrl(url));
        // As pixels: given a theme icon, Qt sends KWin only its name, and KWin looks it up in its own icon theme,
        // which doesn't follow the live switch to Windows mode's icons.
        QIcon pixels;
        for (int size : {16, 22, 32, 48})
            pixels.addPixmap(icon.pixmap(size));
        setWindowIcon(pixels);
        details->icon = icon;
        if (!std::exchange(stepping, false)) {
            history.resize(position + 1);
            history.append(url);
            position = history.size() - 1;
        }
        nav->search->clear();
        nav->search->setPlaceholderText(QStringLiteral("Search ") + name);
        nav->setState(url, position > 0, position < history.size() - 1);
        pane->setLocation(url);
    }

    void step(int by)
    {
        if (position + by < 0 || position + by >= history.size())
            return;
        position += by;
        stepping = true;
        files->setUrl(history[position], true);
    }

    // Windows draws no focus rectangle until the keyboard is used, but loading and focusing the view make the first
    // item current in Qt, so that is undone afterwards. Arrow keys still start at the first item.
    void hideFocus()
    {
        if (!keyboardUsed)
            QTimer::singleShot(0, this, [this] { files->view()->selectionModel()->clearCurrentIndex(); });
    }

    QSortFilterProxyModel *proxy() const { return static_cast<QSortFilterProxyModel *>(files->view()->model()); }

    void updateDetails()
    {
        const int selected = files->selectedItems().size();
        const int total = proxy()->rowCount();
        details->text = selected ? QStringLiteral("%1 item%2 selected").arg(selected).arg(selected == 1 ? "" : "s")
                                 : QStringLiteral("%1 item%2").arg(total).arg(total == 1 ? "" : "s");
        details->update();
        empty->setVisible(total == 0);
        if (total == 0) {
            const int top = qobject_cast<QTreeView *>(files->view()) ? static_cast<QTreeView *>(files->view())->header()->height() : 0;
            empty->adjustSize();
            empty->move((files->width() - empty->width()) / 2, top + 16);
            empty->raise();
        }
    }

    void updateActions()
    {
        const bool any = !files->selectedItems().isEmpty();
        cut->setEnabled(any);
        copy->setEnabled(any);
        paste->setEnabled(KUrlMimeData::urlsFromMimeData(QApplication::clipboard()->mimeData()).size() > 0);
        undo->setEnabled(KIO::FileUndoManager::self()->isUndoAvailable());
    }

    void openUrl(const QUrl &url, const QString &mimeType = QString())
    {
        auto *job = new KIO::OpenUrlJob(url, mimeType);
        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
        job->setRunExecutables(false);
        job->start();
    }

    void open(const KFileItem &item) { openUrl(item.targetUrl(), item.mimetype()); }

    void toClipboard(bool cutting)
    {
        auto *data = new QMimeData;
        data->setUrls(files->selectedItems().urlList());
        KIO::setClipboardDataCut(data, cutting);
        QApplication::clipboard()->setMimeData(data);
    }

    void pasteInto(const QUrl &dir)
    {
        auto *job = KIO::paste(QApplication::clipboard()->mimeData(), dir);
        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
    }

    void contextMenu(const KFileItem &item, const QPoint &pos)
    {
        updateActions();
        QMenu menu(this);
        if (item.isNull()) {
            auto *view = menu.addMenu(QStringLiteral("&View"));
            view->addActions(views->actions());
            auto *sort = menu.addMenu(QStringLiteral("Sort &by"));
            sort->addActions({files->action(KDirOperator::SortByName), files->action(KDirOperator::SortByDate),
                             files->action(KDirOperator::SortByType), files->action(KDirOperator::SortBySize)});
            sort->addSeparator();
            sort->addActions({files->action(KDirOperator::SortAscending), files->action(KDirOperator::SortDescending)});
            menu.addAction(QStringLiteral("R&efresh"), files, &KDirOperator::rereadDir);
            menu.addSeparator();
            menu.addAction(QStringLiteral("&Paste"), paste, &QAction::trigger)->setEnabled(paste->isEnabled());
            menu.addAction(QStringLiteral("Paste &shortcut"), this, [this] {
                auto *job = KIO::link(KUrlMimeData::urlsFromMimeData(QApplication::clipboard()->mimeData()), files->url());
                job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
                KIO::FileUndoManager::self()->recordCopyJob(job);
            })->setEnabled(paste->isEnabled());
            menu.addAction(QStringLiteral("&Undo"), undo, &QAction::trigger)->setEnabled(undo->isEnabled());
            menu.addSeparator();
            menu.addMenu(QStringLiteral("Ne&w"))->addAction(assetIcon(QStringLiteral("folder")), QStringLiteral("&Folder"), files, &KDirOperator::mkdir);
            menu.addSeparator();
            menu.addAction(QStringLiteral("P&roperties"), this, [this] { KPropertiesDialog::showDialog(files->url(), this); });
        } else {
            const KFileItemList items = files->selectedItems().isEmpty() ? KFileItemList{item} : files->selectedItems();
            auto *openItem = menu.addAction(QStringLiteral("&Open"), this, [this, items] {
                for (const KFileItem &i : items)
                    i.isDir() ? files->setUrl(i.url(), true) : open(i);
            });
            menu.setDefaultAction(openItem);
            openWith.setItemListProperties(KFileItemListProperties(items));
            openWith.setParentWidget(this);
            openWith.insertOpenWithActionsTo(nullptr, &menu, {});
            menu.addSeparator();
            menu.addActions({cut, copy});
            if (item.isDir())
                menu.addAction(QStringLiteral("&Paste"), this, [this, item] { pasteInto(item.url()); })->setEnabled(paste->isEnabled());
            menu.addSeparator();
            menu.addActions({files->action(KDirOperator::Trash), files->action(KDirOperator::Rename)});
            menu.addSeparator();
            menu.addAction(files->action(KDirOperator::Properties));
        }
        menu.exec(pos);
    }
};

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("win7-explorer"));
    // Matches the .desktop file, so the taskbar groups windows under it and shows its icon.
    app.setDesktopFileName(QStringLiteral("org.win7classic.explorer"));
    QCommandLineParser args;
    args.addPositionalArgument(QStringLiteral("url"), QStringLiteral("Folder to open (default: home)"));
    args.process(app);
    const QStringList urls = args.positionalArguments();
    for (const QString &u : urls.isEmpty() ? QStringList{QDir::homePath()} : urls)
        (new Explorer(QUrl::fromUserInput(u, QDir::currentPath(), QUrl::AssumeLocalFile)))->show();
    return app.exec();
}
