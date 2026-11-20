// Windows 7 Classic Explorer: Explorer's chrome, laid out to the pixel geometry of reference/screenshots/w7-explorer*.png
// and drawn with Windows' own art (explorer/assets, see reference/tools/extract-assets.py), around KDE's KIO file
// widgets, which do the actual file management.
#include "ClassicPrimitives.h"
#include "ExplorerFrequent.h"
#include "ExplorerPrivacy.h"
#include "FolderProperties.h"
#include <KApplicationTrader>
#include <KConfig>
#include <KConfigGroup>
#include <KDirLister>
#include <KDirModel>
#include <KDirOperator>
#include <KFileItemActions>
#include <KFileItemDelegate>
#include <KFileItemListProperties>
#include <KFilePreviewGenerator>
#include <KIconEffect>
#include <KIconUtils>
#include <KIO/ApplicationLauncherJob>
#include <KIO/UDSEntry>
#include <KIO/FileUndoManager>
#include <KIO/Global>
#include <KIO/JobUiDelegateFactory>
#include <KIO/OpenUrlJob>
#include <KIO/Paste>
#include <KIO/PasteJob>
#include <KIO/SimpleJob>
#include <KIO/CopyJob>
#include <KUrlMimeData>
#include <KUser>

#include <QAbstractItemView>
#include <QActionGroup>
#include <QApplication>
#include <QClipboard>
#include <QCheckBox>
#include <QCommandLineParser>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QDialog>
#include <QDialogButtonBox>
#include <QDir>
#include <QDragEnterEvent>
#include <QEnterEvent>
#include <QFile>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QFontMetricsF>
#include <QFutureWatcher>
#include <QGroupBox>
#include <QHeaderView>
#include <QIdentityProxyModel>
#include <QLabel>
#include <QLineEdit>
#include <QListView>
#include <QListWidget>
#include <QMainWindow>
#include <QMenu>
#include <QMenuBar>
#include <QMessageBox>
#include <QMimeData>
#include <QMouseEvent>
#include <QPainter>
#include <QPrintDialog>
#include <QPrinter>
#include <QPointer>
#include <QPromise>
#include <QRadioButton>
#include <QRegularExpression>
#include <QScreen>
#include <QScopedValueRollback>
#include <QSemaphore>
#include <QSortFilterProxyModel>
#include <QScrollBar>
#include <QSignalBlocker>
#include <QSet>
#include <QSplitter>
#include <QStackedWidget>
#include <QStandardPaths>
#include <QStorageInfo>
#include <QStyle>
#include <QStyledItemDelegate>
#include <QStringDecoder>
#include <QTextDocument>
#include <QTabWidget>
#include <QTimer>
#include <QThreadPool>
#include <QTreeView>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

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

class DetailsHeader : public QHeaderView
{
public:
    explicit DetailsHeader(QWidget *parent) : QHeaderView(Qt::Horizontal, parent)
    {
        // The top inset belongs between the header's clickable viewport and the tree's first row.
        setViewportMargins(0, 0, 0, rowInset);
        setBackgroundRole(QPalette::Base);
        setAutoFillBackground(true);
    }

    QSize sizeHint() const override
    {
        return QHeaderView::sizeHint() + QSize(0, rowInset);
    }

protected:
    void paintEvent(QPaintEvent *event) override
    {
        QHeaderView::paintEvent(event);
        const int used = qBound(0, length() - offset(), viewport()->width());
        const auto area = viewport()->rect();
        const auto cap = QStyle::visualRect(layoutDirection(), area, area.adjusted(used, 0, 0, 0));
        if (!cap.isEmpty()) {
            QPainter p(viewport());
            p.fillRect(cap, classic::face);
            Classic::drawEdge(p, cap, Classic::Raised, Classic::Top | Classic::Bottom | Classic::Soft);
        }
    }

    QString label(int column) const
    {
        return column == KDirModel::ModifiedTime ? tr("Date modified")
            : model()->headerData(column, Qt::Horizontal).toString();
    }

    QSize sectionSizeFromContents(int column) const override
    {
        // Auto-fit must leave space for the triangle next to the label.
        return QSize(fontMetrics().horizontalAdvance(label(column)) + (column == KDirModel::Name ? 28 : 17),
                     qMax(23, fontMetrics().height() + 8));
    }

    void paintSection(QPainter *p, const QRect &rect, int column) const override
    {
        if (!rect.isValid())
            return;
        QStyleOptionHeader option;
        initStyleOption(&option);
        initStyleOptionForIndex(&option, column);
        const bool pressed = option.state & QStyle::State_Sunken;
        p->save();
        p->setClipRect(rect, Qt::IntersectClip);
        Classic::drawButton(*p, rect, pressed);
        const auto visual = [this, &rect](const QRect &r) { return QStyle::visualRect(layoutDirection(), rect, r); };
        auto textBox = rect.adjusted((column == KDirModel::Name ? 15 : 4) + pressed, pressed, -4, 0);
        const bool sorted = option.sortIndicator != QStyleOptionHeader::None;
        const auto text = fontMetrics().elidedText(label(column), Qt::ElideRight, textBox.width() - (sorted ? 9 : 0));
        p->setPen(classic::text);
        p->drawText(visual(textBox), Qt::AlignLeading | Qt::AlignVCenter | Qt::TextSingleLine, text);
        if (sorted && !text.isEmpty()) {
            const bool ascending = option.sortIndicator == QStyleOptionHeader::SortDown;
            const int x = textBox.x() + fontMetrics().horizontalAdvance(text) + 4;
            for (int row = 0; row < 3; ++row) {
                const int inset = ascending ? 2 - row : row;
                p->fillRect(visual(QRect(x + inset, textBox.center().y() - 2 + row, 5 - 2 * inset, 1)), classic::shadow);
            }
        }
        p->restore();
    }

private:
    static constexpr int rowInset = 7;
};

class DetailsNameDelegate : public KFileItemDelegate
{
public:
    explicit DetailsNameDelegate(QTreeView *tree, KDirLister *lister)
        : KFileItemDelegate(tree), plainFolders(lister)
    {
        plainFolders.setSourceModel(tree->model());
        connect(&modeWatcher, &QFileSystemWatcher::fileChanged, this, [this, tree] { updateMode(tree); });
        connect(&modeWatcher, &QFileSystemWatcher::directoryChanged, this, [this, tree] { updateMode(tree); });
        updateMode(tree);
        auto *clipboard = QApplication::clipboard();
        const auto updateCut = [this, tree, clipboard] {
            const auto *data = clipboard->mimeData();
            const auto urls = data && KIO::isClipboardDataCut(data) ? KUrlMimeData::urlsFromMimeData(data) : QList<QUrl>{};
            plainFolders.cut = QSet<QUrl>(urls.cbegin(), urls.cend());
            if (windowsMode)
                tree->viewport()->update();
        };
        connect(clipboard, &QClipboard::dataChanged, this, updateCut);
        updateCut();
    }

    QSize sizeHint(const QStyleOptionViewItem &option, const QModelIndex &index) const override
    {
        auto size = KFileItemDelegate::sizeHint(option, index);
        return QSize(size.width() + 14, qMax(22, size.height()));
    }

    void paint(QPainter *painter, const QStyleOptionViewItem &option, const QModelIndex &index) const override
    {
        auto cell = option;
        cell.rect = QStyle::visualRect(option.direction, option.rect, option.rect.adjusted(14, 0, 0, 0));
        if (windowsMode && index.data(KDirModel::FileItemRole).value<KFileItem>().isDir()) {
            plainFolders.iconSize = cell.decorationSize;
            plainFolders.dpr = painter->device()->devicePixelRatioF();
            KFileItemDelegate::paint(painter, cell, plainFolders.mapFromSource(index));
        } else {
            KFileItemDelegate::paint(painter, cell, index);
        }
    }

private:
    // KDirModel puts previews and plain icons in the same role. Only change the paint-time read:
    // clearing the live role would lose Large Icons montages which KIO can't regenerate at 16px.
    class PlainFolderDecoration : public QIdentityProxyModel
    {
    public:
        explicit PlainFolderDecoration(KDirLister *lister) : lister(lister) {}
        QSet<QUrl> cut;
        QSize iconSize;
        qreal dpr = 1;

        QVariant data(const QModelIndex &index, int role) const override
        {
            if (role != Qt::DecorationRole)
                return QIdentityProxyModel::data(index, role);
            const auto item = index.data(KDirModel::FileItemRole).value<KFileItem>();
            const auto name = item.iconName();
            // Match KDirModel's non-preview branch, including its unknown icon and slow-listing rule.
            QIcon icon = QDir::isAbsolutePath(name) ? QIcon(name) : QIcon();
            if (icon.isNull() || (!(name.endsWith(u".svg") || name.endsWith(u".svgz")) && icon.availableSizes().isEmpty()))
                icon = QIcon::fromTheme(name, QIcon::fromTheme(QStringLiteral("unknown")));

            if (root.url() != lister->url())
                root = KFileItem(lister->url());
            bool slow = root.isSlow();
            for (auto parent = index.parent(); !slow && parent.isValid(); parent = parent.parent())
                slow = parent.data(KDirModel::FileItemRole).value<KFileItem>().isSlow();
            if (!slow)
                icon = KIconUtils::addOverlays(icon, item.overlays());
            if (cut.contains(item.url())) {
                auto pixmap = icon.pixmap(iconSize, dpr);
                KIconEffect::toDisabled(pixmap);
                icon = QIcon(pixmap);
            }
            return icon;
        }

    private:
        const KDirLister *lister;
        mutable KFileItem root;
    };

    void updateMode(QTreeView *tree)
    {
        const auto state = QStandardPaths::writableLocation(QStandardPaths::GenericStateLocation)
            + QStringLiteral("/win7-classic/mode");
        // A fresh install has no mode file yet; watch its nearest existing parent until it appears.
        auto watch = state;
        while (!QFileInfo::exists(watch))
            watch = QFileInfo(watch).absolutePath();
        const auto old = modeWatcher.files() + modeWatcher.directories();
        if (!old.contains(watch)) {
            if (!modeWatcher.addPath(watch))
                qWarning() << "Explorer cannot watch active mode at" << watch;
            if (!old.isEmpty())
                modeWatcher.removePaths(old);
        }
        QFile mode(state);
        const bool windows = mode.open(QIODevice::ReadOnly) && mode.readLine().trimmed() == "windows";
        if (!mode.isOpen() && QFileInfo::exists(state))
            qWarning() << "Explorer cannot read active mode:" << mode.errorString();
        if (windowsMode != windows) {
            windowsMode = windows;
            tree->viewport()->update();
        }
    }

    QFileSystemWatcher modeWatcher;
    mutable PlainFolderDecoration plainFolders;
    bool windowsMode = false;
};

static QString absoluteDate(const QDateTime &date, const QLocale &locale)
{
    // Keep local date order and clock, but not a relative label or a two-digit year.
    static const QRegularExpression year(QStringLiteral("(?<!y)yy(?!y)"));
    auto format = locale.dateTimeFormat(QLocale::ShortFormat).split(u'\'');
    for (qsizetype part = 0; part < format.size(); part += 2)
        format[part].replace(year, QStringLiteral("yyyy"));
    return locale.toString(date, format.join(u'\''));
}

