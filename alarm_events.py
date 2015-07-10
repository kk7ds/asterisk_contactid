#!/usr/bin/python

try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser
import glob
import os
import subprocess
import sys
import time
import urllib2


CONFIG = None


events = {
    100: 'Medical alarm',
    110: 'Fire alarm',
    115: 'Manual fire alarm',
    120: 'Panic alarm (keypad audible)',
    121: 'Duress (keypad silent)',
    122: 'Silent panic',
    123: 'Audible panic alarm',
    130: 'Burglary alarm',
    131: 'Burglary alarm (perimeter)',
    132: 'Burglary alarm (interior)',
    133: '24 hour burglary',
    134: 'Burglary alarm (entry)',
    135: 'Burglary alarm (day/night)',
    136: 'Burglary alarm (outdoor)',
    137: 'Tamper alarm',
    138: 'Burglary alarm (near)',
    139: 'Burglary alarm',
    140: 'General alarm',
    150: 'Nonburglary 24-hour alarm',
    151: 'Gas detected',
    154: 'Water leakage',
    158: 'High temperature',
    159: 'Low temperature',

    301: 'AC Fail',
    309: 'Low battery',
    310: 'Ground fault',
    312: 'Aux power overcurrent',
    321: 'Siren tamper',
    333: 'Expander trouble',
    351: 'Telephone fault',
    354: 'Fail to communicate',
    380: 'Zone trouble',
    381: 'RF sensor lost',
    384: 'Sensor battery low',
    391: 'Zone activity fault',
    393: 'CleanMe',

    401: 'Open/Close',
    406: 'Cancel',
    412: 'Download complete',
    423: 'Forced door',
    451: 'Early open/late close',
    454: 'Fail to close',
    457: 'Exit error',

    570: 'Zone bypass',

    601: 'Manual test',
    602: 'Periodic test',
    605: 'Event log full',
    627: 'Start program',
    628: 'End program',
    }


def _update_state(prefix, key, value):
    url = '%s/%s' % (prefix, key)
    req = urllib2.Request(url, data=value)
    req.get_method = lambda: 'PUT'
    try:
        u = urllib2.urlopen(req)
    except urllib2.HTTPError:
        req.get_method = lambda: 'POST'
        u = urllib2.urlopen(req)

def update_state(event):
    try:
        prefix = CONFIG.get(event.system, 'post_url')
    except ConfigParser.NoOptionError:
        return

    try:
        if event.event_code == 570:
            # Record bypasses separately
            inbypass = event.qualifier != 3
            _update_state(prefix, 'bypass', inbypass and 'yes' or 'no')
            return

        if event.event_code == 401:
            if event.qualifier == 1:
                state = 'disarmed'
            elif event.qualifier == 3:
                state = 'armed'
            else:
                state = 'unknown'
            _update_state(prefix, 'state', state)
        _update_state(prefix, 'event', event.event)
        _update_state(prefix, 'event_code', str(event.event_code))
        _update_state(prefix, 'event_full', str(event))
    except Exception, e:
        print 'FAILED to update state: %s' % e


