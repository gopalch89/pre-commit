from __future__ import unicode_literals

import os.path

from pre_commit.languages.ruby import _install_rbenv
from pre_commit.util import get_shell


def test_install_rbenv(cmd_runner):
    _install_rbenv(cmd_runner)
    # Should have created rbenv directory
    assert os.path.exists(cmd_runner.path('rbenv'))
    # We should have created our `activate` script
    activate_path = cmd_runner.path('rbenv', 'bin', 'activate')
    assert os.path.exists(activate_path)

    # Should be able to activate using our script and access rbenv
    cmd_runner.run(
        [
            get_shell(),
            '-c',
            '. {prefix}/rbenv/bin/activate && rbenv --help',
        ],
    )


def test_install_rbenv_with_version(cmd_runner):
    _install_rbenv(cmd_runner, version='1.9.3p547')

    # Should be able to activate and use rbenv install
    cmd_runner.run(
        [
            get_shell(),
            '-c',
            '. {prefix}/rbenv/bin/activate && rbenv install --help',
        ],
    )
