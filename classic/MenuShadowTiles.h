#pragma once

#include <KWindowShadow>
#include <array>
#include <memory>

namespace Classic {
using MenuShadowTiles = std::array<KWindowShadowTile::Ptr, 5>;

inline std::unique_ptr<KWindowShadow> menuShadow(QWindow *window, MenuShadowTiles &tiles)
{
    if(!tiles[0]) {
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
        // KWin filters across atlas tile boundaries. Continue each straight edge into
        // the adjoining cap/corner texel so its stretched tile samples a constant profile.
        tiles={tile(5,11,[&](int x,int y){return y==10?edge[x]:cap[y][x];}),
                       tile(5,1,[&](int x,int){return edge[x];}),
                       tile(6,6,[&](int x,int y){
                           if(x==0) return y==0?255:edge[y-1];
                           return y==0?edge[x-1]:corner[y-1][x-1];
                       }),
                       tile(1,5,[&](int,int y){return edge[y];}),
                       tile(11,5,[&](int x,int y){return x==10?edge[y]:cap[x][y];})};
    }
    auto shadow=std::make_unique<KWindowShadow>();
    shadow->setWindow(window);
    shadow->setTopRightTile(tiles[0]);
    shadow->setRightTile(tiles[1]);
    shadow->setBottomRightTile(tiles[2]);
    shadow->setBottomTile(tiles[3]);
    shadow->setBottomLeftTile(tiles[4]);
    shadow->setPadding(QMargins(0,0,5,5));
    return shadow;
}
}
