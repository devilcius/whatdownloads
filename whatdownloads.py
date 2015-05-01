# -*- coding: utf_8 -*-
#!/usr/bin/env python
import whatapi
import ConfigParser
import time
import os
import organizer
from utilities import decode_htmlentities


class Error(Exception):
    """Base class for exceptions in this module."""
    pass

def checkSnatched(what, what_cd_user, db, alreadysnatched, page):

    whatuser = what.getUser(what_cd_user)
    torrents_snatched = whatuser.getTorrentsSnatched(page)

    for torrent in torrents_snatched:

        torrentid = torrent['id']

        if int(torrentid) in alreadysnatched:
            print "torrent %s already checked!" % torrentid
        else:
            whattorrent = what.getTorrent(torrentid)
            details =  whattorrent.getTorrentDetails()
            folder = whattorrent.getTorrentFolderName()
            year = torrent["year"]
            rlstype = whattorrent.getTorrentReleaseType()
            albumname = torrent["album"]
            tag = torrent["tag"]
            bitrate = details.split('/')[1].strip()
            media = whattorrent.getTorrentMediaType()
            isScene = torrent['scene']
            artist = torrent["artist"]
            if len(torrent['artist']) > 1:
                artist = "%s & %s" % (artist[0],artist[1])
            else:
                artist = artist[0]
            # just in case someone added an empty tag or the artist
            # is missing (already seen, more than once)
            if tag is None:
                    tag = "no_tag"
            if artist is None:
                    artist = "empty artist"
            if year is None:
                    year = "no_year"
            try:
                    if folder != '':
                        print "adding %s to database (%s)" % (decode_htmlentities(folder),torrentid)
                    else:
                        print "adding single file to database (%s)" % torrentid
                    db.updateDB(decode_htmlentities(folder), int(torrentid), 0, decode_htmlentities(artist), decode_htmlentities(albumname), year, rlstype, decode_htmlentities(tag),isScene, bitrate, media)
                    time.sleep(5)
            except Error:
                    print "error while adding torrent to database:"
                    print "Error: %s" % Error.msg
                    error = "Error: %s" % Error.msg
                    print error
                    if os.path.exists("error"):
                        f = open("error", "r")
                        input = open.read()
                        f.close()
                    else:
                        input = ""
                    f = open("error", "w")
                    f.write("error while adding torrent %s to database\n%s\n\n %s" % (torrentid, error, input))
                    f.close()
            scene = False

if __name__ == '__main__':
    #params
    pagestocheck = 1
    #end params
    db = organizer.DB()
    alreadysnatched = db.getSnatched()
    config = ConfigParser.ConfigParser()
    config.read('whatdownloads.cfg')
    what_cd_user = config.get("what", "username")
    what_cd_pwd = config.get("what", "password")
    page = 0
    whatcd = whatapi.getWhatcdNetwork(what_cd_user, what_cd_pwd)
    whatcd.enableCaching()

    for i in range(page, pagestocheck):
        print "checking page %d/%d" % (page+1, pagestocheck)
        checkSnatched(whatcd, what_cd_user, db, alreadysnatched, i+1)
        page = page + 1

    print "Proceding to sync.."
    sync = organizer.Sync(db)
    sync.copySnatched()

