#!/usr/bin/env python
# coding=utf-8
from html.entities import name2codepoint as n2cp
import re
import unicodedata
import string

def substitute_entity(match):
    ent = match.group(2)
    if match.group(1) == "#":
        return chr(int(ent))
    else:
        cp = n2cp.get(ent)

        if cp:
            return chr(cp)
        else:
            return match.group()

def decode_htmlentities(string):
    if string:
        entity_re = re.compile("&(#?)(\d{1,5}|\w{1,8});")
        return entity_re.subn(substitute_entity, string)[0]
    else:
        return ''


def unescape(text):

    htmlCodes = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }


    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return chr(int(text[3:-1], 16))
                else:
                    return chr(int(text[2:-1]))
            except ValueError:
                pass
        elif text[:1] == "&":
            import html.entities
            entity = html.entities.entitydefs.get(text[1:-1])
            if entity:
                if entity[:2] == "&#":
                    try:
                        return chr(int(entity[2:-1]))
                    except ValueError:
                        pass
                if entity[:1] in htmlCodes:
                    try:
                        return htmlCodes[entity[:1]]
                    except ValueError:
                        pass

                else:
                    return str(entity, "iso-8859-1")
        else:
            # named entity
            try:
                text = chr(html.entities.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

validchars = "-_.()[] %s%s" % (string.ascii_letters, string.digits)

def removeDisallowedFilenameChars(filename):
    cleanedFilename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore')
    extraCleanedFilename = ''.join(c for c in cleanedFilename.decode('utf-8') if c in validchars)

    return extraCleanedFilename

