import QtQuick
import QtTest
import "../share/plasma/plasmoids/org.win7classic.clock/contents/ui"

TestCase {
    id: test
    name: "CalendarPopup"
    when: windowShown
    CalendarPopup { id: popup; now: new Date(2026, 11, 31, 7, 47, 13); transientParent: test.Window.window }
    function test_applet_loads() {
        const component = Qt.createComponent("../share/plasma/plasmoids/org.win7classic.clock/contents/ui/main.qml")
        tryVerify(() => component.status !== Component.Loading)
        compare(component.status, Component.Ready, component.errorString())
    }
    function cleanup() {
        popup.close()
        testTimeZone.setZone("Pacific/Apia")
        popup.now = new Date(2026, 11, 31, 7, 47, 13)
        popup.locale = Qt.locale()
    }
    function test_apiaSkippedDay() {
        // Apia jumped directly from Dec 29 to Dec 31 in 2011; the grid must not.
        compare(Qt.formatDateTime(new Date(Date.UTC(2011, 11, 30, 10)), "yyyy-MM-dd"), "2011-12-31")
        popup.now = new Date(Date.UTC(2011, 11, 30, 10))
        popup.open()
        const grid = findChild(popup.mainItem, "calendarDays")
        const cells = grid.children.filter(c => c.dayNumber !== undefined)
        compare(cells.filter(c => c.isSelected).length, 1)
        popup.moveDay(-1)
        compare(new Date(popup.selected).toISOString().split("T")[0], "2011-12-30")
        compare(cells.filter(c => c.isSelected).map(c => c.dayNumber), [30])
        compare(popup.longDate(popup.selected), "Friday, December 30, 2011")
        popup.moveDay(-1)
        compare(popup.selectedDay, 29)
        popup.moveDay(1)
        compare(popup.selectedDay, 30)
        popup.moveDay(1)
        compare(popup.selectedDay, 31)
    }
    function test_midnight() {
        // UTC midnight is still the prior day in Apia before the dateline change.
        popup.now = new Date(Date.UTC(2011, 11, 29, 0))
        popup.open()
        compare(popup.localDate, "2011-12-28")
        popup.now = new Date(2026, 11, 31, 23, 59, 59)
        compare(popup.selectedDay, 31)
        popup.now = new Date(2027, 0, 1, 0, 0, 0)
        compare(findChild(popup.mainItem, "monthHeading").text, "January, 2027")
        checkMarkers(popup, "2027-1-1", "2027-1-1")
        compare(findChild(popup.mainItem, "secondHand").angle, 0)
        popup.moveDay(-1)
        popup.now = new Date(2027, 0, 2, 0, 0, 0)
        checkMarkers(popup, "2026-12-31", "2027-1-2")
    }
    Component {
        id: zonePopup
        CalendarPopup { transientParent: test.Window.window }
    }
    function checkMarkers(calendarPopup, selected, today) {
        const grid = findChild(calendarPopup.mainItem, "calendarDays")
        const cells = grid.children.filter(c => c.dayNumber !== undefined)
        compare(cells.length, 42)
        const key = c => `${c.yearNumber}-${c.monthNumber}-${c.dayNumber}`
        compare(cells.filter(c => c.isSelected && c.color.toString() === "#0a246a").map(key), [selected])
        compare(cells.filter(c => c.isToday && (c.isSelected || c.border.width === 1)).map(key), [today])
    }
    function test_liveTimeZoneGrid() {
        const instant = second => new Date(Date.UTC(2026, 10, 18, 7, 0, second))
        testTimeZone.setZone("America/Los_Angeles")
        const p = createTemporaryObject(zonePopup, test, {now: instant(1)})
        verify(p !== null)
        p.open()
        checkMarkers(p, "2026-11-17", "2026-11-17")
        testTimeZone.setZone("Pacific/Kiritimati")
        p.now = instant(2)
        verify(p.visible)
        checkMarkers(p, "2026-11-18", "2026-11-18")
        p.moveDay(3)
        checkMarkers(p, "2026-11-21", "2026-11-18")
        testTimeZone.setZone("America/Los_Angeles")
        p.now = instant(3)
        verify(p.visible)
        checkMarkers(p, "2026-11-21", "2026-11-17")
        p.close()
    }
    function test_centuryPagingKeepsYearDigit() {
        popup.now = new Date(2026, 10, 17, 12)
        popup.open()
        for (let i = 0; i < 3; ++i)
            popup.zoomOut()
        popup.page(-1, false)
        popup.page(1, false)
        const overview = findChild(popup.mainItem, "calendarOverview")
        const highlighted = () => overview.children.filter(c => c.chosen).map(c => c.year)
        compare(highlighted(), [2000])
        overview.children.find(c => c.year === 2040).choose()
        compare(highlighted(), [2046])
        verify(overview.activeFocus)
    }
    function test_weekdayHeadings() {
        popup.open()
        const headings = findChild(popup.mainItem, "weekdayHeadings")
        const grid = findChild(popup.mainItem, "calendarDays")
        function checkHeadings(expected, first) {
            const firstCell = grid.children.find(c => c.index === 0)
            compare(new Date(firstCell.day).getUTCDay(), first % 7)
            for (let i = 0; i < 7; ++i) {
                const item = headings.itemAt(i)
                verify(item.visible)
                compare(item.text, expected[i])
                compare([item.x, item.y, item.width, item.height], [15 + i * 23, 69, 23, 16])
            }
        }
        compare(popup.locale.name, "en_US")
        checkHeadings(["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"], Qt.Sunday)
        // Test a Monday-first locale with ambiguous narrow labels, and keep its full short names.
        popup.locale = Qt.locale("de_DE")
        checkHeadings(Array.from({length: 7}, (_, i) => popup.locale.standaloneDayName(i + 1, Locale.ShortFormat)), Qt.Monday)
    }
    function test_dayFocus() {
        popup.open()
        const grid = findChild(popup.mainItem, "calendarDays")
        const days = grid.children.filter(c => c.dayNumber !== undefined)
        const today = days.find(c => c.isToday)
        const previous = days[days.indexOf(today) - 1]
        function checkCue(cell, visible) {
            const image = grabImage(popup.mainItem)
            const cx = grid.x + cell.x, cy = grid.y + cell.y
            for (let y = 0; y < cell.height; ++y) {
                for (let x = 0; x < cell.width; ++x) {
                    const edge = (x >= 1 && x <= 21 && (y === 1 || y === 13))
                              || (y >= 1 && y <= 13 && (x === 1 || x === 21))
                    const dot = edge && ((popup.x + cx + x + popup.y + cy + y) & 1) === 1
                    const color = image.pixel(cx + x, cy + y)
                    compare(color.toString() === "#f5db95", visible && dot, `day ${cell.dayNumber} cue at ${x},${y}: ${color}`)
                }
            }
        }
        tryVerify(() => grid.activeFocus)
        compare(today.y, previous.y)
        compare(today.x - previous.x, 23)
        checkCue(today, true)
        keyClick(Qt.Key_Left)
        compare(popup.selectedDay, 30)
        checkCue(previous, true)
        checkCue(today, false)
        compare(today.border.width, 1)
        keyClick(Qt.Key_Tab)
        verify(!grid.activeFocus)
        verify(previous.isSelected)
        compare(previous.color.toString(), "#0a246a")
        checkCue(previous, false)
        keyClick(Qt.Key_Backtab)
        verify(grid.activeFocus)
        checkCue(previous, true)
    }
    function test_localizedWeekdaysAndBounds() {
        popup.locale = Qt.locale("ar_SA")
        compare(new Set(popup.weekdays).size, 7)
        const first = popup.locale.firstDayOfWeek
        const expected = popup.locale.standaloneDayName(first, Locale.NarrowFormat)
        compare(popup.weekdays[0], expected)
        popup.close()
        popup.locale = Qt.locale()
        popup.now = new Date(1900, 0, 1, 12)
        popup.open()
        const grid = findChild(popup.mainItem, "calendarDays")
        const outside = grid.children.find(c => c.yearNumber === 1899)
        verify(outside !== undefined)
        verify(!outside.enabled)
        verify(outside.Accessible.ignored)
        const previous = findChild(popup.mainItem, "calendarPrevious")
        compare(previous.Accessible.name, "Previous month")
        popup.zoomOut()
        compare(previous.Accessible.name, "Previous year")
        popup.zoomOut()
        compare(previous.Accessible.name, "Previous decade")
        popup.zoomOut()
        compare(previous.Accessible.name, "Previous century")
        const edge = findChild(popup.mainItem, "calendarOverview").children.find(c => c.year === 1890)
        verify(edge !== undefined)
        verify(!edge.enabled)
        verify(edge.Accessible.ignored)
    }
    function test_popup() {
        popup.open()
        compare(popup.width, 331)
        compare(popup.height, 243)
        const heading = findChild(popup.mainItem, "monthHeading")
        const grid = findChild(popup.mainItem, "calendarDays")
        compare(heading.text, "December, 2026")
        compare(grid.children.filter(c => c.dayNumber !== undefined).length, 42)
        compare(popup.selectedDay, 31)
        popup.page(1, true)
        compare(heading.text, "January, 2027")
        popup.page(1, true)
        compare(heading.text, "February, 2027")
        compare(popup.selectedDay, 28)
        popup.moveDay(1)
        compare(heading.text, "March, 2027")
        compare(popup.selectedDay, 1)
        popup.moveDay(-1)
        compare(heading.text, "February, 2027")
        popup.page(-1, true)
        compare(heading.text, "January, 2027")
        popup.zoomOut()
        compare(heading.text, "2027")
        popup.zoomOut()
        compare(heading.text, "2020-2029")
        popup.zoomOut()
        compare(heading.text, "2000-2099")
        popup.zoomOut()
        compare(popup.overview, 3)
        popup.chooseCell(2040, 1)
        compare(heading.text, "2040-2049")
        compare(popup.selectedYear, 2047)
        popup.zoomOut()
        popup.page(-1, false)
        compare(heading.text, "1900-1999")
        verify(!popup.canPage(-1))
        popup.page(1, false)
        popup.choosePeriod()
        compare(heading.text, "2000-2009")
        popup.choosePeriod()
        compare(heading.text, "2007")
        popup.choosePeriod()
        compare(heading.text, "January, 2007")
        const time = findChild(popup.mainItem, "digitalSeconds")
        const secondHand = findChild(popup.mainItem, "secondHand")
        compare(time.text.replace(/\s/g, " "), "7:47:13 AM")
        compare(secondHand.angle, 78)
        popup.now = new Date(2026, 11, 31, 7, 47, 14)
        compare(time.text.replace(/\s/g, " "), "7:47:14 AM")
        compare(secondHand.angle, 84)
        compare(heading.text, "January, 2007")
        popup.close()
        verify(!popup.visible)
        popup.open()
        compare(heading.text, "December, 2026")
        popup.close()
    }
}
