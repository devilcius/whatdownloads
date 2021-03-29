# -*- coding: utf_8 -*-
#!/usr/bin/env python
import os.path
from sqlite3 import *
import datetime
import shutil
import os
import re
import configparser
from utilities import removeDisallowedFilenameChars
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3




class DB():


    def __init__(self):
        self.conn = connect('music.db')
        self.curs = self.conn.cursor()
        self.curs.execute('PRAGMA journal_mode=WAL')
        self.snatched = []
        self.foldersnotcopied = []
        self.idsnotcopied = []


    def updateDB(self,torrentfolder,torrentid,error, artist, album, year, type, tag, scene, bitrate, media ):

        self.curs.execute("insert into snatched (torrent_folder, torrent_id, error, copied, date, artist, album, year, type, what_tag, pred_updated, scene, bitrate, media) \
                            values(?,?,?,0,?,?,?,?,?,?,?,?,?,? )", \
                          (torrentfolder, torrentid, error, str(datetime.datetime.now()), artist, album, year, type, tag, 0, scene, bitrate, media))
        self.conn.commit()

    def getSnatched(self):

        # Create snatched table if not exists
        self.curs.execute('''create table if not exists snatched
          (id integer primary key, torrent_folder text, torrent_id integer,
                error integer, copied integer, date text, artist text, album text, year text, type text, what_tag text, fixed_dir text,
                genre_tag text, artist_tag text, album_tag text, track_tag text, year_tag text, title_tag text, tags_checked integer, scene integer, bitrate text, media text, pred_updated integer, meta_checked integer)''')

        self.curs.execute("select torrent_id from snatched")
        for row in self.curs:
            self.snatched.append(row[0])
        return self.snatched

    def getSnatchedToCheck(self):
        cursor = self.conn.cursor()
        return cursor.execute("select id, fixed_dir from snatched where meta_checked is null")

    def setSnatchedChecked(self,id):
        cursor = self.conn.cursor()
        cursor.execute("update snatched set meta_checked = 1 where id = %d" % id)
        self.conn.commit()

    def findTagInWhatSnatched(self,id,tag):
        value = None
        #print "DIR TO CHECK::::::: %s\n\n" % dir
        if tag == "date":
            tag = "year"
        if tag == "genre":
            tag = "what_tag"
        self.curs.execute("select "+tag+" from snatched where id = %d" % id)
        for row in self.curs:
            value = row[0]
        return value

    def closeDBConnection(self):
        self.conn.close()

class FixMetadata():

    def __init__(self):
        self.db = DB()

    def isFlacFile(self,file):
        try:
            FLAC(file)
            return True
        except:
            return False


    def isMP3File(self,file):
        try:
            MP3(file)
            return True
        except:
            return False

    def updateFlacMeta(self,file,tag,value):
        audio = FLAC(file)
        audio[tag] = value
        audio.save()


    def updateMP3Meta(self,file,tag,value):
        audio = EasyID3(file)
        audio[tag] = value
        audio.save()

    def scanFiles(self, folderpath, id):
        for root, dirs, files in os.walk(folderpath):
            print("about to check %s" % root)
            #meta tags that can be retrieved from what.cd
            metaTags = ['album', 'artist','genre','date']
            for file in [f for f in files]:
                if self.isFlacFile(os.path.join(root,file)) and os.path.splitext(os.path.join(root,file))[1] == '.flac':    
                    for tag in metaTags: # updates all tags from redacted. More reliable than user tagging
                        whattag = self.db.findTagInWhatSnatched(id, tag)
                        if tag == 'artist' and whattag == 'Various Artists':
                            continue
                        if whattag:
                            self.updateFlacMeta((os.path.join(root,file)), tag, whattag)
                            print("updated {} tag from redacted.cd!".format(tag))
                        else:
                            print("No tag found in local DB ...")

                elif self.isMP3File(os.path.join(root,file)) and os.path.splitext(os.path.join(root,file))[1] == '.mp3':
                    try:
                        for tag in metaTags: # updates all tags from redacted. More reliable than user tagging
                            whattag = self.db.findTagInWhatSnatched(id, tag)
                            if tag == 'artist' and whattag == 'Various Artists':
                                continue                            
                            if whattag:
                                self.updateMP3Meta((os.path.join(root,file)), tag, whattag)
                                print("updated {} tag from redacted.cd!".format(tag))
                            else:
                                print("no tag found found in local DB...")
                    except:
                        print("mp3 file corrupt??")

            
            print("All tags updated!")

        return True



