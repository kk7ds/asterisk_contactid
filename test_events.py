import ConfigParser
import mock
import os
import subprocess
import unittest

import alarm_events

FAKE_EVENT_LINES = ['[metadata]',
                    '',
                    'CALLINGFROM=1',
                    'CALLERNAME=Test',
                    'FOO=bar',
                    '',
                    '[events]',
                    '',
                    '987618340103001_',
                ]



class BaseTest(unittest.TestCase):
    def setUp(self):
        cfg = ConfigParser.ConfigParser()

        cfg.add_section('general')
        cfg.set('general', 'systems', '1')
        cfg.set('general', 'spool_dir', '/tmp')

        cfg.add_section('1')
        cfg.set('1', 'name', 'Test System')
        cfg.set('1', 'email', 'junk@danplanet.com')
        cfg.set('1', 'nomail_events', '570,666')
        cfg.set('1', 'zone_1', 'Front Door')
        cfg.set('1', 'zone_2', 'Back Door')
        cfg.set('1', 'zone_3', 'Motion')
        cfg.set('1', 'user_1', 'Fake Master')
        cfg.set('1', 'user_2', 'Fake User')
        cfg.set('1', 'post_url', 'http://localhost/foo')

        cfg_mock = mock.patch.object(alarm_events, 'CONFIG', cfg)
        cfg_mock.start()
        self.addCleanup(cfg_mock.stop)


class TestEvents(BaseTest):
    def test_disarm(self):
        e = alarm_events.parse_event_code('1', '987618140103001_')
        self.assertEqual('System disarmed normally', e.event)
        self.assertEqual(9876, e.account)
        self.assertEqual(1, e.qualifier)
        self.assertEqual(1, e.zone_number)
        self.assertEqual(3, e.partition)
        self.assertEqual(401, e.event_code)
        self.assertEqual('Fake Master', e.user)
        self.assertEqual('Front Door', e.zone)
        self.assertEqual('Test System', e.system_name)

    def test_arm(self):
        e = alarm_events.parse_event_code('1', '987618340103001_')
        self.assertEqual('System armed normally', e.event)
        self.assertEqual(9876, e.account)
        self.assertEqual(3, e.qualifier)
        self.assertEqual(1, e.zone_number)
        self.assertEqual(3, e.partition)
        self.assertEqual(401, e.event_code)
        self.assertEqual('Fake Master', e.user)
        self.assertEqual('Front Door', e.zone)

    def test_quick_arm(self):
        e = alarm_events.parse_event_code('1', '987618340103098_')
        self.assertEqual('keypad user', e.user)

    def test_unknown_user(self):
        e = alarm_events.parse_event_code('1', '987618340103031_')
        self.assertEqual('User 31', e.user)

    def test_unknown_zone(self):
        e = alarm_events.parse_event_code('1', '987618340103031_')
        self.assertEqual('Zone 31', e.zone)

    def test_summary_4xx(self):
        e = alarm_events.parse_event_code('1', '987618340103001_')
        self.assertEqual('Event 401: System armed normally by '
                         'Fake Master at Test System', str(e))

    def test_summary_1xx(self):
        e = alarm_events.parse_event_code('1', '987618113003001_')
        self.assertEqual('Alarm 130: Burglary alarm in zone '
                         'Front Door at Test System', str(e))


class TestSampleConfig(unittest.TestCase):
    def test_load_sample_config(self):
        alarm_events.load_config('sample.config')


class TestUpdateState(BaseTest):
    def test_put_401_armed(self):
        e = alarm_events.parse_event_code('1', '987618340103001_')
        with mock.patch('urllib2.urlopen') as mock_open:
            alarm_events.update_state('1', e)
            self.assertTrue(mock_open.called)
            req = mock_open.call_args_list[0][0][0]
            self.assertEqual('http://localhost/foo/state', req.get_full_url())
            self.assertEqual('PUT', req.get_method())
            self.assertEqual('armed', req.get_data())

    def test_put_401_disarmed(self):
        e = alarm_events.parse_event_code('1', '987618140103001_')
        with mock.patch('urllib2.urlopen') as mock_open:
            alarm_events.update_state('1', e)
            self.assertTrue(mock_open.called)
            req = mock_open.call_args_list[0][0][0]
            self.assertEqual('http://localhost/foo/state', req.get_full_url())
            self.assertEqual('PUT', req.get_method())
            self.assertEqual('disarmed', req.get_data())

    def test_put_570_bypass(self):
        e = alarm_events.parse_event_code('1', '987618057003001_')
        with mock.patch('urllib2.urlopen') as mock_open:
            alarm_events.update_state('1', e)
            self.assertTrue(mock_open.called)
            req = mock_open.call_args_list[0][0][0]
            self.assertEqual('http://localhost/foo/bypass', req.get_full_url())
            self.assertEqual('PUT', req.get_method())
            self.assertEqual('yes', req.get_data())
            self.assertEqual(1, len(mock_open.call_args_list))

    def test_put_570_unbypass(self):
        e = alarm_events.parse_event_code('1', '987618357003001_')
        with mock.patch('urllib2.urlopen') as mock_open:
            alarm_events.update_state('1', e)
            self.assertTrue(mock_open.called)
            req = mock_open.call_args_list[0][0][0]
            self.assertEqual('http://localhost/foo/bypass', req.get_full_url())
            self.assertEqual('PUT', req.get_method())
            self.assertEqual('no', req.get_data())
            self.assertEqual(1, len(mock_open.call_args_list))


class TestMisc(BaseTest):
    def test_process_event(self):
        extension, event = alarm_events.process_event(FAKE_EVENT_LINES)
        self.assertEqual('1', extension)
        self.assertEqual('987618340103001_', event)

    def test_mail_nomail(self):
        e = alarm_events.Event('1')
        e.event_code = 570
        with mock.patch('subprocess.Popen') as mock_p:
            alarm_events.mail_event(e)
            self.assertFalse(mock_p.called)
        e.event_code = 666
        with mock.patch('subprocess.Popen') as mock_p:
            alarm_events.mail_event(e)
            self.assertFalse(mock_p.called)

    def test_mail_event(self):
        e = alarm_events.parse_event_code('1', '987618140103001_')
        with mock.patch('subprocess.Popen') as mock_p:
            alarm_events.mail_event(e)
            mock_p.assert_called_once_with(['/usr/bin/mail', '-s',
                                            str(e), 'junk@danplanet.com'],
                                           stdin=subprocess.PIPE)
            mock_p.return_value.stdin.write.assert_called_once_with(e.dump())
            mock_p.return_value.stdin.close.assert_called_once_with()
            mock_p.return_value.wait.assert_called_once_with()

    @mock.patch('glob.glob')
    @mock.patch('urllib2.urlopen')
    @mock.patch('subprocess.Popen')
    def test_main(self, mock_popen, mock_urlopen, mock_glob):
        fn = '/tmp/test_event'
        with open(fn, 'w') as f:
            f.write('\n'.join(FAKE_EVENT_LINES))
        mock_glob.return_value = [fn]
        alarm_events.main()
        mock_glob.assert_called_once_with('/tmp/event-*')
        self.assertFalse(os.path.exists(fn))
        self.assertTrue(mock_urlopen.called)
        self.assertTrue(mock_popen.called)