// Keep KIO's model and proxy untouched: translated text must not become the comparison key.
class DetailsMetadataDelegate : public QStyledItemDelegate
{
public:
    using QStyledItemDelegate::QStyledItemDelegate;

protected:
    void initStyleOption(QStyleOptionViewItem *option, const QModelIndex &index) const override
    {
        QStyledItemDelegate::initStyleOption(option, index);
        const auto item = index.data(KDirModel::FileItemRole).value<KFileItem>();
        switch (index.column()) {
        case KDirModel::Size:
            if (item.isDir())
                option->text.clear();
            break;
        case KDirModel::Type:
            if (item.isDir())
                option->text = tr("File folder");
            break;
        case KDirModel::ModifiedTime: {
            const auto &entry = item.entry();
            option->text.clear();
            if (!entry.contains(KIO::UDSEntry::UDS_MODIFICATION_TIME))
                break;
            const QDateTime modified = QDateTime::fromSecsSinceEpoch(entry.numberValue(KIO::UDSEntry::UDS_MODIFICATION_TIME));
            option->text = absoluteDate(modified, option->locale);
            break;
        }
        }
    }
};

// These values are the on-disk View field, not positions in a menu.
enum ViewMode { ExtraLarge = 0, Large = 1, Medium = 2, Small = 3, List = 4, Details = 5, Tiles = 6, Content = 7 };

class RichFileDelegate : public QStyledItemDelegate
{
public:
    RichFileDelegate(bool tile, QListView *view) : QStyledItemDelegate(view), tile(tile), view(view) {}

    QSize sizeHint(const QStyleOptionViewItem &option, const QModelIndex &) const override
    {
        const int lines = option.fontMetrics.height() * (tile ? 3 : 2);
        return {tile ? 254 : view->viewport()->width(), qMax(tile ? 56 : 44, lines + 10)};
    }

    void paint(QPainter *p, const QStyleOptionViewItem &option, const QModelIndex &index) const override
    {
        const auto item = index.data(KDirModel::FileItemRole).value<KFileItem>();
        const auto r = option.rect;
        auto background = option;
        background.showDecorationSelected = true;
        if (option.state & QStyle::State_Selected)
            background.palette.setCurrentColorGroup(option.state & QStyle::State_Active ? QPalette::Active : QPalette::Inactive);
        view->style()->drawControl(QStyle::CE_ItemViewItem, &background, p, view);
        const auto visual = [&](const QRect &rect) { return QStyle::visualRect(option.direction, r, rect); };
        const int extent = tile ? 48 : 32;
        const auto icon = qvariant_cast<QIcon>(index.data(Qt::DecorationRole));
        icon.paint(p, visual(QRect(r.x() + (tile ? 12 : 16), r.y() + (r.height() - extent) / 2, extent, extent)));
        const int line = option.fontMetrics.height();
        const auto metadata = tile ? (item.isDir() ? tr("File folder") : item.mimeComment()) : QString();
        QString size;
        if (!item.isDir() && item.entry().contains(KIO::UDSEntry::UDS_SIZE))
            size = KIO::convertSize(item.size());
        p->save();
        p->setFont(option.font);
        p->setPen(background.palette.color(option.state & QStyle::State_Selected ? QPalette::HighlightedText : QPalette::Text));
        auto draw = [&](const QString &text, int x, int y, int width) {
            if (width > 0)
                p->drawText(visual(QRect(r.x() + x, r.y() + y, width, line)), Qt::AlignLeading | Qt::AlignVCenter,
                            option.fontMetrics.elidedText(text, Qt::ElideRight, width));
        };
        if (tile) {
            const int y = (r.height() - line * (size.isEmpty() ? 2 : 3)) / 2;
            draw(index.data().toString(), 65, y, r.width() - 75);
            draw(metadata, 65, y + line, r.width() - 75);
            draw(size, 65, y + 2 * line, r.width() - 75);
        } else {
            const int split = r.width() * 63 / 100;
            draw(index.data().toString(), 55, 6, split - 65);
            if (!item.isDir())
                draw(item.mimeComment(), 55, 6 + line, split - 65);
            if (item.entry().contains(KIO::UDSEntry::UDS_MODIFICATION_TIME))
                draw(tr("Date modified: %1").arg(absoluteDate(item.time(KFileItem::ModificationTime), option.locale)),
                     split, 6, r.width() - split - 5);
            if (!size.isEmpty())
                draw(tr("Size: %1").arg(size), split, 6 + line, r.width() - split - 5);
            if (index.row() + 1 < index.model()->rowCount(index.parent()) && !(option.state & QStyle::State_Selected)) {
                QLinearGradient rule(r.topLeft(), r.topRight());
                rule.setColorAt(0, option.palette.color(QPalette::Base));
                rule.setColorAt(.45, option.palette.color(QPalette::Mid));
                rule.setColorAt(1, option.palette.color(QPalette::Base));
                p->fillRect(QRect(r.x(), r.bottom(), r.width(), 1), rule);
            }
        }
        p->restore();
    }

private:
    bool tile;
    QListView *view;
};

class RichFileView : public QListView
{
public:
    RichFileView(bool tile, QWidget *parent) : QListView(parent)
    {
        setViewMode(tile ? IconMode : ListMode);
        setResizeMode(Adjust);
        setMovement(Static);
        setUniformItemSizes(true);
        setDragDropMode(DragOnly);
        setEditTriggers(NoEditTriggers);
        setVerticalScrollMode(ScrollPerPixel);
    }

protected:
    void dragEnterEvent(QDragEnterEvent *event) override
    {
        // KDirOperator also accepts URI drops from applications that don't offer its model MIME type.
        if (event->mimeData()->hasUrls())
            event->acceptProposedAction();
    }
};

// KDirOperator's file-dialog menu needs separate Explorer background and item actions.
class Files : public KDirOperator
{
public:
    using KDirOperator::KDirOperator;
    std::function<void(const KFileItem &, const QPoint &)> onMenu;
    std::function<void(const QUrl &)> onOpenFolder;
    std::function<void(const QUrl &, bool)> navigate;
    void setUrl(const QUrl &url, bool clearForward) override { navigate(url, clearForward); }
    int presentation = Large;
    void syncSelectionActions() { updateSelectionDependentActions(); }

protected:
    void selectDir(const KFileItem &item) override { onOpenFolder(item.targetUrl()); }

    QAbstractItemView *createView(QWidget *parent, KFile::FileView viewKind) override
    {
        if (presentation == Tiles || presentation == Content)
            return new RichFileView(presentation == Tiles, parent);
        auto *view = KDirOperator::createView(parent, viewKind);
        if (auto *tree = qobject_cast<QTreeView *>(view)) {
            // Install before KDirOperator wires its sort synchronization to the header.
            tree->setHeader(new DetailsHeader(tree));
        }
        return view;
    }

    bool eventFilter(QObject *watched, QEvent *event) override
    {
        if (view() && (watched == view()->viewport() || watched == view())
            && (event->type() == QEvent::DragEnter || event->type() == QEvent::DragMove || event->type() == QEvent::Drop)
            && static_cast<QDropEvent *>(event)->source() == view()) {
            // Wayland enters the origin before crossing windows; reject this target, not the entire drag.
            event->ignore();
            return true;
        }
        return KDirOperator::eventFilter(watched, event);
    }

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
            const auto click = parts[part].click;
            // Organize → Close can delete the owning window during the popup event loop.
            const QPointer<Painted> alive(this);
            click();
            if (alive)
                alive->update();
        }
    }
    void mouseReleaseEvent(QMouseEvent *e) override
    {
        const int part = std::exchange(pressed, -1);
        update();
        if (part >= 0 && part == partAt(e->position().toPoint())) {
            // Opening a folder can rebuild the command bar before the callback returns.
            const auto click = parts[part].click;
            click();
        }
    }
    virtual bool pressOpens(int) const { return false; }
};

static const QUrl computerUrl(QStringLiteral("win7-explorer:/computer"));
static const QUrl librariesUrl(QStringLiteral("win7-explorer:/libraries"));

static bool isOverviewUrl(const QUrl &url) { return url == computerUrl || url == librariesUrl; }

static QUrl standardFolder(QStandardPaths::StandardLocation location)
{
    return QUrl::fromLocalFile(QStandardPaths::writableLocation(location));
}

struct Library {
    const char *name;
    const char *icon;
    QStandardPaths::StandardLocation location;
};

static constexpr Library libraries[] = {
    {"Documents", "library-documents", QStandardPaths::DocumentsLocation},
    {"Music", "library-music", QStandardPaths::MusicLocation},
    {"Pictures", "library-pictures", QStandardPaths::PicturesLocation},
    {"Videos", "library-videos", QStandardPaths::MoviesLocation},
};

static quint64 browseableMountId(const QString &path)
{
    const auto name = QFile::encodeName(path);
    struct statx info = {};
    // Device numbers and paths can both be reused after an unmount.
    constexpr unsigned mask = STATX_TYPE | STATX_MNT_ID_UNIQUE;
    if (::statx(AT_FDCWD, name.constData(), AT_NO_AUTOMOUNT, mask, &info) != 0
        || (info.stx_mask & mask) != mask || !(info.stx_attributes & STATX_ATTR_MOUNT_ROOT)
        || !S_ISDIR(info.stx_mode) || ::access(name.constData(), R_OK | X_OK) != 0)
        return 0;
    return info.stx_mnt_id;
}

class OverviewTiles : public QStyledItemDelegate
{
public:
    using QStyledItemDelegate::QStyledItemDelegate;
    enum Role { Target = Qt::UserRole, MountId, CapacityText, UsedPercent, Subtitle };

    void paint(QPainter *p, const QStyleOptionViewItem &option, const QModelIndex &item) const override
    {
        const bool selected = option.state.testFlag(QStyle::State_Selected);
        const QRect r = option.rect.adjusted(3, 2, -3, -2);
        p->save();
        p->setClipRect(r);
        if (selected)
            p->fillRect(r, classic::highlight);
        p->setPen(selected ? classic::light : classic::text);
        qvariant_cast<QIcon>(item.data(Qt::DecorationRole)).paint(p, QRect(r.topLeft() + QPoint(4, 2), QSize(48, 48)));
        const QString usage = item.data(CapacityText).toString();
        const int left = r.left() + 56, w = r.right() - left - 3;
        const QFontMetrics metrics(option.font);
        const int line = metrics.height();
        const QString subtitle = item.data(Subtitle).toString();
        const int top = usage.isEmpty() ? r.center().y() - (subtitle.isEmpty() ? line / 2 : line) : r.center().y() - line - 5;
        const auto text = [&](int y, const QString &value) {
            p->drawText(QRect(left, y, w, line), Qt::AlignVCenter, metrics.elidedText(value, Qt::ElideRight, w));
        };
        text(top, item.data().toString());
        if (!subtitle.isEmpty())
            text(top + line, subtitle);
        if (!usage.isEmpty()) {
            const QRect meter(left, top + line + 1, w, 11);
            p->fillRect(meter, classic::light);
            p->setPen(classic::highlight);
            p->drawRect(meter.adjusted(0, 0, -1, -1));
            p->fillRect(meter.left() + 1, meter.top() + 1, (w - 2) * item.data(UsedPercent).toInt() / 100,
                        meter.height() - 2, classic::highlight);
            p->setPen(selected ? classic::light : classic::text);
            text(meter.bottom() + 1, usage);
        }
        p->restore();
    }
};