class Sync():

    def __init__(self, db):
        self.config = configparser.ConfigParser()
        self.config.read('whatdownloads.cfg')
        self.storageFolder = self.config.get("paths", "storagefolder")
        self.watchfolder = self.config.get("paths", "watchfolder")
        self.db = db
        self.fixMD = FixMetadata()


    def getFolderCreationDate(self, filename):
        t = os.path.getmtime(filename)
        return datetime.datetime.fromtimestamp(t)


    def updateMP3MetaFromLocalDB(self):
        foldersToUpdate = self.db.getSnatchedToCheck()
        albumsupdated = []

        for row in foldersToUpdate:
            if row[1]:
                albumpath = row[1]
                albumsupdated.append(albumpath[albumpath.rfind("/")+1:len(albumpath)])
                if self.fixMD.scanFiles(albumpath, row[0]):
                    self.db.setSnatchedChecked(row[0])
                    continue
                else:
                    print("update from db failed!")
                    break                    

    def copySnatched(self):
        w_db = DB()
        copied = 0
        self.curs2 = w_db.conn.cursor()
        w_db.curs.execute("select torrent_folder, torrent_id, artist, album, year, type, scene, bitrate, media from snatched where copied = 0 and torrent_folder <> '' and torrent_folder <> '//'")
        #scene release regex to macht folder naming
        scenereg = re.compile('[a-zA-Z0-9_]*-*[a-zA-Z0-9_]*-.*-[a-zA-Z0-9]*')
        for row in w_db.curs:
            #check if is not a scene release or the folder naming doesn't apply to scene folder naming convention
            if row[6] == 0 or not re.match(scenereg,row[0][1:len(row[0])-1]):
                if row[8] == "CD":
                    media = ""
                else:
                    media = "[%s]" % row[8]
                if row[5] == "Album":
                    type = ""
                else:
                    type = "[%s]" % row[5]
                if row[7] == "FLAC":
                    format = ""
                else:
                    if row[7] == "V0 (VBR)" or row[7] == "V2 (VBR)" or row[7] == "V1 (VBR)":
                        format = "[%s]" % row[7][0:2]
                    else:
                        format = "[%s]" % row[7]
                newFolder = row[2] + " - " +row[4]+" - " + row[3] + media  +  format + type;

            else: #scene rls, we keep the folder name
                newFolder = row[0][1:] #remove the first slash

            destinationPath = self.storageFolder + "/" + row[2][0].lower() + "/" + removeDisallowedFilenameChars(newFolder)

            if not os.path.exists(destinationPath):
                if os.path.exists(self.watchfolder + row[0]):
                    shutil.copytree(self.watchfolder + row[0], destinationPath)
                    copied = copied + 1
                    print("%d copied %s to %s with id: %s" % (copied, row[0], destinationPath, row[1]))
                    self.curs2.execute("update snatched set copied = 1, fixed_dir = ?, date = ? where torrent_id = ?", (destinationPath, self.getFolderCreationDate(self.watchfolder + row[0]), row[1]))
                else:
                    print("!!!!%s folder not found, cannot be copied to destination folder" % row[0])
                    self.curs2.execute("update snatched set copied = 2, fixed_dir = ? where torrent_id = ?", (destinationPath, row[1]))
                    if os.path.exists("error"):
                        input = open ("error", "r")
                    else:
                        input = ""
                    f = open("error", "w")
                    f.write("!!!!torrent %d  not found, cannot be copied to destination folder \n%s" % (row[1], input))
                    f.close()
            elif os.path.exists(destinationPath) and os.path.exists(self.watchfolder + row[0]):
                    print("%s already copied to %s with id: %s" % (row[0], destinationPath, row[1]))
                    self.curs2.execute("update snatched set copied = 1, fixed_dir = ?, date = ? where torrent_id = ?", (destinationPath, self.getFolderCreationDate(self.watchfolder + row[0]), row[1]))
            elif os.path.exists(destinationPath) and not os.path.exists(self.watchfolder + row[0]):
                    print("missing origin folder %s with id: %s, did you delete it?" % (self.watchfolder + row[0], row[1]))
                    self.curs2.execute("update snatched set copied = 1, fixed_dir = ?, date = ? where torrent_id = ?", (destinationPath, self.getFolderCreationDate(destinationPath), row[1]))



        w_db.conn.commit()
        w_db.conn.close()
        print("all copied, proceed check files meta tags:")
        self.updateMP3MetaFromLocalDB()
        print("all files checked")
        if self.config.get("predatum", "enabled") == '1':
            print("proceed to update predatum:")
            import predatumconnector
            predatum = predatumconnector.Connector(self.config)
            predatum.updateFromDB()
