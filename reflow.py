#!/usr/bin/env python
# -*- coding: utf8 -*-

#  Reflow plugin for pluma
#
#  Copyright (C) 2011 Guillaume Chereau
#
#  This program is free software: you can redistribute it and/or modify it under
#  the terms of the GNU General Public License as published by the Free Software
#  Foundation, either version 3 of the License, or (at your option) any later
#  version.
#
#  This program is distributed in the hope that it will be useful, but WITHOUT
#  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#  FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
#  details.
#
#  You should have received a copy of the GNU General Public License along with
#  this program.  If not, see <http://www.gnu.org/licenses/>.

import pluma
import gtk
import re
import textwrap

# TODO:
# - Replace cursor at the correct position after a reflow.
# - Support double space characters (like chinese chars).
# - Fix bug when there is no newline at the end of the document.

ACCELERATOR = '<Alt>q'

# Simple to start.
FILL_REGEX = r'^([#\*"/\-\+]*\s*)+'

class ReflowPlugin(pluma.Plugin):
    def __init__(self):
        pluma.Plugin.__init__(self)
        self._instances = {}

    def activate(self, window):
        self._instances[window] = ReflowWindowHelper(self, window)
        self._instances[window].activate()

    def deactivate(self, window):
        self._instances[window].deactivate()
        del self._instances[window]

    def update_ui(self, window):
        self._instances[window].update_ui()


class ReflowWindowHelper:
    def __init__(self, plugin, window):
        print "Plugin created for", window
        self._window = window
        self._plugin = plugin

    def activate(self):
        # Add reflow paragraph shortcut.
        actions = []
        manager = self._window.get_ui_manager()
        name = 'Reflow'
        stock_id = None
        label = 'Reflow'
        accelerator = ACCELERATOR
        tooltip = 'Reflow paragraph.'
        callback = lambda action: self._reflow()
        actions.append((name, stock_id, label, accelerator, tooltip, callback))
        self._action_group = gtk.ActionGroup("ReflowPluginActions")
        self._action_group.add_actions(actions)
        manager.insert_action_group(self._action_group, -1)
        ui_str = """
            <ui>
              <menubar name="MenuBar">
                <menu name="EditMenu" action="Edit">
                  <placeholder name="EditOps_6">
                    <placeholder name="Rewrap">
                      <menuitem name="reflow" action="Reflow"/>
                    </placeholder>
                  </placeholder>
                </menu>
              </menubar>
            </ui>
            """
        self._menu_ui_id = manager.add_ui_from_string(ui_str)

    def deactivate(self):
        manager = self._window.get_ui_manager()
        manager.remove_action_group(self._action_group)
        self._action_group = None
        manager.ensure_update()

        self._window = None
        self._plugin = None

    def update_ui(self):
        pass

    def _reflow(self):
        begin, end = self._get_paragraph()
        if begin == end:
            return
        # We first reflow up to the cursor location, just to get the number of
        # characters from the beginning till the cursor.
        document = self._window.get_active_document()
        insert_mark = document.get_insert()
        insert_iter = document.get_iter_at_mark(insert_mark)
        before_text = document.get_iter_at_line(begin).get_text(insert_iter)
        text = self._fill(before_text)
        insert_pos = len(text) # We use it later to restore the cursor pos.
        # Fill all the lines in the paragraph
        lines = [self._get_line(i) for i in range(begin, end)]
        text = self._fill("\n".join(lines))
        self._replace(begin, end, text)
        # Restore the cursor pos.
        # XXX: there is a bug if the cursor was after a space.
        cursor_iter = document.get_iter_at_line(begin)
        cursor_iter.forward_chars(insert_pos)
        document.place_cursor(cursor_iter)

    def _fill(self, text):
        lines = text.splitlines()
        splits = [self._split(x) for x in lines]
        lines = [x[1].strip() for x in splits]
        text = '\n'.join(lines)
        first_prefix = splits[0][0]
        prefix = splits[-1][0]
        text = textwrap.fill(text,
                             width = get_pluma_margin(),
                             initial_indent=first_prefix,
                             subsequent_indent=prefix,
                             drop_whitespace=True)
        return text

    def _get_line(self, index):
        document = self._window.get_active_document()
        begin = document.get_iter_at_line(index)
        if begin.ends_line():
            return ""
        end = begin.copy()
        end.forward_to_line_end()
        return begin.get_text(end)

    def _split(self, line, prefix=None):
        if prefix is None:
            m = re.match(FILL_REGEX, line) # XXX: too slow I guess
            if not m:
                return (None, line)
            return (m.group(), line[m.end():])
        else:
            if not line.startswith(prefix):
                return (None, line)
            return (prefix, line[len(prefix):])

    def _get_paragraph(self):
        """return begin and end line of the current paragraph"""
        document = self._window.get_active_document()
        insert_mark = document.get_insert()
        start = document.get_iter_at_mark(insert_mark).get_line()
        end = start
        prefix, line = self._split(self._get_line(start))
        if prefix is None or line.strip() == "":
            return start, end
        while start > 0:
            other_prefix, line = self._split(self._get_line(start - 1))
            if line.strip() == "" or prefix and not other_prefix:
                break
            if other_prefix != prefix:
                # Check if we should consider the line as part of the block or
                # not.  This is a quite empirical formula that works fine in
                # most of the tested cases.
                if len(other_prefix) <= prefix and \
                        len(other_prefix.strip()) >= len(prefix.strip()):
                    start -= 1
                break
            start -= 1

        # When we run the command on the firt line, then we consider all the
        # lines that starts with the first line prefix.
        search_prefix = prefix if start == end else None
        while end < document.get_line_count():
            end += 1
            other_prefix, line = self._split(self._get_line(end), search_prefix)
            if other_prefix != prefix or line.strip() == "":
                break
        return start, end

    def _replace(self, begin, end, text):
        document = self._window.get_active_document()
        document.begin_user_action()
        begin_iter = document.get_iter_at_line(begin)
        if end >= document.get_line_count():
            end_iter = document.get_end_iter()
        else:
            end_iter = document.get_iter_at_line(end)
            end_iter.backward_char()
        document.delete(begin_iter, end_iter)
        document.insert(begin_iter, text)
        document.end_user_action()


def get_pluma_margin():
    # We no longer have mateconf, but we can't from gi.repository import Gio
    # because apparently "static modules" are already loaded by the time we get
    # control.
    return 80