class Overview : public QWidget
{
public:
    QListWidget *tiles = new QListWidget;
    QLabel *heading = new QLabel;
    QLabel *description = new QLabel;
    Overview()
    {
        setAutoFillBackground(true);
        auto colors = palette();
        colors.setColor(QPalette::Window, classic::light);
        colors.setColor(QPalette::Base, classic::light);
        colors.setColor(QPalette::WindowText, classic::text);
        setPalette(colors);
        auto *layout = new QVBoxLayout(this);
        layout->setContentsMargins(14, 8, 4, 0);
        layout->setSpacing(4);
        heading->setTextFormat(Qt::PlainText);
        heading->setWordWrap(true);
        heading->setAlignment(Qt::AlignTop | Qt::AlignLeft);
        layout->addWidget(heading);
        description->setWordWrap(true);
        layout->addWidget(description);
        tiles->setFrameShape(QFrame::NoFrame);
        tiles->setViewMode(QListView::IconMode);
        tiles->setMovement(QListView::Static);
        tiles->setFlow(QListView::LeftToRight);
        tiles->setResizeMode(QListView::Adjust);
        tiles->setDragDropMode(QAbstractItemView::NoDragDrop);
        tiles->setGridSize(QSize(254, qMax(56, fontMetrics().height() * 2 + 18)));
        tiles->setItemDelegate(new OverviewTiles(tiles));
        layout->addWidget(tiles, 1);
    }

    void load(const QUrl &url)
    {
        const bool computer = url == computerUrl;
        auto font = this->font();
        if (!computer)
            font.setPixelSize(qRound(QFontMetricsF(font).height() * 1.25));
        heading->setFont(font);
        description->setVisible(!computer);
        tiles->clear();
        if (computer) {
            loadComputer();
            return;
        }
        tiles->setVisible(true);
        heading->setText(tr("Libraries"));
        description->setText(tr("Open a library to see your files in its configured folder."));
        for (const auto &library : libraries) {
            auto *item = add(QString::fromLatin1(library.name), assetIcon(QString::fromLatin1(library.icon)), standardFolder(library.location));
            item->setData(OverviewTiles::Subtitle, tr("Library"));
        }
    }

private:
    void loadComputer()
    {
        // Probe a guaranteed path so unavailable mount IDs aren't mistaken for inaccessible volumes.
        struct statx root = {};
        const bool supported = ::statx(AT_FDCWD, "/", AT_NO_AUTOMOUNT, STATX_MNT_ID_UNIQUE, &root) == 0
            && (root.stx_mask & STATX_MNT_ID_UNIQUE);
        tiles->setVisible(supported);
        if (!supported) {
            heading->setText(tr("Cannot list storage volumes: unique mount IDs are unavailable (requires Linux 6.8 or later)."));
            return;
        }
        QSet<QString> seen;
        for (const auto &volume : QStorageInfo::mountedVolumes()) {
            const QString path = volume.rootPath();
            if (!volume.isValid() || path.isEmpty() || seen.contains(path))
                continue;
            const auto mountId = browseableMountId(path);
            if (!mountId)
                continue;
            seen.insert(path);
            const auto name = volume.name();
            const QString label = name.isEmpty() || name == path ? path : tr("%1 (%2)").arg(name, path);
            auto *item = add(label, assetIcon(path == QLatin1String("/") ? QStringLiteral("drive-system") : QStringLiteral("drive")),
                             QUrl::fromLocalFile(path));
            item->setData(OverviewTiles::MountId, mountId);
            const qint64 free = volume.bytesAvailable(), total = volume.bytesTotal();
            if (volume.isReady() && total > 0 && free >= 0 && free <= total) {
                item->setData(OverviewTiles::CapacityText,
                              tr("%1 free of %2").arg(locale().formattedDataSize(free), locale().formattedDataSize(total)));
                item->setData(OverviewTiles::UsedPercent, qRound(100.0 * (total - free) / total));
            }
        }
        heading->setText(tr("Storage volumes (%1)").arg(tiles->count()));
    }

public:
    void filter(const QString &text)
    {
        for (int i = 0; i < tiles->count(); ++i) {
            auto *item = tiles->item(i);
            item->setHidden(!item->text().contains(text, Qt::CaseInsensitive));
        }
    }

private:
    QListWidgetItem *add(const QString &name, const QIcon &icon, const QUrl &url)
    {
        auto *item = new QListWidgetItem(icon, name, tiles);
        item->setSizeHint(tiles->gridSize());
        item->setData(OverviewTiles::Target, url);
        item->setToolTip(url.toLocalFile());
        return item;
    }
};

static QString locationName(const QUrl &url)
{
    if (url == computerUrl)
        return QStringLiteral("Computer");
    if (url == librariesUrl)
        return QStringLiteral("Libraries");
    if (url.isLocalFile() && url.path() == QLatin1String("/"))
        return QStringLiteral("File System");
    const QString name = url.adjusted(QUrl::StripTrailingSlash).fileName();
    return name.isEmpty() ? url.toDisplayString() : name;
}

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
        // A separate, input-transparent window can extend past the painted bar without grabbing focus.
        tip.setTextFormat(Qt::PlainText);
        tip.setAttribute(Qt::WA_ShowWithoutActivating);
        QFont tipFont(QStringLiteral("Tahoma"));
        tipFont.setPixelSize(11);
        tip.setFont(tipFont);
        tip.setStyleSheet(QStringLiteral("background: #ffffe1; color: black; border: 1px solid black; padding: 0 1px"));
        tipDwell.setSingleShot(true);
        tipExpiry.setSingleShot(true);
        connect(&tipDwell, &QTimer::timeout, this, [this] {
            if (window()->isActiveWindow() && partAt(tipPointer) == tipPart)
                showNavigationTip();
        });
        connect(&tipExpiry, &QTimer::timeout, &tip, &QLabel::hide);
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

    void setState(const QUrl &url, const QUrl &backUrl, const QUrl &forwardUrl, const QIcon &icon)
    {
        clearNavigationTip();
        location = url;
        addressIcon = icon;
        backDestination = backUrl;
        forwardDestination = forwardUrl;
        backEnabled = !backUrl.isEmpty();
        forwardEnabled = !forwardUrl.isEmpty();
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
        p.drawPixmap(box.left() + 2, 9, addressIcon.pixmap(QSize(16, 16), devicePixelRatioF()));
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

    bool pressOpens(int part) const override { return part == LibraryPlacesPart || part >= HistoryPart; }

    void enterEvent(QEnterEvent *event) override { trackNavigationTip(event->position().toPoint()); }
    void mouseMoveEvent(QMouseEvent *event) override
    {
        Painted::mouseMoveEvent(event);
        if (!event->buttons())
            trackNavigationTip(event->position().toPoint());
    }
    void leaveEvent(QEvent *event) override
    {
        clearNavigationTip();
        Painted::leaveEvent(event);
    }
    void mousePressEvent(QMouseEvent *event) override
    {
        clearNavigationTip();
        Painted::mousePressEvent(event);
    }
    bool event(QEvent *event) override
    {
        if (event->type() == QEvent::WindowDeactivate || event->type() == QEvent::Hide)
            clearNavigationTip();
        return Painted::event(event);
    }

private:
    enum { BackPart, ForwardPart, SearchPart, RefreshPart, LibraryPlacesPart, EditPart, HistoryPart };  // crumb parts follow HistoryPart
    struct Crumb {
        QString label;
        QUrl url;
        QRect text, arrow;
    };
    QUrl location, backDestination, forwardDestination;
    QIcon addressIcon;
    bool backEnabled = false, forwardEnabled = false;
    QList<Crumb> crumbs;
    QLineEdit *address = new QLineEdit(this);
    QLabel tip{this, Qt::ToolTip | Qt::WindowDoesNotAcceptFocus | Qt::WindowTransparentForInput};
    QTimer tipDwell, tipExpiry;
    int tipPart = -1;
    QPoint tipPointer;

    void clearNavigationTip()
    {
        tipDwell.stop();
        tipExpiry.stop();
        tip.hide();
        tipPart = -1;
    }
    void trackNavigationTip(const QPoint &position)
    {
        const int part = partAt(position);
        if (part != tipPart) {
            clearNavigationTip();
            if (part == BackPart || part == ForwardPart) {
                tipPart = part;
                tipDwell.start(700);
            }
        }
        tipPointer = position;
    }
    void showNavigationTip()
    {
        const QRect screen = this->screen()->geometry();
        const bool back = tipPart == BackPart;
        const QUrl &destination = back ? backDestination : forwardDestination;
        const QString name = locationName(destination.adjusted(QUrl::RemoveUserInfo));
        const QString label = back ? tr("Back to %1").arg(name) : tr("Forward to %1").arg(name);
        tip.setText(tip.fontMetrics().elidedText(label, Qt::ElideRight, screen.width() - 4));
        tip.resize(std::min(screen.width(), tip.sizeHint().width()), 16);
        QPoint at = mapToGlobal(tipPointer);
        at.setX(std::clamp(at.x(), screen.left(), screen.right() - tip.width() + 1));
        // Win32 anchors below the cursor hotspot unless the tip would run off-screen.
        at.setY(at.y() + 21 + tip.height() <= screen.bottom() + 1 ? at.y() + 21 : at.y() - tip.height());
        tip.move(at);
        tip.show();
        tipExpiry.start(5000);
    }

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
            if (!url.isEmpty())
                list.append({isOverviewUrl(url) ? locationName(url) : url.toDisplayString(), url, {}, {}});
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
            list.append({locationName(QUrl::fromLocalFile(base)), QUrl::fromLocalFile(base), {}, {}});
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
        const QRect placesArrow = crumbs.first().arrow;
        const auto openPlaces = [this, placesArrow] {
            QMenu menu;
            for (const auto &[name, url] : places())
                menu.addAction(name, this, [this, url] { go(url); });
            menu.exec(mapToGlobal(QPoint(placesArrow.left(), 28)));
        };
        parts = {
            {QRect(2, 2, 30, 32), [this] { back(); }, backEnabled},
            {QRect(32, 2, 28, 32), [this] { forward(); }, forwardEnabled},
            {QRect(width() - 23, 7, 21, 21), [this] { search->setFocus(); }},
            {QRect(box.right() - 21, 8, 21, 20), [this] { refresh(); }},
            // Only Libraries gives Places priority over the published click-to-edit area.
            {placesArrow, openPlaces, location == librariesUrl},
            {box.adjusted(0, 0, -41, 0), [this] { editAddress(); }},
            {QRect(box.right() - 41, 8, 19, 20), [this, box] { menuOf(history(), QRect(box.left(), box.bottom(), 0, 0)); }, backEnabled || forwardEnabled},
            {placesArrow, openPlaces, location != librariesUrl},
        };
        for (int i = 1; i < crumbs.size(); ++i) {
            const Crumb crumb = crumbs[i];
            parts.insert(HistoryPart + 1, {crumb.text.adjusted(-3, -2, 3, 2), [this, crumb] { go(crumb.url); }});
            parts.insert(HistoryPart + 1, {crumb.arrow, [this, crumb] { subfolderMenu(crumb.url, QPoint(crumb.arrow.left(), 28)); }});
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
        QActionGroup *menuAnchorActions = nullptr;
        QAction *action = nullptr;
    };
    QList<Command> left, right;
    void setSelection(bool selected, const QString &icon, QMenu *menu, bool library, bool print)
    {
        if (showOpen == selected && openIcon == icon && left[1].menu == menu && showLibrary == library && showPrint == print)
            return;
        showOpen = selected;
        showLibrary = library;
        showPrint = print;
        openIcon = icon;
        left[1].icon = QIcon::fromTheme(icon);
        left[1].menu = menu;
        relayout();
    }

    void setOverview(bool value)
    {
        overview = value;
        relayout();
    }

    CommandBar() { setFixedHeight(31); }
    void relayout()
    {
        parts.clear();
        visibleLeft.clear();
        visibleRight.clear();
        pressed = -1;
        int x = 2;
        const QFontMetrics metrics(font());
        // Keep the view controls clickable even when Open makes the left group too wide.
        const int offsets[] = {115, 64, 36};
        const int end = width() - offsets[0];
        QList<std::pair<Command, int>> commands;
        int fullWidth = x;
        for (qsizetype i = 0; i < left.size(); ++i) {
            if ((overview && i != 0) || (i == 1 && !showOpen) || (i == 2 && !showLibrary) || (i == 4 && !showPrint))
                continue;
            const Command &command = left[i];
            const int width = 21 + metrics.horizontalAdvance(command.text) + (command.menu ? 15 : 0)
                              + (command.icon.isNull() ? 0 : 13);
            commands.append({command, width});
            fullWidth += width;
        }
        constexpr int overflowWidth = 36;
        QList<Command> hidden;
        auto add = [this, &x](const Command &command, int width) {
            visibleLeft.append(command);
            parts.append({QRect(x, 2, width, 27), [this, command, x = x, width] { trigger(command, x, width); }});
            x += width;
        };
        for (const auto &[command, width] : commands) {
            if (fullWidth > end && (x + width + overflowWidth > end || !hidden.isEmpty()))
                hidden.append(command);
            else
                add(command, width);
        }
        if (!hidden.isEmpty())
            add({QStringLiteral("»"), {}, nullptr, [this, hidden, x] {
                QMenu menu(this);
                for (const auto &command : hidden) {
                    if (command.action)
                        menu.addAction(command.action);
                    else if (command.act)
                        menu.addAction(command.icon, command.text, this, command.act);
                    if (command.menu) {
                        auto *submenu = menu.addMenu(command.act ? QStringLiteral("Open with") : command.text);
                        connect(submenu, &QMenu::aboutToShow, command.menu, &QMenu::aboutToShow);
                        connect(submenu, &QMenu::aboutToShow, submenu, [submenu, command] {
                            submenu->clear();
                            submenu->addActions(command.menu->actions());
                        });
                    }
                }
                menu.exec(mapToGlobal(QPoint(x, 29)));
            }}, overflowWidth);
        // Right-aligned like the reference: view split button, preview pane, help.
        for (int i = 0; i < right.size(); ++i) {
            if (overview && i != 2)
                continue;
            const auto &command = right[i];
            visibleRight.append(command);
            const int x = width() - offsets[i];
            const int width = command.menu ? 47 : 26;
            parts.append({QRect(x, 2, width, 27), [this, command, x, width] { trigger(command, x, width); }});
        }
        hovered = partAt(mapFromGlobal(QCursor::pos()));
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
                if (i < visibleLeft.size()) {
                    p.drawText(QPoint(r.left() + 24, 19), c.text);
                    if (c.menu)
                        arrow(p, r.right() - 16, 13, 7);
                } else if (c.menu) {
                    arrow(p, r.left() + 34, 13, 7);
                }
            }
        }
    }

