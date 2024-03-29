#! /usr/bin/python

__author__="devilcius"
__date__ ="$Dec 6, 2012 11:10:42 AM$"


import logging
import predatumupdater
import configparser
from sqlite3 import *
import sys


class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class PredBase():

    LOG_FILENAME = 'whatdownload.log'
    LEVELS = {'debug': logging.DEBUG,
              'info': logging.INFO,
              'warning': logging.WARNING,
              'error': logging.ERROR,
              'critical': logging.CRITICAL}

    if len(sys.argv) > 1:
        level_name = sys.argv[1]
        level = LEVELS.get(level_name, logging.NOTSET)
        logging.basicConfig(level=level, datefmt='%m-%d %H:%M', filename=LOG_FILENAME, filemode='w')

class Connector():


    def __init__(self, config):
        self.conn = self.conn = connect('music.db')
        self.conn.text_factory = str
        self.curs = self.conn.cursor()
        self.config = config
        self.mail_user =  config.get("mail","user")
        self.mail_pass =  config.get("mail","password")
        self.mail_recipient = config.get("mail","recipient")
        self.mail_smtp = config.get("mail","smtp")
        self.mail_port = config.get("mail","port")
        self.createAuditTable()

    def createAuditTable(self):
        # Creates table to releases posted to predatum
        self.curs.execute('''create table if not exists audit
          (id integer primary key, folderpath text, pred_updated integer)''')

    def getSnatchedToUpdate(self):
        snatchedToUpdate = {}
        for row in self.curs.execute("select id, fixed_dir, type from snatched where pred_updated = 0 and fixed_dir IS NOT NULL"):
            if row[1]:
                snatchedToUpdate[row[0]] = (row[1], row[2])

        return snatchedToUpdate

    #updates predatum.com
    def updateFromDB(self):
        # first scan files
        releasesToUpdate = self.getSnatchedToUpdate()
        albumsupdated = []
        scan = predatumupdater.Scan(False, self.conn)
        # create table with temp data to gather releases updated and send email
        self.conn.execute('''create table if not exists albums_updated (album text)''')
        self.conn.commit()
        for k, v in list(releasesToUpdate.items()):
            print("updating %s" % v[0])
            albumpath = v[0]
            albumtype = v[1]
            self.conn.execute("insert into albums_updated (album) values (?)", (albumpath[albumpath.rfind("/")+1:len(albumpath)],))
            if scan.folders(albumpath, albumtype):
                self.conn.execute("update snatched set pred_updated = 1 where id = %d" % k)
            else:
                print("update from db failed!")
                break
        self.conn.commit()
        self.curs.execute("select distinct album from albums_updated");
        for row in self.curs:
            albumsupdated.append(row[0]);
        # update predatum.com
        predatum = predatumupdater.Predatum(self.config.get("predatum", "username"), self.config.get("predatum", "passwd"), self.conn)
        while predatum.updateSite():
            time.sleep(0.1) # kind of prevents CPU going nuts

        self.sendEmail(albumsupdated)

        # delete tmp table
        self.conn.execute("delete from albums_updated");
        self.conn.commit()

        self.conn.close()

    def sendEmail(self, albums):
        # Imports
        import smtplib
        from email.mime.text import MIMEText
        albumsupdated = ''
        #create the message
        for album in albums:
            albumsupdated = albumsupdated + album + "\n"

        msg = MIMEText('Predatum has been updated by whatdownloads. Albums added:\n\n%s' % albumsupdated)

        msg['Subject'] = 'whatdownload: Predatum updated!!'

        # Send the message via our own SMTP server

        s = smtplib.SMTP(self.mail_smtp, self.mail_port)
        s.ehlo()
        s.starttls()
        s.ehlo()
        try:
            print('INFO','Emailing %s with a notification.'%self.mail_recipient)
            s.login(self.mail_user, self.mail_pass)
            s.sendmail(self.mail_user, self.mail_recipient, msg.as_string())
            s.quit()
        except Exception as e:
            print('ERROR', 'Could not send notify email. Error: %s'%e.smtp_error)


if __name__ == "__main__":
    print("Hello World");