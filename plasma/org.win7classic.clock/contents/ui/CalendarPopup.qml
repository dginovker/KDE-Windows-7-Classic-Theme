pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtQuick.Templates as T
import "../../../../../win7-classic/primitives2" as Classic
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.workspace.calendar as PlasmaCalendar
import org.kde.kcmutils as KCMUtils

PlasmaCore.Dialog {
    id: popup
    required property date now
    property var locale: Qt.locale()
    readonly property font uiFont: Qt.font({ family: "Tahoma", pixelSize: 11 })
    readonly property color linkColor: "#000080"
    readonly property string localDate: Qt.formatDateTime(new Date(+now), "yyyy-MM-dd")
    readonly property var localTime: Qt.formatTime(now, "HH:mm:ss").split(":").map(Number)
    // Keep civil keys numeric. Qt can reinterpret a stored QML Date when the system zone changes.
    readonly property real today: Date.parse(localDate + "T00:00:00Z")
    property real selected: today
    readonly property int selectedYear: new Date(selected).getUTCFullYear()
    readonly property int selectedMonth: new Date(selected).getUTCMonth() + 1
    readonly property int selectedDay: new Date(selected).getUTCDate()
    property bool followingToday: false
    onTodayChanged: if (followingToday) showToday()
    readonly property bool usWeekdays: locale.name === "en_US"
    readonly property int firstDayOfWeek: usWeekdays ? Qt.Sunday : locale.firstDayOfWeek
    readonly property var weekdays: weekdayNames()
    // The native heading zooms out from days to months, years and decades.
    property int overview: 0
    readonly property int yearStep: overview === 3 ? 10 : 1
    readonly property int yearSpan: overview === 3 ? 100 : overview === 2 ? 10 : 1
    readonly property int firstYear: Math.floor(selectedYear / yearSpan) * yearSpan
    readonly property int minYear: Math.min(1900, Math.floor(new Date(today).getUTCFullYear() / 100) * 100)
    readonly property int maxYear: Math.max(2099, Math.floor(new Date(today).getUTCFullYear() / 100) * 100 + 99)

    type: PlasmaCore.Dialog.AppletPopup
    flags: Qt.WindowStaysOnTopHint
    backgroundHints: PlasmaCore.Dialog.NoBackground
    hideOnWindowDeactivate: true
    // The applet supplies an explicit screen-right position, not a centered visualParent.
    location: PlasmaCore.Types.Floating

    function civil(year: int, month: int, day: int): real {
        return Date.UTC(year, month - 1, day);
    }

    function longDate(day: real): string {
        // The ISO string overload formats a QDate without reinterpreting it in the local zone.
        return Qt.formatDate(new Date(day).toISOString().split("T")[0], locale, Locale.LongFormat);
    }

    function weekdayNames(): var {
        if (usWeekdays)
            return ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
        const order = Array.from({length: 7}, (_, i) => (firstDayOfWeek - 1 + i) % 7 + 1);
        const narrow = order.map(day => locale.standaloneDayName(day, Locale.NarrowFormat));
        // Some locales reuse narrow labels for different days.
        return new Set(narrow).size === 7 ? narrow : order.map(day => locale.standaloneDayName(day, Locale.ShortFormat));
    }

    function arrowName(previous: bool): string {
        switch (overview) {
        case 0: return previous ? qsTr("Previous month") : qsTr("Next month");
        case 1: return previous ? qsTr("Previous year") : qsTr("Next year");
        case 2: return previous ? qsTr("Previous decade") : qsTr("Next decade");
        default: return previous ? qsTr("Previous century") : qsTr("Next century");
        }
    }

    function showToday() {
        const date = new Date(today);
        calendar.goToYearAndMonth(date.getUTCFullYear(), date.getUTCMonth() + 1);
        selected = today;
    }

    function open() {
        showToday();
        overview = 0;
        followingToday = true;
        visible = true;
        requestActivate();
        grid.forceActiveFocus();
    }

    function selectDay(day: real) {
        const date = new Date(day);
        if (date.getUTCFullYear() < minYear || date.getUTCFullYear() > maxYear)
            return;
        followingToday = false;
        calendar.goToYearAndMonth(date.getUTCFullYear(), date.getUTCMonth() + 1);
        selected = day;
    }

    function moveDay(offset: int) {
        selectDay(civil(selectedYear, selectedMonth, selectedDay + offset));
    }

    function canPage(offset: int): bool {
        if (overview)
            return firstYear + offset * yearSpan >= minYear && firstYear + offset * yearSpan <= maxYear;
        const date = new Date(civil(calendar.year, calendar.month + offset, 1));
        return date.getUTCFullYear() >= minYear && date.getUTCFullYear() <= maxYear;
    }

    function clampedDay(year: int, month: int, day: int): real {
        const last = new Date(civil(year, month + 1, 0)).getUTCDate();
        return civil(year, month, Math.min(day, last));
    }

    function page(offset: int, preserveDay: bool) {
        if (!canPage(offset))
            return;
        followingToday = false;
        if (overview) {
            // The first decade lights up on a new century page, but keeps the drill-down digit.
            selected = civil(firstYear + offset * yearSpan + (overview === 3 ? selectedYear % 10 : 0), 1, 1);
            return;
        }
        const day = preserveDay ? selectedDay : 1;
        if (offset < 0)
            calendar.previousMonth();
        else
            calendar.nextMonth();
        selected = clampedDay(calendar.year, calendar.month, day);
    }

    function zoomOut() {
        if (overview < 3) {
            followingToday = false;
            ++overview;
            overviewGrid.forceActiveFocus();
        }
    }

    function choosePeriod() {
        if (!overview)
            return;
        --overview;
        if (overview) {
            overviewGrid.forceActiveFocus();
        } else {
            selectDay(selected);
            grid.forceActiveFocus();
        }
    }

    function chooseCell(year: int, month: int) {
        // Changing the decade keeps the selected year digit; lower fields also survive drill-down.
        const targetYear = overview === 3 ? year + selectedYear % 10 : year;
        selected = clampedDay(targetYear, month, selectedDay);
        choosePeriod();
    }

    function movePeriod(offset: int) {
        const month = selectedMonth;
        const day = selectedDay;
        if (overview === 1) {
            if (month + offset >= 1 && month + offset <= 12)
                selected = clampedDay(firstYear, month + offset, day);
        } else {
            const year = selectedYear + offset * yearStep;
            if (year >= minYear && year <= maxYear)
                selected = clampedDay(year, month, day);
        }
    }

    readonly property PlasmaCalendar.Calendar calendar: PlasmaCalendar.Calendar {
        days: 7
        weeks: 6
        firstDayOfWeek: popup.firstDayOfWeek
    }

    // Pixel geometry from reference/screenshots/w7-calendar.png (origin 949,513).
    mainItem: Classic.Raster {
        id: body
        width: 331; height: 243
        fill: Classic.Palette.window
        flatBorder: true
        Keys.onEscapePressed: popup.close()

        component CalendarText: Text {
            font: popup.uiFont
            color: Classic.Palette.text
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            renderType: Text.NativeRendering
        }

        CalendarText {
            x: 1; y: 14; width: 329; height: 16
            text: popup.longDate(popup.today)
            color: popup.linkColor
        }

        Rectangle {
            x: 15; y: 41; width: 161; height: 27
            color: Classic.Palette.selection
            T.AbstractButton {
                id: heading
                x: 27; width: 107; height: parent.height
                enabled: popup.overview < 3
                focusPolicy: Qt.StrongFocus
                Accessible.name: label.text
                onClicked: popup.zoomOut()
                Keys.onReturnPressed: heading.clicked()
                Keys.onEnterPressed: heading.clicked()
                contentItem: CalendarText {
                    id: label
                    objectName: "monthHeading"
                    text: popup.overview === 0 ? qsTr("%1, %2").arg(popup.calendar.monthName).arg(popup.calendar.year)
                        : popup.overview === 1 ? popup.firstYear
                        : qsTr("%1-%2").arg(popup.firstYear).arg(popup.firstYear + popup.yearSpan - 1)
                    color: Classic.Palette.selectionText
                    font.bold: true
                    font.underline: heading.visualFocus
                    elide: Text.ElideRight
                }
            }
            Repeater {
                model: 2
                delegate: T.AbstractButton {
                    id: arrow
                    required property int index
                    readonly property bool previous: index === 0
                    x: previous ? 5 : 135; y: 5; width: 21; height: 16
                    focusPolicy: Qt.StrongFocus
                    objectName: previous ? "calendarPrevious" : "calendarNext"
                    Accessible.name: popup.arrowName(previous)
                    enabled: popup.canPage(previous ? -1 : 1)
                    onClicked: popup.page(previous ? -1 : 1, false)
                    Keys.onReturnPressed: arrow.clicked()
                    Keys.onEnterPressed: arrow.clicked()
                    background: Classic.Raster {
                        fill: Classic.Palette.face
                        edge: arrow.down ? Classic.Raster.Sunken : Classic.Raster.Raised
                        Classic.Raster {
                            x: 7; y: 4; width: 7; height: 8
                            glyph: arrow.previous ? Classic.Raster.ArrowLeft : Classic.Raster.ArrowRight
                            disabled: !arrow.enabled
                            pressed: arrow.down
                            focused: arrow.visualFocus
                        }
                    }
                }
            }
        }

        Repeater {
            objectName: "weekdayHeadings"
            model: 7
            CalendarText {
                required property int index
                visible: popup.overview === 0
                x: 15 + index * 23; y: 69; width: 23; height: 16
                text: popup.weekdays[index]
                fontSizeMode: Text.HorizontalFit
                minimumPixelSize: 8
                color: Classic.Palette.selection
            }
        }
        Rectangle { visible: popup.overview === 0; x: 19; y: 86; width: 153; height: 1; color: Classic.Palette.text }
        Item {
            id: grid
            objectName: "calendarDays"
            visible: popup.overview === 0
            x: 15; y: 87; width: 161; height: 90
            activeFocusOnTab: true
            Accessible.role: Accessible.Table
            Accessible.name: qsTr("Calendar, %1").arg(popup.longDate(popup.selected))
            Keys.onLeftPressed: popup.moveDay(-1)
            Keys.onRightPressed: popup.moveDay(1)
            Keys.onUpPressed: popup.moveDay(-7)
            Keys.onDownPressed: popup.moveDay(7)
            Keys.onPressed: event => {
                if (event.key === Qt.Key_PageUp || event.key === Qt.Key_PageDown) {
                    popup.page(event.key === Qt.Key_PageUp ? -1 : 1, true);
                    event.accepted = true;
                }
            }
            Repeater {
                model: popup.calendar.daysModel
                delegate: Rectangle {
                    id: cell
                    required property int index
                    required property int dayNumber
                    required property int monthNumber
                    required property int yearNumber
                    required property bool isCurrent
                    readonly property real day: popup.civil(yearNumber, monthNumber, dayNumber)
                    enabled: yearNumber >= popup.minYear && yearNumber <= popup.maxYear
                    Accessible.ignored: !enabled
                    readonly property bool isToday: day === popup.today
                    readonly property bool isSelected: day === popup.selected
                    x: index % 7 * 23; y: Math.floor(index / 7) * 15; width: 23; height: 15
                    color: isSelected ? Classic.Palette.selection : "transparent"
                    border.color: Classic.Palette.selection
                    border.width: isToday && !isSelected ? 1 : 0
                    Accessible.role: Accessible.Cell
                    Accessible.name: popup.longDate(day)
                    Accessible.selected: isSelected
                    Accessible.onPressAction: popup.selectDay(day)
                    CalendarText {
                        anchors.fill: parent
                        text: cell.dayNumber
                        color: cell.isSelected ? Classic.Palette.selectionText
                             : cell.isCurrent ? Classic.Palette.text : Classic.Palette.grayText
                    }
                    // Native dots lie on odd desktop pixels, not on a fixed cell-relative phase.
                    // Use scene-graph rectangles so fractional scaling cannot filter a focus texture.
                    Repeater {
                        id: cue
                        readonly property real scale: body.Screen.devicePixelRatio
                        readonly property int px: Math.round((popup.x + grid.x + cell.x) * scale)
                        readonly property int py: Math.round((popup.y + grid.y + cell.y) * scale)
                        readonly property int phase: (px + py) & 1
                        readonly property int rowDots: 10 + phase
                        readonly property int sideDots: 6 - phase
                        model: cell.isSelected && grid.activeFocus ? 32 : 0
                        Rectangle {
                            required property int index
                            readonly property int sideIndex: index - 2 * cue.rowDots
                            x: sideIndex < 0 ? 2 - cue.phase + index % cue.rowDots * 2
                                            : sideIndex < cue.sideDots ? 1 : 21
                            y: sideIndex < 0 ? (index < cue.rowDots ? 1 : 13)
                                            : 2 + cue.phase + sideIndex % cue.sideDots * 2
                            width: 1; height: 1
                            color: "#f5db95"
                        }
                    }
                    TapHandler {
                        onTapped: {
                            grid.forceActiveFocus(Qt.MouseFocusReason);
                            popup.selectDay(cell.day);
                        }
                    }
                }
            }
        }

        Item {
            id: overviewGrid
            objectName: "calendarOverview"
            x: 15; y: 68; width: 161; height: 108
            visible: popup.overview > 0
            activeFocusOnTab: true
            Accessible.role: Accessible.Table
            Accessible.name: label.text
            Keys.onLeftPressed: popup.movePeriod(-1)
            Keys.onRightPressed: popup.movePeriod(1)
            Keys.onUpPressed: popup.movePeriod(-4)
            Keys.onDownPressed: popup.movePeriod(4)
            Keys.onReturnPressed: popup.choosePeriod()
            Keys.onEnterPressed: popup.choosePeriod()
            Keys.onSpacePressed: popup.choosePeriod()
            Keys.onPressed: event => {
                if (event.key === Qt.Key_PageUp || event.key === Qt.Key_PageDown) {
                    popup.page(event.key === Qt.Key_PageUp ? -1 : 1, false);
                    event.accepted = true;
                }
            }
            Repeater {
                model: 12
                delegate: Rectangle {
                    id: period
                    required property int index
                    readonly property int year: popup.firstYear + (index - 1) * popup.yearStep
                    readonly property bool months: popup.overview === 1
                    readonly property bool selectable: months || (year >= popup.minYear && year <= popup.maxYear)
                    readonly property bool chosen: months ? index === popup.selectedMonth - 1
                        : year === Math.floor(popup.selectedYear / popup.yearStep) * popup.yearStep
                    readonly property bool inPage: months || (index > 0 && index < 11)
                    x: index % 4 * 40; y: Math.floor(index / 4) * 36; width: 40; height: 36
                    color: chosen ? Classic.Palette.selection : "transparent"
                    Accessible.role: Accessible.Cell
                    Accessible.name: periodText.text
                    Accessible.selected: chosen
                    enabled: selectable
                    Accessible.ignored: !selectable
                    function choose() {
                        if (selectable)
                            popup.chooseCell(months ? popup.firstYear : year, months ? index + 1 : popup.selectedMonth);
                    }
                    Accessible.onPressAction: choose()
                    CalendarText {
                        id: periodText
                        anchors.fill: parent
                        text: !period.selectable ? "" : period.months ? popup.locale.standaloneMonthName(period.index, Locale.ShortFormat)
                            : popup.overview === 3 ? qsTr("%1-\n%2").arg(period.year).arg(period.year + 9) : period.year
                        color: period.chosen ? Classic.Palette.selectionText : period.inPage ? Classic.Palette.text : Classic.Palette.grayText
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 1
                        visible: period.chosen && overviewGrid.activeFocus
                        color: "transparent"
                        border.color: "#f5db95"
                    }
                    TapHandler { onTapped: period.choose() }
                }
            }
        }

        Image {
            x: 185; y: 41; width: 131; height: 129
            source: "calendar-dial.png"
            component Hand: Rectangle {
                id: hand
                required property real angle
                property int tail: 0
                x: 64.5 - width / 2; y: 64.5 - height + tail
                transform: Rotation { origin.x: hand.width / 2; origin.y: hand.height - hand.tail; angle: hand.angle }
            }
            Hand {
                width: 2; height: 34; color: "#405e65"; antialiasing: true
                angle: (popup.localTime[0] % 12 + popup.localTime[1] / 60) * 30
            }
            Hand {
                width: 2; height: 46; color: "#637c83"; antialiasing: true
                angle: (popup.localTime[1] + popup.localTime[2] / 60) * 6
            }
            Hand {
                objectName: "secondHand"
                width: 1; height: 67; tail: 17; color: "#4a6069"; antialiasing: true
                angle: popup.localTime[2] * 6
            }
            Rectangle { x: 62; y: 62; width: 5; height: 5; radius: 2.5; color: "#284c58"; antialiasing: true }
        }
        CalendarText {
            objectName: "digitalSeconds"
            x: 185; y: 174; width: 131; height: 17
            text: Qt.formatTime(popup.now, popup.locale.timeFormat(Locale.LongFormat).replace(/\s+t+$/, ""))
        }

        Rectangle { x: 1; y: 201; width: 329; height: 41; color: Classic.Palette.face }
        T.AbstractButton {
            id: settingsLink
            objectName: "clockSettingsLink"
            anchors.horizontalCenter: parent.horizontalCenter
            y: 213; width: settingsText.implicitWidth + 6; height: 18
            text: qsTr("Change date and time settings…")
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            Accessible.role: Accessible.Link
            Accessible.name: text
            Keys.onReturnPressed: settingsLink.clicked()
            Keys.onEnterPressed: settingsLink.clicked()
            onClicked: {
                popup.close();
                KCMUtils.KCMLauncher.openSystemSettings("kcm_clock");
            }
            contentItem: CalendarText {
                id: settingsText
                text: settingsLink.text
                color: popup.linkColor
                font.underline: settingsLink.hovered || settingsLink.visualFocus
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
        }
    }
}
