# -*- coding: UTF-8 -*-
from __future__ import unicode_literals

import io
import os
import os.path
import subprocess

import mock
import pytest

from pre_commit.commands.install_uninstall import install
from pre_commit.commands.run import _get_skips
from pre_commit.commands.run import _has_unmerged_paths
from pre_commit.commands.run import get_changed_files
from pre_commit.commands.run import run
from pre_commit.runner import Runner
from pre_commit.util import cmd_output
from pre_commit.util import cwd
from testing.auto_namedtuple import auto_namedtuple
from testing.fixtures import make_consuming_repo


@pytest.yield_fixture
def repo_with_passing_hook(tmpdir_factory):
    git_path = make_consuming_repo(tmpdir_factory, 'script_hooks_repo')
    with cwd(git_path):
        yield git_path


@pytest.yield_fixture
def repo_with_failing_hook(tmpdir_factory):
    git_path = make_consuming_repo(tmpdir_factory, 'failing_hook_repo')
    with cwd(git_path):
        yield git_path


def stage_a_file():
    cmd_output('touch', 'foo.py')
    cmd_output('git', 'add', 'foo.py')


def get_write_mock_output(write_mock):
    return ''.join(call[0][0] for call in write_mock.call_args_list)


def _get_opts(
        all_files=False,
        files=(),
        color=False,
        verbose=False,
        hook=None,
        no_stash=False,
        origin='',
        source='',
):
    # These are mutually exclusive
    assert not (all_files and files)
    return auto_namedtuple(
        all_files=all_files,
        files=files,
        color=color,
        verbose=verbose,
        hook=hook,
        no_stash=no_stash,
        origin=origin,
        source=source,
    )


def _do_run(repo, args, environ={}):
    runner = Runner(repo)
    write_mock = mock.Mock()
    ret = run(runner, args, write=write_mock, environ=environ)
    printed = get_write_mock_output(write_mock)
    return ret, printed


def _test_run(repo, options, expected_outputs, expected_ret, stage):
    if stage:
        stage_a_file()
    args = _get_opts(**options)
    ret, printed = _do_run(repo, args)
    assert ret == expected_ret
    for expected_output_part in expected_outputs:
        assert expected_output_part in printed


def test_run_all_hooks_failing(
        repo_with_failing_hook, mock_out_store_directory
):
    _test_run(
        repo_with_failing_hook,
        {},
        ('Failing hook', 'Failed', 'hookid: failing_hook', 'Fail\nfoo.py\n'),
        1,
        True,
    )


@pytest.mark.parametrize(
    ('options', 'outputs', 'expected_ret', 'stage'),
    (
        ({}, ('Bash hook', 'Passed'), 0, True),
        ({'verbose': True}, ('foo.py\nHello World',), 0, True),
        ({'hook': 'bash_hook'}, ('Bash hook', 'Passed'), 0, True),
        ({'hook': 'nope'}, ('No hook with id `nope`',), 1, True),
        (
            {'all_files': True, 'verbose': True},
            ('foo.py'),
            0,
            True,
        ),
        (
            {'files': ('foo.py',), 'verbose': True},
            ('foo.py'),
            0,
            True,
        ),
        ({}, ('Bash hook', '(no files to check)', 'Skipped'), 0, False),
    )
)
def test_run(
        repo_with_passing_hook,
        options,
        outputs,
        expected_ret,
        stage,
        mock_out_store_directory,
):
    _test_run(repo_with_passing_hook, options, outputs, expected_ret, stage)


@pytest.mark.parametrize(
    ('origin', 'source', 'expect_failure'),
    (
        ('master', 'master', False),
        ('master', '', True),
        ('', 'master', True),
    )
)
def test_origin_source_error_msg(
        repo_with_passing_hook, origin, source, expect_failure,
        mock_out_store_directory,
):
    args = _get_opts(origin=origin, source=source)
    ret, printed = _do_run(repo_with_passing_hook, args)
    warning_msg = 'Specify both --origin and --source.'
    if expect_failure:
        assert ret == 1
        assert warning_msg in printed
    else:
        assert ret == 0
        assert warning_msg not in printed


