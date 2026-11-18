#include "FolderProperties.h"

#include "ClassicPrimitives.h"
#include <KPageWidget>
#include <KPropertiesDialog>
#include <QApplication>
#include <QDialogButtonBox>
#include <QGridLayout>
#include <QLabel>
#include <QPushButton>
#include <QStyle>
#include <QTabBar>
#include <QTabWidget>
#include <QTimer>

#include <functional>
#include <vector>

namespace {
class FolderProperties : public QObject
{
public:
    explicit FolderProperties(KPropertiesDialog *dialog) : QObject(dialog), dialog(dialog)
    {
        setObjectName(QStringLiteral("win7-folder-properties"));
        dialog->installEventFilter(this);
        refresh();
    }

private:
    KPropertiesDialog *const dialog;
    std::vector<std::function<void()>> restore;
    QWidget *general = nullptr;
    QLabel *created = nullptr;
    QList<QWidget *> rules;

    // Restoring in reverse order also handles paired min/max constraints.
    template<typename T, typename V, typename U = V>
    void change(T *object, V (T::*get)() const, void (T::*set)(U), V value)
    {
        restore.emplace_back([object, set, old = (object->*get)()] { (object->*set)(old); });
        (object->*set)(value);
    }

    template<typename T>
    void margins(T *layout, const QMargins &value)
    {
        restore.emplace_back([layout, old = layout->contentsMargins()] { layout->setContentsMargins(old); });
        layout->setContentsMargins(value);
    }

    void refresh()
    {
        // KDE may wrap the dialog in QStyleSheetStyle; only the application style has the mode name.
        const bool classic = QApplication::style()->name() == QStringLiteral("win7classic");
        if (classic == !restore.empty())
            return;
        if (!classic) {
            general->removeEventFilter(this);
            general->update();
            for (auto *rule : rules) {
                rule->removeEventFilter(this);
                rule->update();
            }
            for (auto it = restore.rbegin(); it != restore.rend(); ++it)
                (*it)();
            restore.clear();
        } else {
            auto *page = dialog->findChild<KPageWidget *>(QString(), Qt::FindDirectChildrenOnly);
            auto *tabs = page ? page->findChild<QTabWidget *>() : nullptr;
            general = tabs ? tabs->findChild<QWidget *>(QStringLiteral("KFilePropsPluginWidget")) : nullptr;
            auto *grid = general ? general->findChild<QGridLayout *>(QStringLiteral("gridLayout")) : nullptr;
            auto *icon = general ? general->findChild<QPushButton *>(QStringLiteral("iconButton")) : nullptr;
            created = general ? general->findChild<QLabel *>(QStringLiteral("createdTimeLabel_Left")) : nullptr;
            auto *identity = general ? general->findChild<QWidget *>(QStringLiteral("kseparator_2")) : nullptr;
            auto *storage = general ? general->findChild<QWidget *>(QStringLiteral("fsSeparator")) : nullptr;
            auto *iconLayout = general ? general->findChild<QHBoxLayout *>(QStringLiteral("iconLayout")) : nullptr;
            auto *buttons = dialog->buttonBox();
            if (!grid || !icon || !created || !identity || !storage || !iconLayout || !buttons || !buttons->layout()) {
                qWarning("Win7 Explorer: KDE folder Properties page layout has changed; cannot apply Classic presentation");
                return;
            }

            // Measurements in logical pixels from reference/screenshots/w7-properties.png.
            change(tabs, &QTabWidget::documentMode, &QTabWidget::setDocumentMode, false);
            change(tabs->tabBar(), &QTabBar::expanding, &QTabBar::setExpanding, false);
            margins(dialog->layout(), {4, 4, 4, 4});
            margins(page->layout(), {});
            margins(general->layout(), {14, 9, 14, 9});
            change(grid, &QGridLayout::horizontalSpacing, &QGridLayout::setHorizontalSpacing, 12);
            change(grid, &QGridLayout::verticalSpacing, &QGridLayout::setVerticalSpacing, 7);
            for (auto *label : general->findChildren<QLabel *>(QString(), Qt::FindDirectChildrenOnly)) {
                // Only leading-column captions; preserve alignment and selection in the value widgets.
                if (label->buddy())
                    change(label, &QLabel::alignment, &QLabel::setAlignment,
                           (label->alignment() & Qt::AlignVertical_Mask) | Qt::AlignLeading);
            }
            const int oldIndex = iconLayout->indexOf(icon);
            restore.emplace_back([iconLayout, icon, oldIndex] {
                iconLayout->removeWidget(icon);
                iconLayout->insertWidget(oldIndex, icon);
            });
            iconLayout->removeWidget(icon);
            iconLayout->insertWidget(0, icon);
            change<QWidget>(icon, &QWidget::minimumSize, &QWidget::setMinimumSize, QSize(38, 38));
            change<QWidget>(icon, &QWidget::maximumSize, &QWidget::setMaximumSize, QSize(38, 38));
            change<QAbstractButton>(icon, &QAbstractButton::iconSize, &QAbstractButton::setIconSize, QSize(32, 32));
            for (auto button : {QDialogButtonBox::Ok, QDialogButtonBox::Cancel}) {
                if (auto *widget = buttons->button(button))
                    change<QWidget>(widget, &QWidget::minimumSize, &QWidget::setMinimumSize, QSize(75, 23));
            }
            change<QLayout>(buttons->layout(), &QLayout::spacing, &QLayout::setSpacing, 6);
            rules = {identity, storage};
            for (auto *rule : rules) {
                change(rule, &QWidget::minimumSize, &QWidget::setMinimumSize, QSize(0, 2));
                change(rule, &QWidget::maximumSize, &QWidget::setMaximumSize, QSize(QWIDGETSIZE_MAX, 2));
                rule->installEventFilter(this);
            }
            general->installEventFilter(this);
            // KDE fixes the initial minimum before the Classic layout exists.
            change<QLayout>(dialog->layout(), &QLayout::sizeConstraint, &QLayout::setSizeConstraint, QLayout::SetNoConstraint);
        }
        dialog->layout()->invalidate();
        dialog->layout()->activate();
        const QSize minimum = dialog->minimumSizeHint();
        dialog->setMinimumSize(minimum);
        dialog->resize(classic ? minimum.expandedTo({358, 446}) : dialog->sizeHint());
    }