private:
    bool overview = false;
    bool showOpen = false, showLibrary = true, showPrint = false;
    QString openIcon;
    QList<Command> visibleLeft, visibleRight;
    const Command &command(int part) const { return part < visibleLeft.size() ? visibleLeft[part] : visibleRight[part - visibleLeft.size()]; }
    void trigger(const Command &command, int x, int width)
    {
        // Keep the main action on the text/icon and the menu on the trailing arrow.
        const QPoint cursor = mapFromGlobal(QCursor::pos());
        if (command.menu && (!command.act || cursor.x() >= x + width - 21)) {
            auto *menu = command.menu;
            if (command.menuAnchorActions && menu->style()->name().compare(QStringLiteral("Win7Classic"), Qt::CaseInsensitive) == 0) {
                // Explorer opens View with the current choice beside the command, subject to popup constraints.
                auto *selected = command.menuAnchorActions->checkedAction();
                const int rowHeight = menu->actionGeometry(selected).height();
                menu->exec(mapToGlobal(QPoint(x, 15 - rowHeight / 2)), selected);
            } else {
                menu->exec(mapToGlobal(QPoint(x, 29)));
            }
        } else if (command.action) {
            command.action->trigger();
        } else {
            command.act();
        }
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
        bool library = false;
    };
    std::function<void(const QUrl &)> go;

    NavigationPane()
    {
        rows = {
            {QStringLiteral("Favorites"), QStringLiteral("favorites"), QUrl()},
            {QStringLiteral("Desktop"), QStringLiteral("desktop"), standardFolder(QStandardPaths::DesktopLocation), true},
            {QStringLiteral("Downloads"), QStringLiteral("downloads"), standardFolder(QStandardPaths::DownloadLocation), true},
            {QStringLiteral("Recent Places"), QStringLiteral("recent-places"), QUrl(QStringLiteral("recentlyused:/locations")), true},
            {},
            {QStringLiteral("Libraries"), QStringLiteral("libraries"), librariesUrl},
        };
        for (const auto &library : libraries)
            rows.append({QString::fromLatin1(library.name), QString::fromLatin1(library.icon), standardFolder(library.location), true, true});
        rows.append({{}, {QStringLiteral("Computer"), QStringLiteral("computer"), computerUrl}, {},
                     {QStringLiteral("Network"), QStringLiteral("network"), QUrl(QStringLiteral("remote:/"))}});
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
            parts.append({QRect(0, 9 + 19 * i, width(), 19), [this, row] {
                              if (row.url.isValid() || row.library)
                                  go(row.url);
                          },
                          !row.text.isEmpty()});
        }
        update();
    }
};

// Selection fields share the existing 48px strip; see w7-explorer-selection.png.
class DetailsPane : public QWidget
{
public:
    QIcon icon;
    QString name, type, modified, size, created;
    bool mixed = false;
    DetailsPane() { setFixedHeight(48); }

    void setItems(const KFileItemList &items, bool filesOnly, int total, const QIcon &folderIcon)
    {
        const qsizetype count = items.size();
        const auto item = count ? items.first() : KFileItem();
        mixed = std::ranges::any_of(items, &KFileItem::isDir) && std::ranges::any_of(items, &KFileItem::isFile);
        icon = count && !mixed ? QIcon::fromTheme(item.iconName()) : folderIcon;
        name = count == 1 ? item.text() : count ? tr("%n items selected", nullptr, count)
                                               : total < 0 ? QString()
                                               : total == 1 ? tr("1 item") : tr("%n items", nullptr, total);
        type = count == 1 ? (item.isDir() ? tr("File folder") : item.mimeComment()) : QString();
        modified = dateProperty(tr("Date modified: %1"), items, KFileItem::ModificationTime);
        created = filesOnly ? dateProperty(tr("Date created: %1"), items, KFileItem::CreationTime) : QString();
        size.clear();
        if (filesOnly) {
            KIO::filesize_t bytes = 0;
            bool known = true;
            for (const auto &file : items) {
                known &= file.entry().contains(KIO::UDSEntry::UDS_SIZE);
                bytes += file.size();
            }
            if (known)
                size = tr("Size: %1").arg(locale().formattedDataSize(bytes));
        }
        update();
    }

protected:
    void paintEvent(QPaintEvent *) override
    {
        QPainter p(this);
        p.fillRect(rect(), classic::light);
        p.setPen(classic::text);
        if (mixed)
            p.drawPixmap(17, -2, asset(QStringLiteral("mixed-selection")));
        else
            p.drawPixmap(17, -2, icon.pixmap(QSize(48, 48), devicePixelRatioF()));
        const QFontMetricsF metrics(p.font());
        auto advance = [&metrics](const QString &text) { return int(std::ceil(metrics.horizontalAdvance(text))); };
        auto draw = [&](int x, int y, const QString &text, int available) {
            if (!text.isEmpty() && available > 0)
                p.drawText(QPoint(x, y), advance(text) <= available ? text : metrics.elidedText(text, Qt::ElideRight, available));
        };
        const int left = type.isEmpty() ? 79 : 77;
        const int right = width() - 8;
        const int first = qMin(qMax(advance(name), advance(type)), qMax(0, (right - left) / 2));
        draw(left, 16, name, modified.isEmpty() ? right - left : first);
        draw(left, 34, type, modified.isEmpty() ? right - left : first);
        const int second = left + first + 4;
        const int third = second + qMax(210, advance(modified) + 12);
        draw(second, 16, modified, right - second);
        const int sizeLeft = second + qMax(0, advance(tr("Date modified:")) - advance(tr("Size:")));
        draw(sizeLeft, 34, size, right - sizeLeft);
        draw(third, 16, created, right - third);
    }

private:
    QString dateProperty(const QString &label, const KFileItemList &items, KFileItem::FileTimes field) const
    {
        QDateTime first, last;
        for (const auto &item : items) {
            const auto date = item.time(field);
            if (!date.isValid())
                return {};
            if (!first.isValid() || date < first)
                first = date;
            if (!last.isValid() || last < date)
                last = date;
        }
        if (!first.isValid())
            return {};
        const auto from = absoluteDate(first, locale());
        const auto to = absoluteDate(last, locale());
        return label.arg(from == to ? from : from + QStringLiteral(" - ") + to);
    }
};

class ActivityChanges : public QObject
{
    Q_OBJECT
public:
    explicit ActivityChanges(QObject *parent) : QObject(parent)
    {
        const auto query = ExplorerPrivacy::activityQuery();
        auto bus = QDBusConnection::sessionBus();
        subscribed = bus.connect(query.service(), query.path(), query.interface(),
            QStringLiteral("CurrentActivityChanged"), this, SLOT(invalidate()));
        auto *service = new QDBusServiceWatcher(query.service(), bus, QDBusServiceWatcher::WatchForOwnerChange, this);
        connect(service, &QDBusServiceWatcher::serviceOwnerChanged, this, &ActivityChanges::invalidate);
    }
    quint64 generation() const { return subscribed ? epoch : 0; }

private slots:
    void invalidate() { ++epoch; }

private:
    bool subscribed;
    quint64 epoch = 1;
};

static ActivityChanges &activityChanges()
{
    static auto *monitor = new ActivityChanges(qApp);
    return *monitor;
}

struct FrequentVisit {
    static inline QSemaphore slotsAvailable{32};
    QUrl url;
    quint64 activityGeneration;
    std::unique_ptr<ExplorerPrivacy> permit;
    ~FrequentVisit() { slotsAvailable.release(); }
};

static QThreadPool &frequentPool(bool preparing)
{
    struct Pool : QThreadPool { explicit Pool(int threads) { setMaxThreadCount(threads); } };
    static Pool prepare(2), record(1);
    return preparing ? prepare : record;
}

static QUrl listingRoot(QUrl url)
{
    // KDirLister cleans paths even when KDirOperator's startup URL still contains dot segments.
    url.setPath(QDir::cleanPath(url.path()));
    return url.adjusted(QUrl::StripTrailingSlash);
}

using PreparedVisit = std::shared_ptr<FrequentVisit>;

