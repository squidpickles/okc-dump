okc-dump
========

This utility logs into OkCupid, reads all answered questions in the user's
profile, and writes them as XML to stdout. Now it's possible to have backups.

Requirements
============
 * Python 2.7.2 or later
 * BeautifulSoup 4.x
 * OkCupid user account

Usage
=====
Create a file called `okc-dump.ini` in the same directory as the utility. You
can use `okc-dump.ini.sample` as a template. Remember to keep the file readable
only by yourself, as it contains your OkCupid username and password.

Once you have that, just run it from the command line:

    python okc-dump.py > questions.xml

It'll take a little while, but in the end, you'll have your backup.

Disclaimer
==========
I'm not affiliated with OkCupid. They'd probably rather folks not do this, so
try not to abuse their service.