    bool eventFilter(QObject *object, QEvent *event) override
    {
        if (object == dialog && event->type() == QEvent::StyleChange) {
            // The child widgets also need to finish changing style before recomputing the layout.
            QTimer::singleShot(0, this, &FolderProperties::refresh);
        } else if (event->type() == QEvent::Paint && object != dialog) {
            if (object == general) {
                if (created->isVisible()) {
                    QPainter p(general);
                    const auto bounds = general->contentsRect().marginsRemoved(general->layout()->contentsMargins());
                    Classic::drawSeparator(p, {bounds.x(), created->y() - 5, bounds.width(), 2});
                }
            } else {
                auto *rule = static_cast<QWidget *>(object);
                QPainter p(rule);
                Classic::drawSeparator(p, rule->rect());
                return true;
            }
        }
        return false;
    }
};

class ExplorerFolderDialogs : public QObject
{
public:
    explicit ExplorerFolderDialogs(QWidget *explorer) : QObject(explorer), explorer(explorer)
    {
        qApp->installEventFilter(this);
    }

private:
    QWidget *const explorer;

    bool eventFilter(QObject *object, QEvent *event) override
    {
        // Watch the native Show so the KDirOperator action and the URL-based entries use the same skin.
        if (event->type() != QEvent::Show)
            return false;
        auto *dialog = qobject_cast<KPropertiesDialog *>(object);
        if (!dialog)
            return false;
        for (auto *parent = dialog->parentWidget(); parent; parent = parent->parentWidget()) {
            if (parent != explorer)
                continue;
            const auto items = dialog->items();
            if (items.size() == 1 && items.first().isDir() && items.first().url().isLocalFile()
                && !dialog->findChild<QObject *>(QStringLiteral("win7-folder-properties"), Qt::FindDirectChildrenOnly))
                new FolderProperties(dialog);
            break;
        }
        return false;
    }
};
}

void watchFolderProperties(QWidget *explorer)
{
    new ExplorerFolderDialogs(explorer);
}
