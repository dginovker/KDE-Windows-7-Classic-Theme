#include "ClassicPrimitives.h"

namespace Classic {
QPalette palette()
{
    QPalette p;
    for (auto group : {QPalette::Active, QPalette::Inactive, QPalette::Disabled}) {
        const bool disabled = group == QPalette::Disabled;
        for (auto role : {QPalette::Window, QPalette::Button, QPalette::Midlight}) p.setColor(group, role, Face);
        for (auto role : {QPalette::WindowText, QPalette::Text, QPalette::ButtonText}) p.setColor(group, role, disabled ? GrayText : Text);
        p.setColor(group, QPalette::Light, Highlight3D);
        p.setColor(group, QPalette::Dark, Shadow3D);
        p.setColor(group, QPalette::Shadow, DarkShadow3D);
        p.setColor(group, QPalette::Mid, Shadow3D);
        p.setColor(group, QPalette::Base, disabled ? Face : Window);
        p.setColor(group, QPalette::AlternateBase, Face);
        p.setColor(group, QPalette::BrightText, Highlight3D);
        p.setColor(group, QPalette::Highlight, group == QPalette::Inactive ? Face : Selection);
        p.setColor(group, QPalette::HighlightedText, group == QPalette::Inactive ? Text : SelectionText);
        p.setColor(group, QPalette::ToolTipBase, QColor(255,255,225));
        p.setColor(group, QPalette::ToolTipText, Text);
        p.setColor(group, QPalette::Link, QColor(0,0,255));
        p.setColor(group, QPalette::LinkVisited, QColor(128,0,128));
        p.setColor(group, QPalette::PlaceholderText, GrayText);
        p.setColor(group, QPalette::Accent, Selection);
    }
    return p;
}
QRect drawEdge(QPainter &p, QRect r, int edge, int flags)
{
    if ((edge & ~15) || (edge & 3)==3 || (edge & 12)==12 || edge==0 ||
        (flags & ~(Rect|Soft|Adjust|Flat|Middle)))
        qFatal("Classic::drawEdge unsupported edge=0x%x flags=0x%x",edge,flags);
    const bool outer=edge & 3, inner=edge & 12, soft=flags & Soft;
    auto ring = [&](QColor tl,QColor br) {
        const int x=r.x(),y=r.y(),w=r.width(),h=r.height();
        if(flags&Top) p.fillRect(x,y,w,1,tl);
        if(flags&Left) p.fillRect(x,y,1,h,tl);
        if(flags&Bottom) p.fillRect(x,y+h-1,w,1,br);
        if(flags&Right) p.fillRect(x+w-1,y,1,h,br);
        r.adjust(flags&Left ? 1:0,flags&Top ? 1:0,flags&Right ? -1:0,flags&Bottom ? -1:0);
    };
    if(outer) {
        const bool raised=edge & RaisedOuter;
        QColor tl=raised ? (soft?Highlight3D:Light3D) : (soft?DarkShadow3D:Shadow3D);
        QColor br=raised ? DarkShadow3D : Highlight3D;
        if(flags&Flat) tl=br=Shadow3D;
        ring(tl,br);
    }
    if(inner) {
        const bool raised=edge & RaisedInner;
        QColor tl=raised ? (soft?Light3D:Highlight3D) : (soft?Shadow3D:DarkShadow3D);
        QColor br=raised ? Shadow3D : Light3D;
        if(flags&Flat) tl=br=Face;
        ring(tl,br);
    }
    if(flags&Middle) p.fillRect(r,Face);
    return r;
}
void drawFlatBorder(QPainter &p,QRect r)
{
    p.fillRect(r.x(),r.y(),r.width(),1,Text);p.fillRect(r.x(),r.bottom(),r.width(),1,Text);
    p.fillRect(r.x(),r.y(),1,r.height(),Text);p.fillRect(r.right(),r.y(),1,r.height(),Text);
}
void drawButton(QPainter &p,QRect r,bool pressed,bool isDefault)
{
    if(isDefault) { p.fillRect(r,Text); r.adjust(1,1,-1,-1); }
    p.fillRect(r,Face);
    drawEdge(p,r,pressed?Sunken:Raised,Rect|Soft);
}
void drawFocusRect(QPainter &p,QRect r,QPoint origin)
{
    for(int y=r.top();y<=r.bottom();++y)
        for(int x=r.left();x<=r.right();++x)
            if((x==r.left()||x==r.right()||y==r.top()||y==r.bottom()) && ((x+origin.x()+y+origin.y())&1))
                p.fillRect(x,y,1,1,Text);
}
void drawArrow(QPainter &p,QPoint at,int width,const QColor &color)
{
    for(int y=0;width-2*y>0;++y) p.fillRect(at.x()+y,at.y()+y,width-2*y,1,color);
}
void drawSeparator(QPainter &p,QRect r)
{
    p.fillRect(r.x(),r.y(),r.width(),1,Shadow3D);
    p.fillRect(r.x(),r.y()+1,1,1,Shadow3D);
    p.fillRect(r.x()+1,r.y()+1,r.width()-1,1,Highlight3D);
}
void drawGlyph(QPainter &p,QRect r,Glyph glyph,bool disabled,CheckState checkState,const QColor &ink)
{
    const QColor color=disabled?GrayText:ink;
    auto bars=[&](std::initializer_list<QRect> boxes) { for(auto b:boxes) p.fillRect(b.translated(r.topLeft()),color); };
    switch(glyph) {
    case None: return;
    case Minimize: bars({{4,9,6,2}}); return;
    case Maximize: bars({{3,2,9,2},{3,4,1,6},{11,4,1,6},{3,10,9,1}}); return;
    case Restore: bars({{5,2,6,2},{5,4,1,1},{10,4,1,4},{3,5,6,2},{3,7,1,4},{8,7,3,1},{8,8,1,2},{3,10,6,1}}); return;
    case Close: bars({{4,3,2,1},{10,3,2,1},{5,4,2,1},{9,4,2,1},{6,5,4,1},{7,6,2,1},{6,7,4,1},{5,8,2,1},{9,8,2,1},{4,9,2,1},{10,9,2,1}}); return;
    case ArrowDown: drawArrow(p,r.topLeft(),r.width(),color); return;
    case ArrowLeft: case ArrowRight:
        for(int y=0;y<7;++y) { const int w=4-abs(3-y); p.fillRect(r.x()+(glyph==ArrowLeft?4-w:0),r.y()+y,w,1,color); } return;
    case Check: {
        p.fillRect(r,disabled?Face:Window);
        if(checkState==Mixed && !disabled) {
            for(int y=r.top()+2;y<r.bottom()-1;++y)
                for(int x=r.left()+2;x<r.right()-1;++x)
                    if((x+y)&1) p.fillRect(x,y,1,1,Face);
        }
        drawEdge(p,r,Sunken);
        if(checkState!=Unchecked) {
            static const char *tick[]={"......#",".....##","#...###","##.###.","#####..",".###...","..#...."};
            for(int y=0;y<7;++y)for(int x=0;x<7;++x)if(tick[y][x]=='#')p.fillRect(r.x()+3+x,r.y()+3+y,1,1,checkState==Mixed?GrayText:color);
        }
        return;
    }
    case Radio: {
        // Native 13px Marlett raster measured in controls-native-client.png, not an antialiased ellipse.
        static const char *rows[]={".....SSSS....","...SSDDDDSS..","..SDDwwwwDDH.","..SDwwwwww.H.",".SDwwwwwwww.H",".SDwwwwwwww.H",".SDwwwwwwww.H",".SDwwwwwwww.H","..SDwwwwww.H.","..S..wwww..H.","...HH....HH..",".....HHHH....","............."};
        for(int y=0;y<13;++y)for(int x=0;x<13;++x){
            char c=rows[y][x]; QColor v=c=='S'?Shadow3D:c=='D'?DarkShadow3D:c=='H'?Highlight3D:c=='w'?(disabled?Face:Window):Face;
            p.fillRect(r.x()+x,r.y()+y,1,1,v);
        }
        if(checkState==Checked) { p.fillRect(r.x()+6,r.y()+4,2,4,color);p.fillRect(r.x()+5,r.y()+5,4,2,color); }
        return;
    }
    }
    qFatal("Classic::drawGlyph unsupported glyph=%d",glyph);
}
}