static void prepareVisit(QObject *context, const QUrl &url, std::function<void(PreparedVisit)> ready)
{
    if (!ExplorerFrequent::candidate(url)) {
        ready({});
        return;
    }
    const auto generation = activityChanges().generation();
    if (!generation) {
        qWarning("win7-explorer: cannot watch Activity changes; visit not recorded");
        ready({});
        return;
    }
    auto promise = std::make_shared<QPromise<PreparedVisit>>();
    auto future = promise->future();
    promise->start();
    if (!frequentPool(true).tryStart([promise, url, generation] {
        if (FrequentVisit::slotsAvailable.tryAcquire()) {
            auto visit = std::make_shared<FrequentVisit>();
            visit->url = url;
            visit->activityGeneration = generation;
            visit->permit = std::make_unique<ExplorerPrivacy>();
            if (!visit->permit->visitActivity().isEmpty() && visit->permit->bindDestination(url.toLocalFile()))
                promise->addResult(std::move(visit));
        } else {
            qWarning("win7-explorer: Frequent recorder is busy; visit not recorded");
        }
        promise->finish();
    })) {
        qWarning("win7-explorer: Frequent policy worker is busy; visit not recorded");
        ready({});
        return;
    }
    // Navigation waits only for a bounded preflight, never for an I/O request to return.
    // Once navigation has started without a permit, a late result cannot authorize it.
    auto *deadline = new QTimer(context);
    deadline->setSingleShot(true);
    deadline->setTimerType(Qt::PreciseTimer);
    auto *watch = new QFutureWatcher<PreparedVisit>(deadline);
    QObject::connect(deadline, &QTimer::timeout, deadline, [deadline, watch, ready] {
        QObject::disconnect(watch, nullptr, deadline, nullptr);
        watch->future().cancel();
        deadline->deleteLater();
        qWarning("win7-explorer: Frequent preflight timed out; visit not recorded");
        ready({});
    });
    QObject::connect(watch, &QFutureWatcher<PreparedVisit>::finished, deadline, [deadline, watch, ready] {
        deadline->stop();
        const auto permit = watch->future().resultCount() ? watch->result() : PreparedVisit{};
        deadline->deleteLater();
        ready(permit);
    });
    watch->setFuture(future);
    deadline->start(180);
}

static void completeVisit(PreparedVisit visit)
{
    if (activityChanges().generation() != visit->activityGeneration)
        return;
    // A reply on the same bus fences Activity signals already sent when KIO finished.
    // A sample alone would miss a public → private → public transition during listing.
    auto *watch = new QDBusPendingCallWatcher(
        QDBusConnection::sessionBus().asyncCall(ExplorerPrivacy::activityQuery(), 100), qApp);
    QObject::connect(watch, &QDBusPendingCallWatcher::finished, watch, [watch, visit = std::move(visit)] {
        const QDBusPendingReply<QString> reply = *watch;
        watch->deleteLater();
        if (activityChanges().generation() != visit->activityGeneration || reply.isError()
            || reply.value() != visit->permit->visitActivity())
            return;
        frequentPool(false).start([visit] { ExplorerFrequent::record(visit->url, *visit->permit); });
    });
}

class Explorer : public QMainWindow
{
public:
    explicit Explorer(const QUrl &start, PreparedVisit visit = {})
    {
        setAttribute(Qt::WA_DeleteOnClose);
        auto *central = new QWidget;
        auto *column = new QVBoxLayout(central);
        column->setContentsMargins(0, 0, 0, 0);
        column->setSpacing(0);
        setCentralWidget(central);

        files = new Files(isOverviewUrl(start) ? QUrl::fromLocalFile(QDir::homePath()) : start, this);
        if (visit && visit->url == listingRoot(files->url()))
            pendingVisit = std::move(visit);
        files->navigate = [this](const QUrl &url, bool clearForward) { navigate(url, clearForward); };
        auto *properties = files->action(KDirOperator::Properties);
        // Keep KDirOperator's action state and shortcut, but use Explorer's native-dialog subclass.
        disconnect(properties, &QAction::triggered, files, nullptr);
        connect(properties, &QAction::triggered, this, [this] { showExplorerProperties(files->selectedItems(), files); });
        files->onMenu = [this](const KFileItem &item, const QPoint &pos) { contextMenu(item, pos); };
        files->onOpenFolder = [this](const QUrl &url) { openFolder(url); };
        files->setMode(KFile::Files);
        files->setFollowNewDirectories(false);
        KConfig config(QStringLiteral("win7-explorer-optionsrc"), KConfig::SimpleConfig);
        foldersInNewWindow = config.group("General").readEntry("OpenFoldersInNewWindow", false);
        const auto options = config.group("View");
        thumbnails = options.readEntry("Thumbnails", true);
        files->setInlinePreviewShown(thumbnails);
        if (options.hasKey("ShowHidden"))
            files->setShowHiddenFiles(options.readEntry("ShowHidden", false));
        // KDirOperator remembers its preview panel from file dialogs; Explorer starts without one.
        if (files->action(KDirOperator::ShowPreviewPanel)->isChecked())
            files->action(KDirOperator::ShowPreviewPanel)->trigger();

        nav->go = [this](const QUrl &url) { navigate(url); };
        nav->back = [this] { step(-1); };
        nav->forward = [this] { step(1); };
        nav->refresh = [this] { refresh(); };
        nav->history = [this] { return QList<QUrl>(history.rbegin(), history.rend()); };
        nav->places = [this] { return pane->places(); };
        column->addWidget(nav);
        commands();
        column->addWidget(fileMenuBar);
        column->addWidget(bar);

        pane->go = nav->go;
        auto *splitter = new QSplitter;
        splitter->setHandleWidth(3);
        splitter->setStyleSheet(QStringLiteral("QSplitter::handle { background: rgb(212, 208, 200); }"));
        splitter->addWidget(pane);
        pages->addWidget(files);
        pages->addWidget(overview);
        splitter->addWidget(pages);
        connect(overview->tiles, &QListWidget::itemActivated, this, [this](QListWidgetItem *item) {
            const auto target = item->data(OverviewTiles::Target).toUrl();
            if (history.value(position) == computerUrl) {
                const auto mountId = browseableMountId(target.toLocalFile());
                if (!mountId || mountId != item->data(OverviewTiles::MountId).toULongLong()) {
                    QMessageBox::warning(this, tr("Volume unavailable"),
                                         tr("Cannot open %1. The volume was unmounted, replaced or is no longer accessible. Refresh Computer and try again.")
                                             .arg(target.toLocalFile()));
                    return;
                }
            }
            navigate(target);
        });
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
        connect(detailsPaneAction, &QAction::toggled, gap, &QWidget::setVisible);

        empty = new QLabel(QStringLiteral("This folder is empty."), files);
        empty->setAttribute(Qt::WA_TransparentForMouseEvents);
        empty->hide();

        connect(files, &KDirOperator::urlEntered, this, [this](const QUrl &url) {
            // The hidden KDirOperator can still receive a watched-folder rename.
            if (!inOverview() || openingFolder)
                entered(url);
        });
        connect(files, &KDirOperator::fileSelected, this, &Explorer::open);
        connect(files, &KDirOperator::finishedLoading, this, &Explorer::updateDetails);
        connect(files, &KDirOperator::finishedLoading, this, &Explorer::hideFocus);
        // finishedLoading also means canceled or failed, and a reload clears the proxy before any items arrive.
        auto *lister = files->dirLister();
        const auto invalidateListing = [this] {
            listedUrl.clear();
            empty->hide();
        };
        connect(lister, &KDirLister::clear, this, invalidateListing);
        const auto invalidateCurrent = [this, invalidateListing](const QUrl &url) {
            if (listingRoot(url) == listingRoot(files->url()))
                invalidateListing();
        };
        connect(lister, &KDirLister::started, this, invalidateCurrent);
        connect(lister, &KDirLister::listingDirCanceled, this, [this, invalidateCurrent](const QUrl &url) {
            invalidateCurrent(url);
            if (pendingVisit && pendingVisit->url == listingRoot(url))
                pendingVisit.reset();
        });
        connect(lister, &KDirLister::jobError, this, [this] { pendingVisit.reset(); });
        connect(lister, &KDirLister::listingDirCompleted, this, [this](const QUrl &url) {
            if (listingRoot(url) == listingRoot(files->url())) {
                listedUrl = listingRoot(url);
                if (pendingVisit && pendingVisit->url == listedUrl)
                    completeVisit(std::exchange(pendingVisit, {}));
                QMetaObject::invokeMethod(this, &Explorer::updateDetails, Qt::QueuedConnection);
            }
        });
        connect(lister, &KDirLister::redirection, this, [this](const QUrl &oldUrl, const QUrl &newUrl) {
            // KDirOperator also emits urlEntered for a root rename, which isn't a visit.
            pendingVisit.reset();
            // A root rename keeps the rows and does not list again; other root redirects emit clear first.
            if (listedUrl == listingRoot(oldUrl) && listingRoot(newUrl) == listingRoot(files->url())) {
                listedUrl = listingRoot(newUrl);
                updateDetails();
            }
        });
        connect(files, &KDirOperator::viewChanged, this, [this](QAbstractItemView *view) {
            view->setFrameShape(QFrame::NoFrame);
            // With the scroll bar "as needed", QListView always reserves its width, which costs Windows' fifth column.
            // Windows reflows only once the bar appears, so the bar is switched off until there is something to scroll.
            view->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
            connect(view->verticalScrollBar(), &QScrollBar::rangeChanged, view, [view](int, int max) {
                view->setVerticalScrollBarPolicy(max > 0 ? Qt::ScrollBarAlwaysOn : Qt::ScrollBarAlwaysOff);
            });
            view->installEventFilter(this);
            view->viewport()->installEventFilter(this);
            if (viewIndex == Tiles || viewIndex == Content) {
                auto *list = static_cast<QListView *>(view);
                list->setItemDelegate(new RichFileDelegate(viewIndex == Tiles, list));
                list->setStyleSheet(viewIndex == Tiles ? QStringLiteral("QListView { padding: 4px 0 0 8px; }")
                                                       : QStringLiteral("QListView { padding-top: 7px; }"));
            }
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
            // Loading and selection alone miss additions/removals in a folder that's already open.
            constexpr auto connection = Qt::ConnectionType(Qt::QueuedConnection | Qt::UniqueConnection);
            connect(view->model(), &QAbstractItemModel::rowsInserted, this, &Explorer::updateDetails, connection);
            connect(view->model(), &QAbstractItemModel::rowsRemoved, this, &Explorer::updateDetails, connection);
            connect(view->model(), &QAbstractItemModel::modelReset, this, &Explorer::updateDetails, connection);
            connect(view->model(), &QAbstractItemModel::dataChanged, this, &Explorer::updateDetails, connection);
            QTimer::singleShot(0, this, &Explorer::updateDetails);
        });
        connect(QApplication::clipboard(), &QClipboard::dataChanged, this, &Explorer::updateActions);
        connect(KIO::FileUndoManager::self(), &KIO::FileUndoManager::undoAvailable, this, &Explorer::updateActions);
        connect(KIO::FileUndoManager::self(), &KIO::FileUndoManager::redoAvailable, this, &Explorer::updateActions);
        // Filtering the view's model rather than KDirLister's name filter, which always shows folders.
        connect(nav->search, &QLineEdit::textChanged, this, [this](const QString &text) {
            if (inOverview()) {
                overview->filter(text);
                return;
            }
            proxy()->setFilterCaseSensitivity(Qt::CaseInsensitive);
            proxy()->setFilterFixedString(text);
            updateDetails();
        });
        // Explorer's Delete moves to the Recycle Bin; Shift+Delete deletes.
        files->action(KDirOperator::Trash)->setShortcut(QKeySequence::Delete);
        files->action(KDirOperator::Delete)->setShortcut(Qt::SHIFT | Qt::Key_Delete);
        files->action(KDirOperator::Reload)->setShortcut({});
        auto *reload = action(tr("Refresh"), Qt::Key_F5, {}, [this] { refresh(); });
        auto *address = action(QStringLiteral("Address"), QKeySequence(Qt::ALT | Qt::Key_D), QString(), [this] { nav->editAddress(); });
        auto *find = action(QStringLiteral("Search"), QKeySequence(Qt::CTRL | Qt::Key_E), QString(), [this] { nav->search->setFocus(); });
        // KDirOperator's Back/Forward report enabled with no history, so Explorer keeps its own (as Windows' recent pages).
        files->action(KDirOperator::Back)->setShortcut({});
        files->action(KDirOperator::Forward)->setShortcut({});
        auto *back = action(QStringLiteral("Back"), QKeySequence(Qt::ALT | Qt::Key_Left), QString(), [this] { step(-1); });
        auto *forward = action(QStringLiteral("Forward"), QKeySequence(Qt::ALT | Qt::Key_Right), QString(), [this] { step(1); });
        folderShortcuts = {files->action(KDirOperator::Trash), files->action(KDirOperator::Delete), files->action(KDirOperator::Rename),
                           files->action(KDirOperator::Properties), files->action(KDirOperator::Up), cut, copy, paste, selectAll};
        addActions(folderShortcuts);
        addActions({back, forward, reload, undo, redo, closeWindow, address, find});

        for (auto mode : {KDirOperator::SortByName, KDirOperator::SortByDate, KDirOperator::SortByType, KDirOperator::SortBySize,
                          KDirOperator::SortAscending, KDirOperator::SortDescending}) {
            connect(files->action(mode), &QAction::triggered, this, [this] { rememberSort(); });
        }
        entered(isOverviewUrl(start) ? start : files->url());
        resize(760, 534);
        if (!inOverview())
            files->view()->setFocus();  // Windows starts with the keyboard in the file list
    }

