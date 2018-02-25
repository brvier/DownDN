#!/usr/bin/python2
"""
Sync code inspired by

Synchronator.py
Version: 1.9.0
Created by: Mark Hamilton
Created: March 17, 2017

Didn t found any licence
"""

from __future__ import print_function

import os
import pickle
from functools import partial
from contextlib import contextmanager

import dropbox

try:
    from console import set_color
except ImportError:
    def set_color(r, g, b):
        pass

DROPBOX_FILES = dropbox.files
STATE_FILENAME = '.dropbox_state'
start_end_color = (0, 1, 1)
main_color = (0, 1, 1)
delete_color = (1, 0, 0)
download_color = (0, 0.5, 0)
upload_color = (0, 1, 0)


@contextmanager
def console_color(r, g, b):
    '''
    Sets the console output to the specified color
    Changes it back to black afterwards
    '''
    set_color(r, g, b)
    try:
        yield
    finally:
        set_color(0, 0, 0)


class DropboxState:
    def __init__(self):
        self.local_files = {}       # local file metadata
        self.remote_files = {}      # remote file metadata
        self.local_path = '.'

    def get_fs_path(self, path):
        return os.path.join(self.local_path, path)

    def check_local_update(self, path):
        return os.path.getmtime(self.get_fs_path(path)) > self.local_files[path]['modified']

    def check_state(self, dbx, path):
        if path not in self.remote_files:
            self.upload(dbx, path, '-- Not Found Remotely')
        elif self.check_local_update(path):
            self.upload(dbx, path, '-- Local File Changed')

    def delete_local(self, path):
        with console_color(*delete_color):
            print('\tDeleting Locally: ', path, ' -- File No Longer On Dropbox')
        try:
            os.remove(path)
        except OSError:
            pass
        del self.local_files[path]
        del self.remote_files[path]
        dir = os.path.dirname(path)
        if dir == '':
            dir = '.'
        if os.path.exists(self.get_fs_path(dir)) and not os.listdir(self.get_fs_path(dir)):
            print('\tFolder Empty:', path, ' -- Deleting')
            os.removedirs(self.get_fs_path(dir))

    def delete_remote(self, dbx, path):
        with console_color(*delete_color):
            print('\tDeleting On Dropbox: ', path, ' -- File Deleted Locally')
        try:
            dbx.files_delete('/' + path)
            del self.local_files[path]
            del self.remote_files[path]
        except:
            print('\t!Remote Delete Failed!')
        else:
            dir = os.path.dirname(path)
            if dir == '':
                dir = '.'
            if os.path.exists(dir) and not os.listdir(dir):
                print('\tFolder Empty:', dir, ' -- Deleting')
                os.removedirs(dir)

            dir = '/' + dir
            while len(dir) > 1 and not dbx.files_list_folder(dir).entries:
                print('\tRemote Folder Empty:', dir, ' -- Deleting')
                try:
                    dbx.files_delete(dir)
                except:
                    print('\tRemote Delete Failed!')
                    break
                dir = os.path.dirname(dir)

    def download_remote(self, dbx, path, because=None):
        with console_color(*download_color):
            print('\tDownloading: ', path, because or '')
        head, tail = os.path.split(path)
        if head and not os.path.exists(self.get_fs_path(head)):
            os.makedirs(self.get_fs_path(head))
        result = dbx.files_download_to_file(self.get_fs_path(path), os.path.join('/', path))
        meta = {
            'rev': result.rev,
            'modified': os.path.getmtime(self.get_fs_path(path))
        }
        self.local_files[path] = meta
        self.remote_files[path] = meta

    def execute_delta(self, dbx):
        current_remote_file_paths = set()
        results = dbx.files_list_folder('', True)
        while True:
            cursor = results.cursor
            self.__process_remote_entries(dbx, results.entries, current_remote_file_paths)
            if not results.has_more:
                break
            results = dbx.files_list_folder_continue(cursor)
        # list of file paths that Synchronator thinks are on remote
        remote_files_keys = list(self.remote_files.keys())
        for path in remote_files_keys:
            # remote path was not in the current paths from remote
            if path not in current_remote_file_paths:
                # path exists locally
                if path in self.local_files:
                    # delete file locally
                    self.delete_local(path)

    def make_local_dir(self, path):
        if not os.path.exists(self.get_fs_path(path)):
            # the folder path does not exist
            os.makedirs(self.get_fs_path(path))
        elif os.path.isfile(self.get_fs_path(path)):
            # there is a file in the place that a folder is to be put
            os.remove(self.get_fs_path(path))
            del self.local_files[path]
            os.makedir(self.get_fs_path(path))

    def upload(self, dbx, path, because=None):
        fs_path = self.get_fs_path(path)
        with console_color(*upload_color):
            print('\tUploading: ', path, because or '')
        size = os.path.getsize(fs_path)
        if size > 140000000:
            with open(fs_path, 'rb') as local_fr:
                data = local_fr.read(10000000)
                close = len(data) < 10000000
                session_id = None
                session_cursor = None
                offset = 0
                while not close:
                    if session_id is None:
                        result = dbx.files_upload_session_start(data, close)
                        session_id = result.session_id
                    else:
                        dbx.files_upload_session_append_v2(data,
                                                           session_cursor,
                                                           close)
                    offset += len(data)
                    if session_cursor is None:
                        print('\t.', end='')
                    elif offset % 100000000 == 0:
                        print('.: ', offset)
                        print('\t', end='')
                    else:
                        print('.', end='')
                    session_cursor = DROPBOX_FILES.UploadSessionCursor(session_id,
                                                                       offset)
                    data = local_fr.read(10000000)
                    close = len(data) < 10000000
                mode = DROPBOX_FILES.WriteMode.overwrite
                commit_info = DROPBOX_FILES.CommitInfo(os.path.join('/', path),
                                                       mode, mute=True)
                result = dbx.files_upload_session_finish(data, session_cursor,
                                                         commit_info)
                print('.')
        else:
            with open(fs_path, 'rb') as local_fr:
                data = local_fr.read()
                mode = DROPBOX_FILES.WriteMode.overwrite
                result = dbx.files_upload(data, os.path.join('/', path), mode,
                                          mute=True)
        meta = {'rev': result.rev,
                'modified': os.path.getmtime(self.get_fs_path(path))}
        self.local_files[path] = meta
        self.remote_files[path] = meta

    def handle_conflict(self, dbx, path, prefer_remote=None):
        if prefer_remote is not None:
            if prefer_remote:
                self.download_remote(dbx, path, '-- Preferring Remote File')
            else:
                self.upload(dbx, path, '-- Preferring Local File')
            return prefer_remote
        else:
            self.upload(dbx, path, '-- Preferring Local File')

    def __process_remote_entries(self, dbx, entries, current_remote_file_paths):
        prefer_remote = None
        for entry in entries:
            path = entry.path_display[1:]
            if isinstance(entry, DROPBOX_FILES.FileMetadata):
                rev = entry.rev
                # remote file does not currently exist locally
                if path not in self.local_files:
                    # download remote file to local
                    self.download_remote(dbx, path, '-- Not Found Locally')
                # remote and local files have different revisions
                elif rev != self.local_files[path]['rev']:
                    if self.check_local_update(path):
                        # conflict detected, ask user for behavior
                        prefer_remote = self.handle_conflict(dbx, path, prefer_remote)
                    else:
                        # no conflict, download remote file to local
                        self.download_remote(dbx, path,
                                             '-- Remote File Changed')
                # add remote path to list
                current_remote_file_paths.add(path)
            elif isinstance(entry, DROPBOX_FILES.FolderMetadata):
                if not os.path.exists(self.get_fs_path(path)):
                    print('\n\tMaking Directory: ', path)
                    self.make_local_dir(path)


