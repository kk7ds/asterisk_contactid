=======================================
ContactID event processing for Asterisk
=======================================

Overview
--------

This script provides event processing for ContactID events received by
Asterisk's alarmreceiver module. It is useful for self-monitoring your
alarm system via email and other mechanisms.

*Note:* Use this at your own risk. Do not risk your life or property
on the correct operation of this tool. ABSOLUTELY NO WARRANTY EXPRESS
OR IMPLIED IS PROVIDED WITH THIS CODE.

Configuration
-------------

Configure Asterisk's alarmreceiver.conf to call this script. For
example::

   [general]
   eventcmd=/var/lib/asterisk/alarm_events.py /var/lib/asterisk/my.config
   eventspooldir=/var/lib/asterisk/alarm_events
   logindividualevents=yes
   timestampformat=%a %b %d, %Y @ %H:%M:%S %Z

Use samples/sample.confg to bootstrap your my.config file according to
your needs. Configure your system in the config based on the extension
that is dialed to reach the alarm receiver app.

Configure asterisk to call the AlarmReceiver app. If the extension to
be dialed is 123, something like this::

   exten => 123,1,Ringing()
      same => n,AlarmReceiver
      same => n,Hangup


Testing
-------

The author has used this with GE/Interlogix/Caddx NX-6 and NX-8 alarm
panels with good success.

To run the unit tests, do something like::

  python -munittest test_events