    ~Explorer() override
    {
        // KIO may emit listing or selection signals while QWidget tears down the file view,
        // after Explorer's listing state is already destroyed.
        disconnect(files->dirLister(), nullptr, this, nullptr);
        for (auto *sender : files->findChildren<QObject *>())
            disconnect(sender, nullptr, this, nullptr);
        disconnect(files, nullptr, this, nullptr);
        if (auto *view = files->view()) {
            view->removeEventFilter(this);
            view->viewport()->removeEventFilter(this);
        }
    }

    bool isAt(const QUrl &url) const { return listingRoot(files->url()) == listingRoot(url); }

protected:
    // KDirOperator's icon view sizes its grid from the font after every resize; Explorer's grid is reapplied after it.
    bool eventFilter(QObject *watched, QEvent *event) override
    {
        auto *view = files->view();
        if (!view)
            return false;
        if ((watched == view || watched == view->viewport())
            && (event->type() == QEvent::Move || event->type() == QEvent::Resize))
            QTimer::singleShot(0, this, &Explorer::layoutEmptyMessage);
        if (watched != view)
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
    QStackedWidget *pages = new QStackedWidget;
    Overview *overview = new Overview;
    QList<QAction *> folderShortcuts, folderCommands;
    bool openingFolder = false;

    bool inOverview() const { return pages->currentWidget() == overview; }

    bool canNavigateTo(const QUrl &url)
    {
        constexpr auto options = QUrl::NormalizePathSegments | QUrl::StripTrailingSlash;
        const QUrl target = url.adjusted(options);
        if (std::ranges::none_of(libraries, [&target](const Library &library) {
            return target == standardFolder(library.location).adjusted(options);
        }))
            return true;
        const QString path = target.toLocalFile();
        // KDirOperator treats an unreadable target as a filename and can open its parent instead.
        if (!QFileInfo(path).isDir() || ::access(QFile::encodeName(path).constData(), R_OK | X_OK) != 0) {
            QMessageBox warning(QMessageBox::Warning, tr("Folder unavailable"),
                                tr("Cannot open %1. The folder is missing or not accessible.").arg(path),
                                QMessageBox::Ok, this);
            warning.setTextFormat(Qt::PlainText);
            warning.exec();
            return false;
        }
        return true;
    }

    void refresh()
    {
        if (inOverview()) {
            overview->load(history[position]);
            overview->filter(nav->search->text());
            updateDetails();
        } else {
            files->rereadDir();
        }
    }
    NavigationBand *nav = new NavigationBand;
    CommandBar *bar = new CommandBar;
    NavigationPane *pane = new NavigationPane;
    DetailsPane *details = new DetailsPane;
    QIcon folderIcon;
    QMenu *openMenu = new QMenu(this);
    QLabel *empty;
    QUrl listedUrl;
    PreparedVisit pendingVisit;
    quint64 navigation = 0;
    QActionGroup *views = new QActionGroup(this);
    QActionGroup *backgroundViews = new QActionGroup(this);
    QMenuBar *fileMenuBar = new QMenuBar;
    QAction *detailsPaneAction;
    bool foldersInNewWindow;
    bool thumbnails;
    int viewIndex = -1;
    int iconSize = 96;
    bool keyboardUsed = false;
    QList<QUrl> history;
    qsizetype position = -1;
    bool stepping = false;
    KFileItemActions openWith;
    QAction *print = action(tr("&Print"), {}, {}, [this] { printText(files->selectedItems()); });
    QAction *cut = action(QStringLiteral("Cu&t"), QKeySequence::Cut, QStringLiteral("edit-cut"), [this] { toClipboard(true); });
    QAction *copy = action(QStringLiteral("&Copy"), QKeySequence::Copy, QStringLiteral("edit-copy"), [this] { toClipboard(false); });
    QAction *paste = action(QStringLiteral("&Paste"), QKeySequence::Paste, QStringLiteral("edit-paste"), [this] { pasteInto(files->url()); });
    QAction *undo = action(QStringLiteral("&Undo"), QKeySequence::Undo, QString(), [this] { undoRedo(false); });
    QAction *redo = action(QStringLiteral("&Redo"), QKeySequence::Redo, QString(), [this] { undoRedo(true); });
    QAction *closeWindow = action(QStringLiteral("&Close"), QKeySequence(Qt::CTRL | Qt::Key_W), QString(), [this] { close(); });
    QAction *selectAll = action(QStringLiteral("Select &all"), QKeySequence::SelectAll, QString(), [this] { files->view()->selectAll(); });

    QAction *action(const QString &text, QKeySequence key, const QString &icon, std::function<void()> slot)
    {
        auto *a = new QAction(QIcon::fromTheme(icon), text, this);
        a->setShortcut(key);
        connect(a, &QAction::triggered, this, slot);
        return a;
    }

    void undoRedo(bool forward)
    {
        auto *manager = KIO::FileUndoManager::self();
        manager->uiInterface()->setParentWidget(this);
        forward ? manager->redo() : manager->undo();
    }

    void folderOptions()
    {
        QDialog dialog(this);
        dialog.setWindowTitle(tr("Folder Options"));
        auto *layout = new QVBoxLayout(&dialog);
        auto *scope = new QLabel(tr("These options apply only to Explorer."), &dialog);
        auto *tabs = new QTabWidget(&dialog);
        auto *general = new QWidget(tabs);
        auto *browse = new QGroupBox(tr("Browse folders"), general);
        auto *same = new QRadioButton(tr("Open each folder in the &same window"), browse);
        auto *own = new QRadioButton(tr("Open each folder in its &own window"), browse);
        (foldersInNewWindow ? own : same)->setChecked(true);
        auto *choices = new QVBoxLayout(browse);
        choices->addWidget(same);
        choices->addWidget(own);
        auto *generalLayout = new QVBoxLayout(general);
        generalLayout->addWidget(browse);
        generalLayout->addStretch();
        tabs->addTab(general, tr("&General"));

        auto *view = new QWidget(tabs);
        auto *viewLayout = new QVBoxLayout(view);
        auto *hidden = new QCheckBox(tr("Show &hidden files"), view);
        auto *icons = new QCheckBox(tr("Show &thumbnails instead of file icons"), view);
        hidden->setChecked(files->showHiddenFiles());
        icons->setChecked(thumbnails);
        viewLayout->addWidget(hidden);
        viewLayout->addWidget(icons);
        viewLayout->addStretch();
        tabs->addTab(view, tr("&View"));

        auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dialog);
        layout->addWidget(scope);
        layout->addWidget(tabs);
        layout->addWidget(buttons);
        connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
        connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
        if (dialog.exec() != QDialog::Accepted)
            return;
        KConfig config(QStringLiteral("win7-explorer-optionsrc"), KConfig::SimpleConfig);
        const auto warn = [&] {
            QMessageBox::warning(this, dialog.windowTitle(), tr("Could not save Explorer's folder options."));
        };
        const auto edits = {std::tuple{"General", "OpenFoldersInNewWindow", foldersInNewWindow, own->isChecked()},
                            {"View", "ShowHidden", files->showHiddenFiles(), hidden->isChecked()},
                            {"View", "Thumbnails", thumbnails, icons->isChecked()}};
        // KConfig can discard a locked write without making sync() fail.
        for (const auto &[group, key, before, after] : edits) {
            const auto target = config.group(group);
            if (before != after && (target.isImmutable() || target.isEntryImmutable(key))) {
                warn();
                return;
            }
        }
        for (const auto &[group, key, before, after] : edits) {
            if (before != after)
                config.group(group).writeEntry(key, after);
        }
        if (!config.sync()) {
            // Don't let KConfig retry rejected edits on destruction if writes recover during the warning.
            config.markAsClean();
            warn();
            return;
        }
        foldersInNewWindow = own->isChecked();
        files->setShowHiddenFiles(hidden->isChecked());
        thumbnails = icons->isChecked();
        files->setInlinePreviewShown(thumbnails);
        files->previewGenerator()->setPreviewShown(thumbnails);
    }

