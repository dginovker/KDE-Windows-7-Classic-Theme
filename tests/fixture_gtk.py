#!/usr/bin/env python3
"""GTK 3 window used by test_gtk.py: the native-bench control layout, so it can sit next to the Windows reference."""
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

window = Gtk.Window(title='GTK Classic-demo')
window.set_default_size(992, 533)
fixed = Gtk.Fixed()
window.add(fixed)


def place(widget, x, y, w, h):
    widget.set_size_request(w, h)
    fixed.put(widget, x, y)
    return widget


place(Gtk.Label(label='GTK 3 controls; Windows mode theme'), 24, 20, 300, 24)
place(Gtk.Button(label='Normal'), 24, 65, 130, 26)
place(Gtk.ToggleButton(label='Pressed', active=True), 174, 65, 130, 26)
place(Gtk.Button(label='Disabled', sensitive=False), 324, 65, 130, 26)
focused = place(Gtk.Button(label='Focused'), 474, 65, 130, 26)
default = place(Gtk.Button(label='Default', can_default=True), 624, 65, 130, 26)
place(Gtk.CheckButton(label='Unchecked'), 24, 120, 150, 24)
place(Gtk.CheckButton(label='Checked', active=True), 190, 120, 150, 24)
place(Gtk.CheckButton(label='Disabled checked', active=True, sensitive=False), 356, 120, 190, 24)
radio = place(Gtk.RadioButton(label='Radio'), 24, 162, 150, 24)
place(Gtk.RadioButton.new_with_label_from_widget(radio, 'Selected radio'), 190, 162, 180, 24).set_active(True)
place(Gtk.Entry(text='Editable text'), 24, 215, 280, 24)
place(Gtk.Entry(text='Disabled text', sensitive=False), 324, 215, 280, 24)
combo = place(Gtk.ComboBoxText(), 24, 265, 280, 24)
for option in ('Selected option', 'Another option'):
    combo.append_text(option)
combo.set_active(0)
scroll = place(Gtk.Scrollbar(orientation=Gtk.Orientation.HORIZONTAL, adjustment=Gtk.Adjustment(0, 0, 100, 1, 10, 10)), 324, 265, 280, 17)
frame = place(Gtk.Frame(label='Group box'), 24, 330, 580, 120)
frame.add(Gtk.Label(label='The reference is rendered by Windows, not a web simulator.', xalign=0, margin_start=20))
window.connect('destroy', Gtk.main_quit)
window.show_all()
window.set_default(default)
focused.grab_focus()
Gtk.main()