class Event:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def system(self):
        return str(self.account)

    @property
    def system_name(self):
        return CONFIG.get(self.system, 'name')

    @property
    def event(self):
        if self.event_code == 401:
            opens = {1: 'System disarmed normally',
                     3: 'System armed normally'}
            return opens.get(self.qualifier, 'Unknown Open/Close')
        event = events.get(self.event_code, 'UNKNOWN')
        if self.qualifier == 3 and ((self.event_code / 100) != 4):
            qual = ' (restored)'
        elif self.qualifier == 6:
            qual = ' (repeated)'
        else:
            qual =''
        return '%s%s' % (event, qual)

    @property
    def zone(self):
        try:
            return CONFIG.get(self.system, 'zone_%i' % self.zone_number)
        except ConfigParser.NoOptionError:
            return 'Zone %i' % self.zone_number

    @property
    def user(self):
        if self.zone_number == 98:
            return 'keypad user'

        try:
            return CONFIG.get(self.system, 'user_%i' % self.zone_number)
        except ConfigParser.NoOptionError:
            return 'User %i' % self.zone_number

    def __str__(self):
        data = {
            'partition': self.partition,
            'zone_num': self.zone_number,
            'zone': self.zone,
            'user': self.user,
            'event_num': self.event_code,
            'event': self.event,
            'system': self.system_name,
        }
        if self.event_code >= 600:
            res = 'Event %(event_num)i: %(event)s'
        elif self.event_code >= 500:
            res = ('Event %(event_num)i: %(event)s '
                   'in zone %(zone)s')
        elif self.event_code >= 400:
            res = ('Event %(event_num)i: %(event)s '
                   'by %(user)s')
        elif self.event_code >= 300:
            res = ('Event %(event_num)i: %(event)s '
                   'in device %(zone)s')
        elif self.event_code >= 100:
            res = ('Alarm %(event_num)i: %(event)s in zone %(zone)s')
        else:
            res = 'Unknown event %(event_num)i received for index %(zone_num)i'

        if False:
            # Insert partition information
            res = '[P%(partition)02i] ' + res

        res += ' at %(system)s'
        return res % data

    def dump(self):
        keys = ['event', 'zone', 'user', 'event_code', 'zone_number',
                'partition', 'qualifier', 'account', 'raw_event',
                'system_name', 'from_name', 'from_ext']
        string = ''
        for key in keys:
            if hasattr(self, key):
                string += '%s=%s\n' % (key, getattr(self, key))
        return string


def process_event(lines):
    event = None
    ext = None
    name = None
    for line in lines:
        if not line:
            continue
        if line.startswith('CALLINGFROM'):
            _, ext = line.split('=', 1)
            ext = ext.strip()
        if line.startswith('CALLERNAME'):
            _, name = line.split('=', 1)
            name = name.strip()
        if line[0].isdigit():
            event = line.strip()
            break

    return ext, name, event


def process_event_file(filename):
    with file(filename) as f:
        lines = f.readlines()
    return process_event(lines)


def parse_event_code(event_code):
    event = Event()
    event.account = int(event_code[0:4])
    event.qualifier = int(event_code[6])
    event.event_code = int(event_code[7:10])
    event.partition = int(event_code[10:12])
    event.zone_number = int(event_code[12:15])
    event.raw_event = event_code
    return event


def mail_event(event):
    nomail = CONFIG.get(event.system, 'nomail_events').split(',')
    nomail = [int(x) for x in nomail]
    if event.event_code in nomail:
        return
    fromaddr = CONFIG.get('general', 'email_from')
    dest = CONFIG.get(event.system, 'email')
    mail = subprocess.Popen(
        ['/usr/bin/mail',
         '-S', 'from=%s' % fromaddr,
         '-s', str(event), dest],
         stdin=subprocess.PIPE)
    mail.stdin.write(event.dump())
    mail.stdin.close()
    mail.wait()


def log_event(event):
    filename = os.path.join(os.getenv('HOME', '/tmp'),
                            '%s-security.log' % event.account)
    line = '%s: %s' % (time.strftime('%Y-%m-%dT%H:%M:%S'),
                       str(event))
    with file(filename, 'a') as f:
        f.write(line + '\n')


def load_config(filename):
    global CONFIG
    CONFIG = ConfigParser.ConfigParser()
    CONFIG.read(filename)


def main():
    spool = CONFIG.get('general', 'spool_dir')
    files = glob.glob(os.path.join(spool, 'event-*'))
    for filename in files:
        from_ext, from_name, event_code = process_event_file(filename)
        event = parse_event_code(event_code)
        event.from_ext = from_ext
        event.from_name = from_name

        mail_event(event)
        log_event(event)
        update_state(event)
        os.remove(filename)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print 'Requires config path as argument'

    load_config(sys.argv[1])
    main()
