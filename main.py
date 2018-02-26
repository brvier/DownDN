'''
Notes
=====

Simple application for reading/writing notes.

'''
__version__ = '1.0.1'

from os.path import join, exists, dirname, basename, relpath, splitext
from os import walk, makedirs, stat
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.properties import ListProperty, StringProperty, \
    NumericProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.clock import Clock
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.widget import Widget
from kivy.vector import Vector
# from kivy.uix.listview import ListItemButton
from kivy.uix.textinput import TextInput  # noqa
from kivy.uix.selectableview import SelectableView  # noqa
from kivy.uix.codeinput import CodeInput  # noqa
from kivy.uix.image import Image
from dropbox import DropboxOAuth2FlowNoRedirect
import time
from plyer.utils import platform
from kivy import kivy_home_dir
from kivy.uix.recycleview import RecycleView
from threading import Thread
from stat import ST_MTIME
import json
import os
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from secrets import APP_KEY, APP_SECRET


import dropbox

if platform in ('macosx', 'ios'):
    HomePath = os.path.expanduser('~/Documents/')
elif platform in ('android',):
    from jnius import autoclass
    Environment = autoclass('android.os.Environment')
    HomePath = Environment.getExternalStorageDirectory().getPath()
    # HomePath = user_data_dir
else:
    HomePath = kivy_home_dir
SettingsPath = os.path.join(HomePath, 'settings.json')


class CircularButton(ButtonBehavior, Widget, ):
    def collide_point(self, x, y):
        return Vector(x, y).distance(self.center) <= self.width / 2


class IconButton(ButtonBehavior, Image, ):
    pass


def create_default_prefs():
    settings = {}
    with open(SettingsPath, 'wb') as fh:
        json.dump(settings, fh)


def get_pref(key, default=None):
    ans = default
    try:
        with open(SettingsPath, 'rb') as fh:
            ans = json.load(fh).get(key)
        if (ans is None) and (default is not None):
            ans = default
    except (IOError, ValueError) as err:
        print(err)
        create_default_prefs()
    return ans


def set_pref(key, value):
    try:
        with open(SettingsPath, 'rb') as fh:
            settings = json.load(fh)
    except IOError as err:
        print(err)
        create_default_prefs()

    settings[key] = value
    with open(SettingsPath, 'wb') as fh:
        json.dump(settings, fh)


class NotesRecycleView(RecycleView):
    def __init__(self, **kwargs):
        super(NotesRecycleView, self).__init__(**kwargs)


class TodosRecycleView(RecycleView):
    def __init__(self, **kwargs):
        super(TodosRecycleView, self).__init__(**kwargs)


class SelectableRecycleBoxLayout(FocusBehavior, LayoutSelectionBehavior,
                                 RecycleBoxLayout):
    ''' Adds selection and focus behaviour to the view. '''


class MutableTextInput(FloatLayout):

    text = StringProperty()
    multiline = BooleanProperty(True)

    def __init__(self, **kwargs):
        super(MutableTextInput, self).__init__(**kwargs)
        Clock.schedule_once(self.prepare, 0)

    def prepare(self, *args):
        self.w_textinput = self.ids.w_textinput.__self__
        self.w_label = self.ids.w_label.__self__
        self.view()

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and touch.is_double_tap:
            self.edit()
        return super(MutableTextInput, self).on_touch_down(touch)

    def edit(self):
        self.clear_widgets()
        self.add_widget(self.w_textinput)
        self.w_textinput.focus = True

    def view(self):
        self.clear_widgets()
        if not self.text:
            self.w_label.text = "Double tap/click to edit"
        self.add_widget(self.w_label)

    def check_focus_and_view(self, textinput):
        if not textinput.focus:
            self.text = textinput.text
            self.view()


class NoteView(Screen):

    index = NumericProperty()
    title = StringProperty()
    content = StringProperty()
    last_modification = StringProperty()
    mtime = NumericProperty()
    filepath = StringProperty()


