from __future__ import absolute_import
from __future__ import unicode_literals

import io
import os
import os.path

import mock
import pytest

import pre_commit.constants as C
from pre_commit import five
from pre_commit.prefixed_command_runner import PrefixedCommandRunner
from pre_commit.runner import Runner
from pre_commit.store import Store
from pre_commit.util import cmd_output
from pre_commit.util import cwd
from testing.fixtures import make_consuming_repo


@pytest.yield_fixture
def tmpdir_factory(tmpdir):
    class TmpdirFactory(object):
        def __init__(self):
            self.tmpdir_count = 0

        def get(self):
            path = os.path.join(tmpdir.strpath, five.text(self.tmpdir_count))
            self.tmpdir_count += 1
            os.mkdir(path)
            return path.encode('UTF-8')

    yield TmpdirFactory()


@pytest.yield_fixture
def in_tmpdir(tmpdir_factory):
    path = tmpdir_factory.get()
    with cwd(path):
        yield path


@pytest.yield_fixture
def in_merge_conflict(tmpdir_factory):
    path = make_consuming_repo(tmpdir_factory, 'script_hooks_repo')
    with cwd(path):
        cmd_output('touch', 'dummy')
        cmd_output('git', 'add', 'dummy')
        cmd_output('git', 'add', C.CONFIG_FILE)
        cmd_output('git', 'commit', '-m', 'Add config.')

    conflict_path = tmpdir_factory.get()
    cmd_output('git', 'clone', path, conflict_path)
    with cwd(conflict_path):
        cmd_output('git', 'checkout', 'origin/master', '-b', 'foo')
        with io.open('conflict_file', 'w') as conflict_file:
            conflict_file.write('herp\nderp\n')
        cmd_output('git', 'add', 'conflict_file')
        with io.open('foo_only_file', 'w') as foo_only_file:
            foo_only_file.write('foo')
        cmd_output('git', 'add', 'foo_only_file')
        cmd_output('git', 'commit', '-m', 'conflict_file')
        cmd_output('git', 'checkout', 'origin/master', '-b', 'bar')
        with io.open('conflict_file', 'w') as conflict_file:
            conflict_file.write('harp\nddrp\n')
        cmd_output('git', 'add', 'conflict_file')
        with io.open('bar_only_file', 'w') as bar_only_file:
            bar_only_file.write('bar')
        cmd_output('git', 'add', 'bar_only_file')
        cmd_output('git', 'commit', '-m', 'conflict_file')
        cmd_output('git', 'merge', 'foo', retcode=None)
        yield os.path.join(conflict_path)


@pytest.yield_fixture(scope='session', autouse=True)
def dont_write_to_home_directory():
    """pre_commit.store.Store will by default write to the home directory
    We'll mock out `Store.get_default_directory` to raise invariantly so we
    don't construct a `Store` object that writes to our home directory.
    """
    class YouForgotToExplicitlyChooseAStoreDirectory(AssertionError):
        pass

    with mock.patch.object(
        Store,
        'get_default_directory',
        side_effect=YouForgotToExplicitlyChooseAStoreDirectory,
    ):
        yield


@pytest.yield_fixture
def mock_out_store_directory(tmpdir_factory):
    tmpdir = tmpdir_factory.get()
    with mock.patch.object(
        Store,
        'get_default_directory',
        return_value=tmpdir,
    ):
        yield tmpdir


@pytest.yield_fixture
def store(tmpdir_factory):
    yield Store(os.path.join(tmpdir_factory.get(), '.pre-commit'))


@pytest.yield_fixture
def cmd_runner(tmpdir_factory):
    yield PrefixedCommandRunner(tmpdir_factory.get())


@pytest.yield_fixture
def runner_with_mocked_store(mock_out_store_directory):
    yield Runner('/')