@pytest.mark.parametrize(
    ('no_stash', 'all_files', 'expect_stash'),
    (
        (True, True, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
    ),
)
def test_no_stash(
        repo_with_passing_hook,
        no_stash,
        all_files,
        expect_stash,
        mock_out_store_directory,
):
    stage_a_file()
    # Make unstaged changes
    with open('foo.py', 'w') as foo_file:
        foo_file.write('import os\n')

    args = _get_opts(no_stash=no_stash, all_files=all_files)
    ret, printed = _do_run(repo_with_passing_hook, args)
    assert ret == 0
    warning_msg = '[WARNING] Unstaged files detected.'
    if expect_stash:
        assert warning_msg in printed
    else:
        assert warning_msg not in printed


@pytest.mark.parametrize(('output', 'expected'), (('some', True), ('', False)))
def test_has_unmerged_paths(output, expected):
    mock_runner = mock.Mock()
    mock_runner.cmd_runner.run.return_value = (1, output, '')
    assert _has_unmerged_paths(mock_runner) is expected


def test_merge_conflict(in_merge_conflict, mock_out_store_directory):
    ret, printed = _do_run(in_merge_conflict, _get_opts())
    assert ret == 1
    assert 'Unmerged files.  Resolve before committing.' in printed


def test_merge_conflict_modified(in_merge_conflict, mock_out_store_directory):
    # Touch another file so we have unstaged non-conflicting things
    assert os.path.exists('dummy')
    with open('dummy', 'w') as dummy_file:
        dummy_file.write('bar\nbaz\n')

    ret, printed = _do_run(in_merge_conflict, _get_opts())
    assert ret == 1
    assert 'Unmerged files.  Resolve before committing.' in printed


def test_merge_conflict_resolved(in_merge_conflict, mock_out_store_directory):
    cmd_output('git', 'add', '.')
    ret, printed = _do_run(in_merge_conflict, _get_opts())
    for msg in ('Checking merge-conflict files only.', 'Bash hook', 'Passed'):
        assert msg in printed


@pytest.mark.parametrize(
    ('environ', 'expected_output'),
    (
        ({}, set([])),
        ({'SKIP': ''}, set([])),
        ({'SKIP': ','}, set([])),
        ({'SKIP': ',foo'}, set(['foo'])),
        ({'SKIP': 'foo'}, set(['foo'])),
        ({'SKIP': 'foo,bar'}, set(['foo', 'bar'])),
        ({'SKIP': ' foo , bar'}, set(['foo', 'bar'])),
    ),
)
def test_get_skips(environ, expected_output):
    ret = _get_skips(environ)
    assert ret == expected_output


def test_skip_hook(repo_with_passing_hook, mock_out_store_directory):
    ret, printed = _do_run(
        repo_with_passing_hook, _get_opts(), {'SKIP': 'bash_hook'},
    )
    for msg in ('Bash hook', 'Skipped'):
        assert msg in printed


def test_hook_id_not_in_non_verbose_output(
        repo_with_passing_hook, mock_out_store_directory
):
    ret, printed = _do_run(repo_with_passing_hook, _get_opts(verbose=False))
    assert '[bash_hook]' not in printed


def test_hook_id_in_verbose_output(
        repo_with_passing_hook, mock_out_store_directory,
):
    ret, printed = _do_run(repo_with_passing_hook, _get_opts(verbose=True))
    assert '[bash_hook] Bash hook' in printed


def test_multiple_hooks_same_id(
        repo_with_passing_hook, mock_out_store_directory,
):
    with cwd(repo_with_passing_hook):
        # Add bash hook on there again
        with io.open('.pre-commit-config.yaml', 'a+') as config_file:
            config_file.write('    - id: bash_hook\n')
        cmd_output('git', 'add', '.pre-commit-config.yaml')
        stage_a_file()

    ret, output = _do_run(repo_with_passing_hook, _get_opts())
    assert ret == 0
    assert output.count('Bash hook') == 2


def test_stdout_write_bug_py26(
        repo_with_failing_hook, mock_out_store_directory, tmpdir_factory,
):
    with cwd(repo_with_failing_hook):
        # Add bash hook on there again
        with io.open(
	    '.pre-commit-config.yaml', 'a+', encoding='UTF-8',
	) as config_file:
            config_file.write('        args: ["☃"]\n')
        cmd_output('git', 'add', '.pre-commit-config.yaml')
        stage_a_file()

        install(Runner(repo_with_failing_hook))

        # Don't want to write to home directory
        env = dict(os.environ, **{b'PRE_COMMIT_HOME': tmpdir_factory.get()})
        # Have to use subprocess because pytest monkeypatches sys.stdout
        _, stdout, _ = cmd_output(
            'git', 'commit', '-m', 'Commit!',
            # git commit puts pre-commit to stderr
            stderr=subprocess.STDOUT,
            env=env,
            retcode=None,
        )
        assert 'UnicodeEncodeError' not in stdout
        # Doesn't actually happen, but a reasonable assertion
        assert 'UnicodeDecodeError' not in stdout


def test_get_changed_files():
    files = get_changed_files(
        '78c682a1d13ba20e7cb735313b9314a74365cd3a',
        '3387edbb1288a580b37fe25225aa0b856b18ad1a',
    )
    assert files == ['CHANGELOG.md', 'setup.py']