class NoteListItem(RecycleDataViewBehavior, BoxLayout):

    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)
    title = StringProperty()
    content = StringProperty()
    last_modification = StringProperty()
    mtime = NumericProperty()
    filepath = StringProperty()

    def __init__(self, **kwargs):
        print(kwargs)
        super(NoteListItem, self).__init__(**kwargs)

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        return super(NoteListItem, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        ''' Add selection on touch down '''
        if super(NoteListItem, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        ''' Respond to the selection of items in the view. '''
        self.selected = is_selected
        if is_selected:
            print("selection changed to {0}".format(rv.data[index]))
            self.parent.clear_selection()
        else:
            print("selection removed for {0}".format(rv.data[index]))


class TodoListItem(RecycleDataViewBehavior, BoxLayout):

    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)
    text = StringProperty()
    due = StringProperty()
    done = BooleanProperty(False)
    filename = StringProperty()

    def __init__(self, **kwargs):
        print(kwargs)
        super(TodoListItem, self).__init__(**kwargs)

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        self.index = index
        return super(TodoListItem, self).refresh_view_attrs(rv, index, data)

    def on_touch_down(self, touch):
        ''' Add selection on touch down '''
        if super(TodoListItem, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        ''' Respond to the selection of items in the view. '''
        self.selected = is_selected
        if is_selected:
            self.parent.clear_selection()
            print("selection changed to {0}".format(rv.data[index]))
        else:
            print("selection removed for {0}".format(rv.data[index]))

class TodosScreen(Screen):
    ''' Main Screen listing todos and notes '''


class NotesScreen(Screen):
    ''' Main Screen listing todos and notes '''


class Settings(Screen):
    theme = StringProperty('dark')


class NoteApp(App):

    dbo = DropboxOAuth2FlowNoRedirect(APP_KEY, APP_SECRET)
    connected_to_dropbox = BooleanProperty()
    notes = ListProperty()
    todos = ListProperty()

    def build(self):
        self.sync_th = None

        self.todosScreen = TodosScreen(name='todos')
        self.notesScreen = NotesScreen(name='notes')
        self.noteView = None
        self.transition = SlideTransition(duration=.35)
        root = ScreenManager(transition=self.transition)
        root.add_widget(self.todosScreen)
        root.add_widget(self.notesScreen)
        Clock.schedule_once(self.__init__later__, 0)
        return root

    def load_todos(self):
        self.todos = []
        for path in os.listdir(self.notes_fn):
            if 'todo' in path.lower():
                print(path)
                with open(os.path.join(self.notes_fn, path), 'rb') as fh:
                    content = fh.read().decode('utf-8')
                for line in content.split('\n'):
                    if line.startswith('- [ ]') or line.startswith('- [x]'):
                        self.todos.append({'text': line[5:].strip(),
                                           'due': '',
                                           'done': line.startswith('- [x]'),
                                           'filename': path})

    def __init__later__(self, dt):
        self.load_todos()
        self.load_notes()

        try:
            self.dbx = dropbox.Dropbox(get_pref('access_token'))
            self.connected_to_dropbox = True
        except Exception as err:
            print('Can t connect to dropbox')
        self.sync()
        self.load_todos()

    def load_notes(self):
        if not exists(self.notes_fn):
            makedirs(self.notes_fn)

        self.notes = []
        for path, folders, files in walk(self.notes_fn):
            if os.path.relpath(path, self.notes_fn) != '.':
                continue
            for afile in files:
                if (splitext(basename(afile))[1] in ('.txt')) and (afile[0] != '.'):
                    mtime = stat(join(path, afile))[ST_MTIME]
                    self.notes.append({'title': splitext(basename(afile))[0],
                                       'category': dirname(relpath(join(afile, path), self.notes_fn)),
                                       'last_modification': time.asctime(time.localtime(mtime)),
                                       'mtime': mtime,
                                       'content': '',
                                       'filepath': join(path, afile)})
        self.sort_notes()

    def sort_notes(self, ):
        self.notes = sorted(self.notes,
                            key=lambda k: k['mtime'],
                            reverse=True)

    def save_note(self, filepath, index, content):
        # TODO : Categories in folder
        print('Saving %s' % filepath)
        self.notes[index]['content'] = content
        with open(filepath, 'wb') as fh:
            fh.write(content.encode('utf-8'))
            mtime = stat(filepath)[ST_MTIME]
            self.notes[index]['last_modification'] = time.asctime(time.localtime(mtime))
            self.notes[index]['mtime'] = mtime
        # self.sort_notes()
        self.sync()

    def del_note(self, note_index):
        path = join(self.notes_fn, self.notes[
                    note_index]['title'] + '.txt')
        print('Deleting path ', path)
        # TODO : Remove Local & Remote
        del self.notes[note_index]
        self.sync()
        self.go_notes()

    def inverse_todo(self, index, is_selected):
        if is_selected:
            done = self.todos[index]['done']
            text = self.todos[index]['text']
            filepath = os.path.join(self.notes_fn, self.todos[index]['filename'])
            search_for = u'- [%s] %s' % ('x' if done else ' ', text)
            replace_with = u'- [%s] %s' % (' ' if done else 'x', text)

            with open(filepath, 'rb') as fh:
                content = fh.read().decode('utf-8')

            content = content.replace(search_for, replace_with)

            with open(filepath, 'wb') as fh:
                fh.write(content.encode('utf-8'))

            self.todos[index]['done'] = not done
            self.todosScreen.ids.todolistview.refresh_from_data()

    def edit_note(self, index, is_selected):
        if not is_selected:
            return True

        note = self.notes[index]
        print('Edit Note %s' % note['filepath'])
        try:
            with open(note['filepath'], 'r') as fh:
                note['content'] = fh.read().decode('utf-8')
        except Exception as err:
            print(err)

        if self.noteView is None:
            self.noteView = NoteView(
                name='noteView',
                index=index,
                title=note.get('title'),
                content=note.get('content'),
                last_modification=note.get('last_modification'),
                filepath=note.get('filepath'))
            self.root.add_widget(self.noteView)
        else:
            self.noteView.index = index
            self.noteView.title = note.get('title')
            self.noteView.content = note.get('content')
            self.noteView.last_modification = note.get('last_modification')
            self.noteView.filepath = note.get('filepath')

        self.transition.direction = 'left'
        self.root.current = 'noteView'

    def add_note(self):
        idx = 1
        while (exists(join(self.notes_fn, 'New note %s.txt' % idx))):
            idx += 1
        self.notes.append(
            {'title': 'New note %s' % idx, 'content': '', 'last_modification': '', 'mtime': 0})
        note_index = len(self.notes) - 1
        self.edit_note(note_index)

    def set_note_lastmodification(self, note_index):
        self.notes[note_index]['last_modification'] = time.time()

    # def set_note_content(self, note_index, note_content):
    #    self.notes[note_index]['content'] = note_content
    #    data = self.notes
    #    self.notes = []
    #    self.notes = data
    #    self.save_note(note_index)
    #    self.refresh_notes()

    def set_note_title(self, filepath, index, title):
        self.notes[index]['title'] = title
        os.rename(filepath, join(self.notes_fn, '%s.txt' % title))
        self.refresh_notes()

    def refresh_notes(self):
        notes = self.notes
        self.notes = []
        self.notes = notes
        self.load_todos()

    def sync(self, *kwargs):
        do = True
        if self.sync_th:
            if self.sync_th.is_alive() is True:
                do = False
        if do:
            self.sync_th = Thread(target=self._sync)
            self.sync_th.start()

    def _sync(self,):
        try:
            # TODO: Do the sync
            from sync import load_state, check_remote, check_local, save_state
            dbx = dropbox.Dropbox(get_pref('access_token'))
            # Change current dir for Synchronator
            # os.chdir(self.notes_fn)

            if dbx:
                # load the sync state
                state = load_state(self.notes_fn)
                # check dropbox for sync
                check_remote(dbx, state)
                # save the sync state so far
                save_state(self.notes_fn, state)
                # check local for sync
                check_local(dbx, state)
                # save the sync state
                save_state(self.notes_fn, state)

                self.refresh_notes()
        except Exception as err:
            import traceback
            print(err)
            traceback.print_exc()
            traceback.print_stack()

    def go_notes(self):
        self.transition.direction = 'left'
        self.root.current = 'notes'

    def go_todos(self):
        self.transition.direction = 'right'
        self.root.current = 'todos'

    def start_dropbox_link(self, *kwargs):
        import webbrowser
        webbrowser.open(self.dbo.start())

    def finish_dropbox_link(self, code, *kwargs):
        res = self.dbo.finish(code)
        access_token, account_id, user_id = res.access_token, res.account_id, res.user_id
        set_pref('access_token', access_token)
        set_pref('account_id', account_id)
        set_pref('user_id', user_id)
        self.connected_to_dropbox = True

    def logout_dropbox(self, code, *kwargs):
        set_pref('access_token', None)
        set_pref('account_id', None)
        set_pref('user_id', None)
        self.connected_to_dropbox = False

    def open_settings(self):
        if not hasattr(self, 'settingsScreen'):
            self.settingsScreen = Settings(name='settings')
            self.root.add_widget(self.settingsScreen)
        self.transition.direction = 'left'
        self.root.current = 'settings'

    @property
    def notes_fn(self):
        return join(self.user_data_dir, 'DownDN')


if __name__ == '__main__':
    NoteApp().run()
