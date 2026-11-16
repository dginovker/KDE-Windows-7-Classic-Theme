import QtQuick
import "../../../../../win7-classic/primitives" as Classic

Classic.Raster {
    property bool sunken: false
    fill: Classic.Palette.face
    edge: sunken ? Classic.Raster.Sunken : Classic.Raster.Raised
    flags: Classic.Raster.Rect | Classic.Raster.Soft
}