    void commands()
    {
        auto *organize = new QMenu(this);
        organize->addActions({cut, copy, paste, undo, redo});
        organize->addSeparator();
        organize->addAction(selectAll);
        organize->addSeparator();
        auto *layout = organize->addMenu(QStringLiteral("&Layout"));
        auto toggle = [layout](const QString &text, QWidget *target, bool visible = true) {
            auto *a = layout->addAction(text);
            a->setCheckable(true);
            a->setChecked(visible);
            target->setVisible(visible);
            QObject::connect(a, &QAction::toggled, target, &QWidget::setVisible);
            return a;
        };
        fileMenuBar->setNativeMenuBar(false);
        toggle(QStringLiteral("&Menu bar"), fileMenuBar, false);
        layout->addSeparator();
        detailsPaneAction = toggle(QStringLiteral("&Details pane"), details);
        auto *preview = files->action(KDirOperator::ShowPreviewPanel);
        preview->setText(QStringLiteral("&Preview pane"));
        preview->setIcon(assetIcon(QStringLiteral("preview-pane")));
        layout->addAction(preview);
        toggle(QStringLiteral("&Navigation pane"), pane);
        auto *options = organize->addAction(QStringLiteral("&Folder and search options"), this, &Explorer::folderOptions);
        organize->addSeparator();
        auto *trash = files->action(KDirOperator::Trash);
        auto *rename = files->action(KDirOperator::Rename);
        trash->setText(QStringLiteral("&Delete"));
        organize->addAction(trash);
        // Changing the KIO action's text would also change the file-item menu, including after overflow dismissal.
        auto *organizeRename = organize->addAction(rename->icon(), QStringLiteral("Re&name"), rename, &QAction::trigger);
        auto syncRename = [rename, organizeRename] { organizeRename->setEnabled(rename->isEnabled()); };
        connect(rename, &QAction::changed, organizeRename, syncRename);
        syncRename();
        auto *properties = organize->addAction(QStringLiteral("P&roperties"), this, [this] {
            const auto items = files->selectedItems();
            if (items.isEmpty())
                showExplorerProperties(files->url(), this);
            else
                showExplorerProperties(items, files);
        });
        organize->addSeparator();
        organize->addAction(closeWindow);
        connect(organize, &QMenu::aboutToShow, this, &Explorer::updateActions);

        // Windows libraries collect folders; here a library is the XDG folder, and including adds a link to it.
        auto *library = new QMenu(this);
        for (const auto &entry : libraries)
            library->addAction(assetIcon(QString::fromLatin1(entry.icon)), QString::fromLatin1(entry.name), this, [this, location = entry.location] {
                const KFileItemList selection = files->selectedItems();
                if (inOverview() || !canIncludeInLibrary(selection))
                    return;
                // KDirOperator appends a slash; KIO names the link using QUrl::fileName().
                const auto sources = selection.isEmpty() ? QList<QUrl>{files->url().adjusted(QUrl::StripTrailingSlash)}
                                                         : selection.urlList();
                auto *job = KIO::link(sources, standardFolder(location));
                job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
            });
        auto *share = new QMenu(this);
        share->addAction(QStringLiteral("Specific people..."), this, [this] {
            const KFileItemList selection = files->selectedItems();
            showExplorerProperties(selection.isEmpty() ? files->url() : selection.first().url(), this);
        });

        auto *viewMenu = new QMenu(this);
        static const char *const labels[] = {"Extra Large Icons", "Large Icons", "Medium Icons", "Small Icons",
                                            "List", "Details", "Tiles", "Content"};
        for (int i = ExtraLarge; i <= Content; ++i) {
            auto *a = viewMenu->addAction(viewIcon(i), QString::fromLatin1(labels[i]), this, [this, i] { chooseView(i); });
            a->setCheckable(true);
            views->addAction(a);
            if (i >= Small && i < Content)
                viewMenu->addSeparator();
        }
        // The background chooser keeps its six modes and its own List artwork.
        for (int i = ExtraLarge; i <= Details; ++i) {
            auto *a = backgroundViews->addAction(i == List ? assetIcon(QStringLiteral("view-list")) : viewIcon(i),
                                                 QString::fromLatin1(labels[i]));
            a->setCheckable(true);
            connect(a, &QAction::triggered, this, [this, i] { chooseView(i); });
        }
        auto *fileMenu = fileMenuBar->addMenu(QStringLiteral("&File"));
        auto *newFolder = fileMenu->addAction(QStringLiteral("New &folder"), files, &KDirOperator::mkdir);
        fileMenu->addSeparator();
        fileMenu->addActions({trash, rename, properties});
        fileMenu->addSeparator();
        fileMenu->addAction(closeWindow);
        auto *editMenu = fileMenuBar->addMenu(QStringLiteral("&Edit"));
        editMenu->addActions({undo, redo});
        editMenu->addSeparator();
        editMenu->addActions({cut, copy, paste, selectAll});
        auto *menuView = fileMenuBar->addMenu(QStringLiteral("&View"));
        menuView->addActions(viewMenu->actions());
        menuView->addSeparator();
        menuView->addAction(tr("Refresh"), this, &Explorer::refresh);
        fileMenuBar->addMenu(QStringLiteral("&Tools"))->addAction(options);
        fileMenuBar->addMenu(QStringLiteral("&Help"))->addAction(QStringLiteral("&Help"), this, [this] { openUrl(QUrl(QStringLiteral("help:/"))); });
        for (auto *menu : {fileMenu, editMenu})
            connect(menu, &QMenu::aboutToShow, this, &Explorer::updateActions);
        folderCommands = {cut, copy, paste, selectAll, trash, rename, properties, preview, newFolder};
        folderCommands.append(views->actions());
        connect(openMenu, &QMenu::aboutToShow, this, [this] {
            openMenu->clear();
            const auto items = files->selectedItems();
            if (items.size() != 1 || items.first().isDir())
                return;
            openWith.setItemListProperties(KFileItemListProperties(items));
            openWith.setParentWidget(this);
            openWith.insertOpenWithActionsTo(nullptr, openMenu, {});
        });
        bar->left = {{QStringLiteral("Organize"), {}, organize, {}},
                     {QStringLiteral("Open"), {}, nullptr, [this] { openItems(files->selectedItems()); }},
                     {QStringLiteral("Include in library"), {}, library, {}},
                     {QStringLiteral("Share with"), {}, share, {}},
                     {tr("Print"), {}, nullptr, {}, nullptr, print},
                     {QStringLiteral("New folder"), {}, nullptr, [this] { files->mkdir(); }}};
        bar->right = {{QStringLiteral("View"), assetIcon(QStringLiteral("view-large")), viewMenu,
                       [this] { chooseView((viewIndex + 1) % views->actions().size()); }, views},
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
        // Changing mode destroys the popup's old focus widget before Qt can restore it.
        QTimer::singleShot(0, this, [this] { files->view()->setFocus(); });
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

    static QIcon viewIcon(int index)
    {
        static const char *const icons[] = {"view-extra-large", "view-large", "view-medium", "view-small",
                                           "view-command-list", "view-details", "view-tiles", "view-list"};
        return assetIcon(QString::fromLatin1(icons[index]));
    }

    void setView(int index)
    {
        if (viewIndex == index)
            return;
        const QPersistentModelIndex current(files->view() ? files->view()->currentIndex() : QModelIndex());
        viewIndex = index;
        files->presentation = index;
        static const int sizes[] = {256, 96, 48, 16, 16, 16, 48, 32};
        const auto mode = index == Details ? KDirOperator::ViewDetailsView
            : index == Small || index == List ? KDirOperator::ViewCompactView : KDirOperator::ViewIconsView;
        files->action(mode)->trigger();
        if (current.isValid())
            files->view()->selectionModel()->setCurrentIndex(current, QItemSelectionModel::NoUpdate);
        files->setIconSize(sizes[index]);
        // A new KIO view can start with the preview size despite a matching cached zoom.
        files->view()->setIconSize(QSize(sizes[index], sizes[index]));
        iconSize = index <= Medium ? sizes[index] : 0;
        views->actions()[index]->setChecked(true);
        if (index <= Details)
            backgroundViews->actions()[index]->setChecked(true);
        else if (auto *checked = backgroundViews->checkedAction())
            checked->setChecked(false);
        bar->right[0].icon = viewIcon(index);
        bar->relayout();
        applyGrid();
    }

    void applyGrid()
    {
        auto *list = qobject_cast<QListView *>(files->view());
        if (!list)
            return;
        if (viewIndex == Small) {
            // Small Icons fills across before wrapping; List fills down the column first.
            list->setFlow(QListView::LeftToRight);
            list->setStyleSheet(QStringLiteral("QListView { padding: 7px 0 0 16px; }"));
            list->setGridSize(QSize(231, qMax(21, list->fontMetrics().height() + 6)));
        } else if (iconSize) {
            list->setStyleSheet(QStringLiteral("QListView { padding: 7px 0 0 7px; background: white; }"));
            list->setGridSize(QSize(iconSize + 21, iconSize + 40));
        }
    }

    void explorerColumns(QTreeView *tree)
    {
        tree->setAlternatingRowColors(false);
        tree->setItemDelegateForColumn(KDirModel::Name, new DetailsNameDelegate(tree, files->dirLister()));
        auto *metadata = new DetailsMetadataDelegate(tree);
        for (int column : {KDirModel::ModifiedTime, KDirModel::Type, KDirModel::Size})
            tree->setItemDelegateForColumn(column, metadata);
        for (int column : {KDirModel::Permissions, KDirModel::Owner, KDirModel::Group})
            tree->setColumnHidden(column, true);
        tree->setColumnHidden(KDirModel::Type, false);
        QHeaderView *header = tree->header();
        header->moveSection(header->visualIndex(KDirModel::ModifiedTime), 1);
        header->moveSection(header->visualIndex(KDirModel::Type), 2);
        header->setStretchLastSection(false);
        header->setHighlightSections(false);
        // Section widths are logical pixels measured in w7-explorer-details.png at 96 DPI.
        for (auto [column, width] : {std::pair{KDirModel::Name, 272}, {KDirModel::ModifiedTime, 120}, {KDirModel::Type, 120}, {KDirModel::Size, 80}}) {
            header->setSectionResizeMode(column, QHeaderView::Interactive);
            header->resizeSection(column, width);
        }
    }

    void navigate(const QUrl &url, bool clearForward = true, qsizetype target = -1)
    {
        if (!canNavigateTo(url))
            return;
        const auto request = ++navigation;
        const auto normalized = url.isValid() ? url : QUrl::fromLocalFile(QDir::homePath());
        const auto folder = listingRoot(normalized);
        const auto move = [this, target](auto &&open) {
            const auto previous = position;
            stepping = target >= 0;
            if (stepping)
                position = target;
            open();
            if (std::exchange(stepping, false))
                position = previous;
        };
        if (isOverviewUrl(url)) {
            pendingVisit.reset();
            move([&] { entered(url); });
        } else if (folder == listingRoot(files->url())) {
            // The hidden folder is already listed; KIO will not emit urlEntered again.
            if (inOverview())
                move([&] { entered(files->url()); });
        } else {
            prepareVisit(this, folder, [this, request, url, clearForward, move](PreparedVisit visit) {
                if (request != navigation)
                    return;
                pendingVisit = std::move(visit);
                QScopedValueRollback opening(openingFolder, true);
                move([&] { files->KDirOperator::setUrl(url, clearForward); });
            });
        }
    }

    void entered(const QUrl &url)
    {
        if (pendingVisit && pendingVisit->url != listingRoot(url))
            pendingVisit.reset();
        const bool special = isOverviewUrl(url);
        if (special != inOverview()) {
            for (auto *a : folderCommands)
                a->setVisible(!special);
            for (auto *a : folderShortcuts) {
                if (special)
                    removeAction(a);
                else
                    addAction(a);
            }
            pages->setCurrentWidget(special ? static_cast<QWidget *>(overview) : files);
            bar->setOverview(special);
        }
        if (special) {
            overview->load(url);
            overview->tiles->setFocus();
        } else {
            restoreFolderView();
            // Computer may already have cleared the edit without touching the hidden folder model.
            proxy()->setFilterFixedString({});
        }
        const QString name = locationName(url);
        setWindowTitle(name);
        const QIcon icon = special ? assetIcon(url == computerUrl ? QStringLiteral("computer") : QStringLiteral("libraries"))
                                   : QIcon::fromTheme(KIO::iconNameForUrl(url));
        // As pixels: given a theme icon, Qt sends KWin only its name, and KWin looks it up in its own icon theme,
        // which doesn't follow the live switch to Windows mode's icons.
        QIcon pixels;
        for (int size : {16, 22, 32, 48})
            pixels.addPixmap(icon.pixmap(size));
        setWindowIcon(pixels);
        folderIcon = icon;
        if (!std::exchange(stepping, false) && (position < 0 || !url.matches(history[position], QUrl::StripTrailingSlash))) {
            history.resize(position + 1);
            history.append(url);
            position = history.size() - 1;
        }
        nav->search->clear();
        nav->search->setPlaceholderText(QStringLiteral("Search ") + name);
        nav->setState(url, history.value(position - 1), history.value(position + 1), icon);
        pane->setLocation(url);
        updateDetails();
    }

    void step(int by)
    {
        if (position + by < 0 || position + by >= history.size())
            return;
        navigate(history[position + by], true, position + by);
    }

    // Windows draws no focus rectangle until the keyboard is used, but loading and focusing the view make the first
    // item current in Qt, so that is undone afterwards. Arrow keys still start at the first item.
    void hideFocus()
    {
        if (!keyboardUsed)
            QTimer::singleShot(0, this, [this] {
                auto *selection = files->view()->selectionModel();
                if (!keyboardUsed && !selection->hasSelection())
                    selection->clearCurrentIndex();
            });
    }

    QSortFilterProxyModel *proxy() const { return static_cast<QSortFilterProxyModel *>(files->view()->model()); }

    void updateDetails()
    {
        if (inOverview()) {
            details->setItems({}, false, overview->tiles->isHidden() ? -1 : overview->tiles->count(), folderIcon);
            return;
        }
        const KFileItemList items = files->selectedItems();
        const int total = proxy()->rowCount();
        const bool filesOnly = !items.isEmpty() && std::ranges::all_of(items, &KFileItem::isFile);
        details->setItems(items, filesOnly, total, folderIcon);
        const bool printable = !localTextPath(items).isEmpty();
        print->setEnabled(printable);
        bar->setSelection(!items.isEmpty(), filesOnly ? items.first().iconName() : QStringLiteral("org.win7classic.explorer"),
                          items.size() == 1 && filesOnly ? openMenu : nullptr, canIncludeInLibrary(items), printable);
        updateActions();
        empty->setVisible(total == 0 && listedUrl == listingRoot(files->url()));
        layoutEmptyMessage();
    }

    void layoutEmptyMessage()
    {
        if (empty->isHidden())
            return;
        auto *view = files->view();
        QPoint top;
        if (auto *tree = qobject_cast<QTreeView *>(view); tree && !tree->header()->isHidden()) {
            // The painted header ends before the blank row inset (w7-explorer-empty-details.png).
            auto *headerFace = tree->header()->viewport();
            top.setY(headerFace->mapTo(view, QPoint(0, headerFace->height())).y());
        }
        empty->adjustSize();
        top.rx() += (view->width() - empty->width()) / 2;
        top.ry() += 16;
        empty->move(view->mapTo(files, top));
        empty->raise();
    }

    void updateActions()
    {
        files->syncSelectionActions();
        const bool any = !files->selectedItems().isEmpty();
        cut->setEnabled(any);
        copy->setEnabled(any);
        paste->setEnabled(!inOverview() && KUrlMimeData::urlsFromMimeData(QApplication::clipboard()->mimeData()).size() > 0);
        undo->setEnabled(KIO::FileUndoManager::self()->isUndoAvailable());
        redo->setEnabled(KIO::FileUndoManager::self()->isRedoAvailable());
    }

    void openUrl(const QUrl &url, const QString &mimeType = QString())
    {
        auto *job = new KIO::OpenUrlJob(url, mimeType);
        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
        job->setRunExecutables(false);
        job->start();
    }

    void open(const KFileItem &item) { openUrl(item.targetUrl(), item.mimetype()); }

    void openFolder(const QUrl &url)
    {
        if (foldersInNewWindow)
            prepareVisit(this, listingRoot(url), [url](PreparedVisit visit) { (new Explorer(url, std::move(visit)))->show(); });
        else
            navigate(url);
    }

    void openItems(const KFileItemList &items)
    {
        // Multiple selections must not replace each other in this view.
        if (items.size() == 1 && items.first().isDir()) {
            openFolder(items.first().targetUrl());
            return;
        }
        for (const auto &item : items) {
            if (foldersInNewWindow && item.isDir())
                openFolder(item.targetUrl());
            else
                open(item);
        }
    }

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

    static bool canIncludeInLibrary(const KFileItemList &items)
    {
        return std::ranges::all_of(items, &KFileItem::isDir);
    }

    static QString localTextPath(const KFileItemList &items)
    {
        if (items.size() != 1 || !items.first().isFile() || items.first().mimetype() != QLatin1String("text/plain"))
            return {};
        const QString path = items.first().url().toLocalFile();
        const QFileInfo file(path);
        return file.isFile() && file.isReadable() ? path : QString();
    }

    void printText(const KFileItemList &items)
    {
        const QString path = localTextPath(items);
        if (path.isEmpty())
            return;
        QFile file(path);
        if (!file.open(QIODevice::ReadOnly)) {
            QMessageBox::critical(this, tr("Print"), file.errorString());
            return;
        }
        const auto bytes = file.readAll();
        QStringDecoder decoder(QStringConverter::encodingForData(bytes).value_or(QStringConverter::Utf8));
        const QString text = decoder(bytes);
        if (file.error() != QFileDevice::NoError || decoder.hasError()) {
            QMessageBox::critical(this, tr("Print"), file.error() != QFileDevice::NoError ? file.errorString()
                                                                                       : tr("Cannot decode this text file as Unicode."));
            return;
        }
        QPrinter printer(QPrinter::HighResolution);
        printer.setDocName(QFileInfo(file).fileName());
        QPrintDialog dialog(&printer, this);
        if (dialog.exec() == QDialog::Accepted) {
            QTextDocument document;
            document.setPlainText(text);
            document.print(&printer);
            if (printer.printerState() == QPrinter::Error)
                QMessageBox::critical(this, tr("Print"), tr("The print job failed."));
        }
    }

    void createShortcut(QUrl source)
    {
        source = source.adjusted(QUrl::StripTrailingSlash);
        const QDir dir(source.adjusted(QUrl::RemoveFilename).toLocalFile());
        const QString base = tr("%1 - Shortcut").arg(source.fileName());
        QString dest = dir.filePath(base);
        for (int i = 2; QFileInfo::exists(dest) || QFileInfo(dest).isSymLink(); ++i)
            dest = dir.filePath(tr("%1 (%2)").arg(base).arg(i));
        auto *job = KIO::linkAs(source, QUrl::fromLocalFile(dest));
        // A raced collision must fail rather than offer to overwrite another file.
        job->setUiDelegate(nullptr);
        connect(job, &KJob::result, this, [this](KJob *result) {
            if (result->error())
                QMessageBox::critical(this, tr("Create shortcut"), result->errorString());
        });
        KIO::FileUndoManager::self()->recordCopyJob(job);
    }

    void contextMenu(const KFileItem &item, const QPoint &pos)
    {
        updateActions();
        QMenu menu(this);
        if (item.isNull()) {
            auto *view = menu.addMenu(QStringLiteral("&View"));
            view->addActions(backgroundViews->actions());
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
            menu.addAction(QStringLiteral("P&roperties"), this, [this] { showExplorerProperties(files->url(), this); });
        } else {
            const KFileItemList items = files->selectedItems().isEmpty() ? KFileItemList{item} : files->selectedItems();
            auto *openItem = menu.addAction(QStringLiteral("&Open"), this, [this, items] { openItems(items); });
            menu.setDefaultAction(openItem);
            if (!localTextPath(items).isEmpty()) {
                menu.addAction(print);
                const auto editors = KApplicationTrader::queryByMimeType(QStringLiteral("text/plain"), [](const KService::Ptr &service) {
                    return service->categories().contains(QStringLiteral("TextEditor"));
                });
                if (!editors.isEmpty())
                    menu.addAction(tr("&Edit"), this, [this, editor = editors.first(), items] {
                        auto *job = new KIO::ApplicationLauncherJob(editor);
                        job->setUrls(items.urlList());
                        job->setUiDelegate(KIO::createDefaultJobUiDelegate(KJobUiDelegate::AutoHandlingEnabled, this));
                        job->start();
                    });
            }
            openWith.setItemListProperties(KFileItemListProperties(items));
            openWith.setParentWidget(this);
            openWith.insertOpenWithActionsTo(nullptr, &menu, {});
            menu.addSeparator();
            menu.addActions({cut, copy});
            if (item.isDir())
                menu.addAction(QStringLiteral("&Paste"), this, [this, item] { pasteInto(item.url()); })->setEnabled(paste->isEnabled());
            menu.addSeparator();
            if (items.size() == 1 && items.first().url().isLocalFile() && (items.first().isFile() || items.first().isDir())
                && QFileInfo(files->url().toLocalFile()).isWritable())
                menu.addAction(tr("Create &shortcut"), this, [this, url = items.first().url()] { createShortcut(url); });
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
    const QCommandLineOption frequent(QStringLiteral("frequent-folder"), QStringLiteral("Open a Frequent folder"), QStringLiteral("path"));
    args.addOption(frequent);
    args.addPositionalArgument(QStringLiteral("url"), QStringLiteral("Folder to open (default: home)"));
    args.process(app);
    const QStringList urls = args.positionalArguments();
    if (args.isSet(frequent)) {
        const auto path = args.value(frequent);
        const auto url = QUrl::fromLocalFile(path);
        const auto error = [](const QString &message) {
            QMessageBox::warning(nullptr, QStringLiteral("Windows Explorer"), message);
            return 1;
        };
        if (!urls.isEmpty() || !ExplorerFrequent::available(path))
            return error(QStringLiteral("This folder is no longer available."));
        if (ExplorerFrequent::listing({path}) != ExplorerFrequent::Listing::Valid)
            return error(QStringLiteral("This folder is no longer in Explorer Frequent history."));
        QTimer::singleShot(0, &app, [&app, path, url, error] {
            prepareVisit(&app, listingRoot(url), [&app, path, url, error](PreparedVisit visit) {
                auto *window = new Explorer(url, std::move(visit));
                if (!window->isAt(url) || !ExplorerFrequent::available(path)) {
                    delete window;
                    app.exit(error(QStringLiteral("This folder is no longer available.")));
                } else if (ExplorerFrequent::listing({path}) != ExplorerFrequent::Listing::Valid) {
                    delete window;
                    app.exit(error(QStringLiteral("This folder is no longer in Explorer Frequent history.")));
                } else {
                    window->show();
                }
            });
        });
    } else if (urls.isEmpty()) {
        (new Explorer(QUrl::fromLocalFile(QDir::homePath())))->show();
    } else {
        for (const auto &u : urls) {
            const auto url = QUrl::fromUserInput(u, QDir::currentPath(), QUrl::AssumeLocalFile);
            prepareVisit(&app, listingRoot(url), [url](PreparedVisit visit) { (new Explorer(url, std::move(visit)))->show(); });
        }
    }
    const int result = app.exec();
    frequentPool(true).waitForDone();
    frequentPool(false).waitForDone();
    return result;
}

#include "main.moc"
