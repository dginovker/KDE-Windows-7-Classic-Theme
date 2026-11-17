#pragma once
#include <QColor>
#include <QPainter>
#include <QPalette>

namespace Classic {
// Semantic roles stay distinct: COLOR_3DLIGHT happens to equal COLOR_BTNFACE in this scheme.
inline const QColor Face(212,208,200), Light3D(212,208,200), Highlight3D(255,255,255),
    Shadow3D(128,128,128), DarkShadow3D(64,64,64), Window(255,255,255), Text(0,0,0),
    GrayText(128,128,128), ActiveCaption(10,36,106), InactiveCaption(128,128,128),
    ActiveCaptionGradient(166,202,240), InactiveCaptionGradient(192,192,192), Selection(10,36,106), SelectionText(255,255,255);
enum Edge { RaisedOuter=1, SunkenOuter=2, RaisedInner=4, SunkenInner=8,
            Raised=5, Sunken=10, Etched=6, Bump=9 };
enum Flag { Left=1, Top=2, Right=4, Bottom=8, Rect=15, Soft=0x1000,
            Adjust=0x2000, Flat=0x4000, Middle=0x800 };
enum CheckState { Unchecked, Checked, Mixed };
enum Glyph { None, Minimize, Maximize, Restore, Close, Check, Radio, MenuCheck, MenuBullet, ArrowDown, ArrowRight, ArrowLeft };
QPalette palette();
// QRect uses inclusive right()/bottom(); all fills below use width/height (Win32 half-open bounds).
QRect drawEdge(QPainter &, QRect, int edge, int flags=Rect);
void drawCaption(QPainter &, QRect, bool active);
void drawFlatBorder(QPainter &, QRect);
void drawButton(QPainter &, QRect, bool pressed=false, bool isDefault=false);
void drawFocusRect(QPainter &, QRect, QPoint origin={});
void drawGlyph(QPainter &, QRect, Glyph, bool disabled=false, CheckState checkState=Unchecked, const QColor &ink=Text);
void drawArrow(QPainter &, QPoint, int width, const QColor &color=Text);
void drawSeparator(QPainter &, QRect);
}
