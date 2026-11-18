#include "ClassicPrimitives.h"
#include <KWindowShadow>
#include <QApplication>
#include <QEvent>
#include <QHash>
#include <QMenu>
#include <QProxyStyle>
#include <QStyleFactory>
#include <QStyleOption>
#include <QStylePlugin>
#include <QWidget>

class ClassicStyle : public QProxyStyle {
public:
    ClassicStyle() : QProxyStyle(QStyleFactory::create("Windows")) {
        if(!baseStyle()) qFatal("Win7Classic requires the Qt Windows style");
    }
    int pixelMetric(PixelMetric m,const QStyleOption *o=nullptr,const QWidget *w=nullptr) const override {
        if(m==PM_ScrollBarExtent) return 17;
        if(m==PM_ScrollBarSliderMin) return 14;
        if(m==PM_ExclusiveIndicatorWidth || m==PM_ExclusiveIndicatorHeight) return 13;
        if(m==PM_DefaultFrameWidth && w && w->property("classicFlatBorder").toBool()) return 1;
        return QProxyStyle::pixelMetric(m,o,w);
    }
    QSize sizeFromContents(ContentsType t,const QStyleOption *o,const QSize &s,const QWidget *w=nullptr) const override {
        QSize result=QProxyStyle::sizeFromContents(t,o,s,w);
        if(t==CT_ComboBox) result.setHeight(o->fontMetrics.height()+10);
        if(t==CT_MenuItem) {
            if(auto item=qstyleoption_cast<const QStyleOptionMenuItem *>(o)) {
                if(item->menuItemType!=QStyleOptionMenuItem::Separator) {
                    result.setHeight(qMax(o->fontMetrics.height()+6,item->icon.isNull()?0:18));
                    result.rwidth()-=item->maxIconWidth?6:1;
                }
            }
        }
        return result;
    }
    QRect subControlRect(ComplexControl c,const QStyleOptionComplex *o,SubControl sc,const QWidget *w=nullptr) const override {
        if(c==CC_ScrollBar && (o->state&State_Horizontal)) {
            QRect result=QProxyStyle::subControlRect(c,o,sc,w);
            // The native 17px control paints a 16px face; its thumb shares the leading button's last column.
            if(sc==SC_ScrollBarSubLine) result.adjust(0,0,-1,-1);
            else if(sc==SC_ScrollBarAddLine) result.adjust(1,0,0,-1);
            else if(sc==SC_ScrollBarSlider) result.adjust(-2,0,0,-1);
            else if(sc==SC_ScrollBarAddPage) result.adjust(0,0,1,-1);
            else if(sc==SC_ScrollBarSubPage) result.adjust(0,0,0,-1);
            return result;
        }
        if(c==CC_GroupBox && sc==SC_GroupBoxFrame)
            return o->rect.adjusted(0,(o->fontMetrics.height()+1)/2,0,0);
        if(c==CC_ComboBox && sc==SC_ComboBoxArrow)
            return visualRect(o->direction,o->rect,QRect(o->rect.right()-17,o->rect.top()+2,16,o->rect.height()-4));
        return QProxyStyle::subControlRect(c,o,sc,w);
    }
    QPalette standardPalette() const override { return Classic::palette(); }
    void polish(QPalette &p) override {
        if(p!=Classic::palette()) m_externalPalette=p;
        p=Classic::palette();
    }
    void polish(QApplication *app) override {
        QProxyStyle::polish(app);
        m_app=app;
        app->installEventFilter(this);
        enforcePalette();
        for(auto *widget : QApplication::topLevelWidgets())
            if(widget->isVisible()) addMenuShadow(widget);
    }
    void unpolish(QApplication *app) override {
        app->removeEventFilter(this);
        qDeleteAll(m_menuShadows);
        m_menuShadows.clear();
        m_app=nullptr;
        // KDE emits the destination palette before StyleChanged; keep that palette for the next style.
        app->setPalette(m_externalPalette);
        QProxyStyle::unpolish(app);
    }
    bool eventFilter(QObject *watched,QEvent *event) override {
        if(watched==m_app && event->type()==QEvent::ApplicationPaletteChange && !m_applyingPalette)
            enforcePalette();
        if(event->type()==QEvent::Show) addMenuShadow(watched);
        return QProxyStyle::eventFilter(watched,event);
    }
    void drawPrimitive(PrimitiveElement e,const QStyleOption *o,QPainter *p,const QWidget *w=nullptr) const override {
        const bool disabled=!(o->state & State_Enabled);
        switch(e) {
        case PE_FrameMenu:
            Classic::drawEdge(*p,o->rect,Classic::Raised);return;
        case PE_FrameFocusRect:
            Classic::drawFocusRect(*p,o->rect); return;
        case PE_IndicatorCheckBox:
            Classic::drawGlyph(*p,o->rect,Classic::Check,disabled,(o->state&State_NoChange)?Classic::Mixed:(o->state&State_On)?Classic::Checked:Classic::Unchecked);return;
        case PE_IndicatorRadioButton:
            Classic::drawGlyph(*p,o->rect,Classic::Radio,disabled,(o->state&State_On)?Classic::Checked:Classic::Unchecked);return;
        case PE_FrameGroupBox:
            Classic::drawEdge(*p,o->rect,Classic::Etched);return;
        case PE_PanelButtonCommand:
            Classic::drawButton(*p,o->rect,o->state & (State_Sunken|State_On));return;
        case PE_PanelLineEdit:
            if(w && w->property("classicFlatBorder").toBool()) {
                p->fillRect(o->rect,disabled?Classic::Face:Classic::Window);
                Classic::drawFlatBorder(*p,o->rect);return;
            }
            break;
        case PE_FrameLineEdit:
            if(w && w->property("classicFlatBorder").toBool()) return;
            break;
        default: break;
        }
        QProxyStyle::drawPrimitive(e,o,p,w);
    }
    void drawControl(ControlElement e,const QStyleOption *o,QPainter *p,const QWidget *w=nullptr) const override {
        if(e==CE_MenuItem) {
            if(auto item=qstyleoption_cast<const QStyleOptionMenuItem *>(o)) {
                drawMenuItem(*item,*p,w);return;
            }
        }
        if(e==CE_ScrollBarAddLine || e==CE_ScrollBarSubLine || e==CE_ScrollBarSlider) {
            p->fillRect(o->rect,Classic::Face);
            Classic::drawEdge(*p,o->rect,(o->state&State_Sunken)?Classic::Sunken:Classic::Raised);
            if(e!=CE_ScrollBarSlider) {
                const bool horizontal=o->state & State_Horizontal;
                if(horizontal) {
                    const bool left=(e==CE_ScrollBarSubLine)==(o->direction==Qt::LeftToRight);
                    const auto glyph=left?Classic::ArrowLeft:Classic::ArrowRight;
                    Classic::drawGlyph(*p,QRect(o->rect.center()-QPoint(left?2:1,3),QSize(4,7)),glyph,!(o->state&State_Enabled));
                } else {
                    p->save();p->translate(o->rect.center());p->rotate(e==CE_ScrollBarSubLine?180:0);
                    Classic::drawArrow(*p,QPoint(-3,-1),7);p->restore();
                }
            }
            return;
        }
        if(e==CE_ScrollBarAddPage || e==CE_ScrollBarSubPage) {
            p->fillRect(o->rect,Classic::Face);
            for(int y=o->rect.top();y<=o->rect.bottom();++y)
                for(int x=o->rect.left();x<=o->rect.right();++x)
                    if((x+y)&1) p->fillRect(x,y,1,1,Classic::Highlight3D);
            return;
        }
        if(e==CE_HeaderSection) {
            p->fillRect(o->rect,Classic::Face);
            Classic::drawEdge(*p,o->rect,(o->state&State_Sunken)?Classic::Sunken:Classic::Raised,Classic::Rect|Classic::Soft);return;
        }
        if(e==CE_PushButtonBevel) {
            auto b=qstyleoption_cast<const QStyleOptionButton *>(o);
            if(b) { Classic::drawButton(*p,b->rect,b->state & (State_Sunken|State_On),b->features & QStyleOptionButton::DefaultButton);return; }
        }
        QProxyStyle::drawControl(e,o,p,w);
    }
    void drawComplexControl(ComplexControl c,const QStyleOptionComplex *o,QPainter *p,const QWidget *w=nullptr) const override {
        // QScrollBar is opaque; the native 17th face row must not expose uninitialized backing pixels.
        if(c==CC_ScrollBar) p->fillRect(o->rect,Classic::Face);
        if(c==CC_ComboBox) {
            auto box=qstyleoption_cast<const QStyleOptionComboBox *>(o);
            if(box && !box->editable) {
                p->fillRect(box->rect,(box->state&State_Enabled)?Classic::Window:Classic::Face);
                Classic::drawEdge(*p,box->rect,Classic::Sunken);
                const QRect arrow=subControlRect(c,o,SC_ComboBoxArrow,w);
                p->fillRect(arrow,Classic::Face);
                Classic::drawEdge(*p,arrow,box->state&State_Sunken?Classic::Sunken:Classic::Raised);
                Classic::drawArrow(*p,QPoint(arrow.center().x()-3,arrow.center().y()-2),7,
                                   (box->state&State_Enabled)?Classic::Text:Classic::GrayText);
                if(box->state&State_HasFocus) Classic::drawFocusRect(*p,subControlRect(c,o,SC_ComboBoxEditField,w));
                return;
            }
        }
        QProxyStyle::drawComplexControl(c,o,p,w);
    }
private:
    void addMenuShadow(QObject *object) {
        auto *menu=qobject_cast<QMenu *>(object);
        if(!menu || menu->windowType()!=Qt::Popup || menu->windowFlags().testFlag(Qt::NoDropShadowWindowHint)
           || !QGuiApplication::platformName().startsWith(QLatin1String("wayland"))) return;
        auto *window=menu->windowHandle();
        if(!window || m_menuShadows.contains(window)) return;
        if(!m_shadowTiles[0]) {
            // Black alpha inferred from the 96-DPI white surround of the genuine Desktop View and Organize captures.
            // KWin stretches the straight edges and scales the logical-pixel tiles on Wayland.
            const int edge[]={142,171,212,241,252};
            const int cap[10][5]={
                {255,255,255,255,255},{255,255,255,255,255},{255,255,255,255,255},
                {255,255,255,255,255},{255,255,255,255,255},
                {242,246,250,253,254},{217,227,241,250,254},{180,199,227,245,253},
                {155,180,217,242,253},{144,172,213,241,252}
            };
            const int corner[5][5]={
                {155,180,217,242,253},{180,199,227,245,253},{217,227,241,250,254},
                {242,246,250,253,254},{253,253,254,254,255}
            };
            auto tile=[](int width,int height,auto gray) {
                QImage image(width,height,QImage::Format_ARGB32_Premultiplied);
                for(int y=0;y<height;++y)
                    for(int x=0;x<width;++x) image.setPixel(x,y,qRgba(0,0,0,255-gray(x,y)));
                auto result=KWindowShadowTile::Ptr::create();
                result->setImage(image);
                return result;
            };
            m_shadowTiles={tile(5,10,[&](int x,int y){return cap[y][x];}),
                           tile(5,1,[&](int x,int){return edge[x];}),
                           tile(5,5,[&](int x,int y){return corner[y][x];}),
                           tile(1,5,[&](int,int y){return edge[y];}),
                           tile(10,5,[&](int x,int y){return cap[x][y];})};
        }
        auto *shadow=new KWindowShadow(this);
        shadow->setWindow(window);
        shadow->setTopRightTile(m_shadowTiles[0]);
        shadow->setRightTile(m_shadowTiles[1]);
        shadow->setBottomRightTile(m_shadowTiles[2]);
        shadow->setBottomTile(m_shadowTiles[3]);
        shadow->setBottomLeftTile(m_shadowTiles[4]);
        shadow->setPadding(QMargins(0,0,5,5));
        if(!shadow->create()) {
            qWarning("Win7Classic: KWindowShadow could not attach a compositor shadow to a QMenu");
            delete shadow;
            return;
        }
        m_menuShadows.insert(window,shadow);
        connect(window,&QObject::destroyed,shadow,[this,window,shadow] {
            m_menuShadows.remove(window);
            delete shadow;
        });
    }
    void drawMenuItem(const QStyleOptionMenuItem &item,QPainter &p,const QWidget *w) const {
        const QRect r=item.rect;
        const bool disabled=!(item.state&State_Enabled), selected=item.state&State_Selected;
        const QColor ink=disabled?Classic::GrayText:selected?Classic::SelectionText:Classic::Text;
        p.save();
        p.fillRect(r,selected?Classic::Selection:Classic::Face);
        auto visual=[&](QRect box) { return visualRect(item.direction,r,box); };
        if(item.menuItemType==QStyleOptionMenuItem::Separator) {
            // Native separators keep two face pixels on each side of the etched line.
            QRect line(r.x()+1,r.y()-1+r.height()/2,r.width()-2,2);
            p.fillRect(line.x(),line.y(),line.width(),1,Classic::Shadow3D);
            p.fillRect(line.x(),line.y()+1,line.width(),1,Classic::Highlight3D);
            p.restore();return;
        }
        const int column=item.maxIconWidth?16:13;
        const QRect iconRect=visual(QRect(r.x()+1,r.y()+(r.height()-16)/2,column,16));
        if(!item.icon.isNull()) {
            if(item.checked) {
                const QRect check=visual(QRect(r.x(),r.y(),column+2,r.height()));
                if(!selected) {
                    for(int y=check.top();y<=check.bottom();++y)
                        for(int x=check.left();x<=check.right();++x)
                            if((x+y)&1) p.fillRect(x,y,1,1,Classic::Highlight3D);
                }
                Classic::drawEdge(p,check,Classic::SunkenOuter);
            }
            item.icon.paint(&p,iconRect,Qt::AlignCenter,disabled?QIcon::Disabled:selected?QIcon::Active:QIcon::Normal,
                            item.checked?QIcon::On:QIcon::Off);
        } else if(item.checked) {
            const bool radio=item.checkType==QStyleOptionMenuItem::Exclusive;
            const QSize size=radio?QSize(6,6):QSize(7,7);
            QRect mark(QPoint(),size);mark.moveCenter(iconRect.center());
            mark.moveTop(r.y()+(r.height()-size.height())/2+(radio?0:1));
            if(disabled && !selected) Classic::drawGlyph(p,mark.translated(1,1),radio?Classic::MenuBullet:Classic::MenuCheck,false,Classic::Unchecked,Classic::Highlight3D);
            Classic::drawGlyph(p,mark,radio?Classic::MenuBullet:Classic::MenuCheck,false,Classic::Unchecked,ink);
        }
        QFont font=item.font;
        if(item.menuItemType==QStyleOptionMenuItem::DefaultItem) font.setBold(true);
        p.setFont(font);
        int flags=Qt::AlignVCenter|Qt::AlignLeft|Qt::TextSingleLine|Qt::TextShowMnemonic;
        if(!styleHint(SH_UnderlineShortcut,&item,w)) flags|=Qt::TextHideMnemonic;
        const QStringList parts=item.text.split('\t');
        const int textLeft=column+3;
        const QRect label=visual(QRect(r.x()+textLeft,r.y(),r.width()-textLeft-item.reservedShortcutWidth-12,r.height()));
        auto text=[&](QRect box,const QString &value) {
            if(disabled && !selected) {
                p.setPen(Classic::Highlight3D);p.drawText(box.translated(1,1),flags,value);
            }
            p.setPen(ink);p.drawText(box,flags,value);
        };
        text(label,parts.first());
        if(parts.size()>1)
            text(visual(QRect(r.right()-item.reservedShortcutWidth-11,r.y(),item.reservedShortcutWidth,r.height())),parts.at(1));
        if(item.menuItemType==QStyleOptionMenuItem::SubMenu) {
            const QRect arrow=visual(QRect(r.right()-9,r.y()+(r.height()-7)/2-1,4,7));
            const auto glyph=item.direction==Qt::RightToLeft?Classic::ArrowLeft:Classic::ArrowRight;
            if(disabled && !selected) Classic::drawGlyph(p,arrow.translated(1,1),glyph,false,Classic::Unchecked,Classic::Highlight3D);
            Classic::drawGlyph(p,arrow,glyph,false,Classic::Unchecked,ink);
        }
        p.restore();
    }
    void enforcePalette() {
        if(!m_app || m_app->palette()==Classic::palette()) return;
        m_externalPalette=m_app->palette();
        m_applyingPalette=true;
        m_app->setPalette(Classic::palette());
        m_applyingPalette=false;
    }
    QList<KWindowShadowTile::Ptr> m_shadowTiles;
    QHash<QWindow *,KWindowShadow *> m_menuShadows;
    QApplication *m_app=nullptr;
    QPalette m_externalPalette;
    bool m_applyingPalette=false;
};
class ClassicStylePlugin : public QStylePlugin {
    Q_OBJECT
    Q_PLUGIN_METADATA(IID "org.qt-project.Qt.QStyleFactoryInterface" FILE "style.json")
public:
    QStyle *create(const QString &key) override { return key.compare("Win7Classic",Qt::CaseInsensitive)==0?new ClassicStyle:nullptr; }
};
#include "ClassicStyle.moc"
