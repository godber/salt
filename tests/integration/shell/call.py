# -*- coding: utf-8 -*-
'''
    :codeauthor: :email:`Pedro Algarvio (pedro@algarvio.me)`


    tests.integration.shell.call
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
'''

# Import python libs
import os
import sys
import re
import shutil
import yaml
from datetime import datetime

# Import Salt Testing libs
from salttesting import skipIf
from salttesting.helpers import ensure_in_syspath
ensure_in_syspath('../../')

# Import salt libs
import integration


class CallTest(integration.ShellCase, integration.ShellCaseCommonTestsMixIn):

    _call_binary_ = 'salt-call'

    def test_default_output(self):
        out = self.run_call('-l quiet test.fib 3')

        expect = ['local:',
                  '    |_',
                  '      - 0',
                  '      - 1',
                  '      - 1',
                  '      - 2']
        self.assertEqual(expect, out[:-1])

    def test_text_output(self):
        out = self.run_call('-l quiet --out txt test.fib 3')

        expect = [
            'local: ([0, 1, 1, 2]'
        ]

        self.assertEqual(''.join(expect), ''.join(out).rsplit(",", 1)[0])

    @skipIf(sys.platform.startswith('win'), 'This test does not apply on Win')
    def test_user_delete_kw_output(self):
        ret = self.run_call('-l quiet -d user.delete')
        self.assertIn(
            'salt \'*\' user.delete name remove=True force=True',
            ''.join(ret)
        )

    def test_salt_documentation_too_many_arguments(self):
        '''
        Test to see if passing additional arguments shows an error
        '''
        data = self.run_call('-d virtualenv.create /tmp/ve', catch_stderr=True)
        self.assertIn('You can only get documentation for one method at one time', '\n'.join(data[1]))

    def test_issue_6973_state_highstate_exit_code(self):
        '''
        If there is no tops/master_tops or state file matches
        for this minion, salt-call should exit non-zero if invoked with
        option --retcode-passthrough
        '''
        src = os.path.join(integration.FILES, 'file/base/top.sls')
        dst = os.path.join(integration.FILES, 'file/base/top.sls.bak')
        shutil.move(src, dst)
        expected_comment = 'No states found for this minion'
        try:
            stdout, retcode = self.run_call(
                '-l quiet --retcode-passthrough state.highstate',
                with_retcode=True
            )
        finally:
            shutil.move(dst, src)
        self.assertIn(expected_comment, ''.join(stdout))
        self.assertNotEqual(0, retcode)

    @skipIf(sys.platform.startswith('win'), 'This test does not apply on Win')
    def test_return(self):
        self.run_call('-c {0} cmd.run "echo returnTOmaster"'.format(self.get_config_dir()))
        jobs = [a for a in self.run_run('-c {0} jobs.list_jobs'.format(self.get_config_dir()))]

        self.assertTrue(True in ['returnTOmaster' in j for j in jobs])
        # lookback jid
        first_match = [(i, j)
                       for i, j in enumerate(jobs)
                       if 'returnTOmaster' in j][0]
        jid, idx = None, first_match[0]
        while idx > 0:
            jid = re.match("([0-9]+):", jobs[idx])
            if jid:
                jid = jid.group(1)
                break
            idx -= 1
        assert idx > 0
        assert jid
        master_out = [
            a for a in self.run_run('-c {0} jobs.lookup_jid {1}'.format(self.get_config_dir(), jid))
        ]
        self.assertTrue(True in ['returnTOmaster' in a for a in master_out])

    @skipIf(sys.platform.startswith('win'), 'This test does not apply on Win')
    def test_issue_2731_masterless(self):
        root_dir = os.path.join(integration.TMP, 'issue-2731')
        config_dir = os.path.join(root_dir, 'conf')
        minion_config_file = os.path.join(config_dir, 'minion')
        logfile = os.path.join(root_dir, 'minion_test_issue_2731')

        if not os.path.isdir(config_dir):
            os.makedirs(config_dir)

        master_config = yaml.load(open(self.get_config_file_path('master')).read())
        master_root_dir = master_config['root_dir']
        this_minion_key = os.path.join(
            master_root_dir, 'pki', 'minions', 'minion_test_issue_2731'
        )

        minion_config = {
            'id': 'minion_test_issue_2731',
            'master': 'localhost',
            'master_port': 64506,
            'root_dir': master_root_dir,
            'pki_dir': 'pki',
            'cachedir': 'cachedir',
            'sock_dir': 'minion_sock',
            'open_mode': True,
            'log_file': logfile,
            'log_level': 'quiet',
            'log_level_logfile': 'info'
        }

        # Remove existing logfile
        if os.path.isfile(logfile):
            os.unlink(logfile)

        start = datetime.now()
        # Let's first test with a master running
        open(minion_config_file, 'w').write(
            yaml.dump(minion_config, default_flow_style=False)
        )
        ret = self.run_script(
            'salt-call',
            '--config-dir {0} cmd.run "echo foo"'.format(
                config_dir
            )
        )
        try:
            self.assertIn('local:', ret)
        except AssertionError:
            if os.path.isfile(minion_config_file):
                os.unlink(minion_config_file)
            # Let's remove our key from the master
            if os.path.isfile(this_minion_key):
                os.unlink(this_minion_key)

            raise

        # Calculate the required timeout, since next will fail.
        # I needed this because after many attempts, I was unable to catch:
        #   WARNING: Master hostname: salt not found. Retrying in 30 seconds
        ellapsed = datetime.now() - start
        timeout = ellapsed.seconds + 3

        # Now let's remove the master configuration
        minion_config.pop('master')
        minion_config.pop('master_port')
        open(minion_config_file, 'w').write(
            yaml.dump(minion_config, default_flow_style=False)
        )

        out = self.run_script(
            'salt-call',
            '--config-dir {0} cmd.run "echo foo"'.format(
                config_dir
            ),
            timeout=timeout,
        )

        try:
            self.assertIn(
                'Process took more than {0} seconds to complete. '
                'Process Killed!'.format(timeout),
                out
            )
        except AssertionError:
            if os.path.isfile(minion_config_file):
                os.unlink(minion_config_file)
            # Let's remove our key from the master
            if os.path.isfile(this_minion_key):
                os.unlink(this_minion_key)

            raise

        # Should work with --local
        ret = self.run_script(
            'salt-call',
            '--config-dir {0} --local cmd.run "echo foo"'.format(
                config_dir
            ),
            timeout=15
        )
        try:
            self.assertIn('local:', ret)
        except AssertionError:
            if os.path.isfile(minion_config_file):
                os.unlink(minion_config_file)
            # Let's remove our key from the master
            if os.path.isfile(this_minion_key):
                os.unlink(this_minion_key)
            raise

        # Should work with local file client
        minion_config['file_client'] = 'local'
        open(minion_config_file, 'w').write(
            yaml.dump(minion_config, default_flow_style=False)
        )
        ret = self.run_script(
            'salt-call',
            '--config-dir {0} cmd.run "echo foo"'.format(
                config_dir
            ),
            timeout=15
        )
        try:
            self.assertIn('local:', ret)
        finally:
            if os.path.isfile(minion_config_file):
                os.unlink(minion_config_file)
            # Let's remove our key from the master
            if os.path.isfile(this_minion_key):
                os.unlink(this_minion_key)

    def test_issue_7754(self):
        old_cwd = os.getcwd()
        config_dir = os.path.join(integration.TMP, 'issue-7754')
        if not os.path.isdir(config_dir):
            os.makedirs(config_dir)

        os.chdir(config_dir)

        minion_config = yaml.load(
            open(self.get_config_file_path('minion'), 'r').read()
        )
        minion_config['log_file'] = 'file:///dev/log/LOG_LOCAL3'
        open(os.path.join(config_dir, 'minion'), 'w').write(
            yaml.dump(minion_config, default_flow_style=False)
        )
        ret = self.run_script(
            'salt-call',
            '--config-dir {0} cmd.run "echo foo"'.format(
                config_dir
            ),
            timeout=15,
            catch_stderr=True,
            with_retcode=True
        )
        try:
            self.assertIn('local:', ret[0])
            self.assertFalse(os.path.isdir(os.path.join(config_dir, 'file:')))
        except AssertionError:
            # We now fail when we're unable to properly set the syslog logger
            self.assertIn(
                'Failed to setup the Syslog logging handler', '\n'.join(ret[1])
            )
            self.assertEqual(ret[2], 2)
        finally:
            os.chdir(old_cwd)
            if os.path.isdir(config_dir):
                shutil.rmtree(config_dir)


if __name__ == '__main__':
    from integration import run_tests
    run_tests(CallTest)