def check_local(dbx, state):
    with console_color(*main_color):
        print('\nChecking For New Or Updated Local Files')
    filelist = []
    invaliddirs = set()
    for root, dirnames, filenames in os.walk(state.local_path):
        print(invaliddirs)
        if root in invaliddirs:
            invaliddirs.update(map(partial(os.path.join, root), dirnames))
        elif valid_dir_for_upload(root):
            for filename in filenames:
                if valid_filename_for_upload(filename):
                    p = os.path.join(os.path.relpath(root, state.local_path), filename)
                    if p.startswith('./'):
                        p = p[2:]
                    filelist.append(unicode(p.decode('utf-8')))
        else:
            invaliddirs.add(root)
            invaliddirs.update(map(partial(os.path.join, root), dirnames))
    for p in filelist:
        state.check_state(dbx, p)
    with console_color(*main_color):
        print('\nChecking For Deleted Local Files')
    oldlist = list(state.local_files.keys())
    for file in oldlist:
        if file not in filelist:
            print(file)
            state.delete_remote(dbx, file)


def check_remote(dbx, state):
    with console_color(*main_color):
        print('\nUpdating From Dropbox')
    state.execute_delta(dbx)


def load_state(path):
    with console_color(*main_color):
        print('\nLoading Local State')
    try:
        with open(os.path.join(path, STATE_FILENAME), 'rb') as state_fr:
            state = pickle.load(state_fr)
            state.local_path = path
    except:
        print('\nCannot Find State File -- Creating New Local State')
        state = DropboxState()
        state.local_path = path
    return state


def save_state(path, state):
    with console_color(*main_color):
        print('\nSaving Local State')
    with open(os.path.join(path, STATE_FILENAME), 'wb') as state_fr:
        pickle.dump(state, state_fr, pickle.HIGHEST_PROTOCOL)


def valid_dir_for_upload(dir):
    if dir == '.':
        return True
    path = dir.split(os.path.sep)
    if len(path) > 1:
        # Pythonista directory
        if path[1].startswith('site'):
            return False
        # temp directory
        if path[1] in ['temp', 'Examples']:
            return False
        # hidden directory
        if path[-1] != '.' and path[-1].startswith('.'):
            return False
    return True


def valid_filename_for_upload(filename):
    return not any((filename == STATE_FILENAME,  # Synchronator state file
                    filename.startswith('.'),    # hidden file
                    filename.startswith('@'),    # temporary file
                    filename.endswith('~'),      # temporary file
                    filename.endswith('.pyc'),   # generated Python file
                    filename.endswith('.pyo')))  # generated Python file
