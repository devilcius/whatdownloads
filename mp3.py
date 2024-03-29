# MP3 stream header information support for Mutagen.
# Copyright 2006 Joe Wreschnig
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.

"""MPEG audio stream information and tags."""

import os
import struct

from mutagen.id3 import ID3FileType, BitPaddedInt, delete

__all__ = ["MP3", "Open", "delete", "MP3"]

class error(RuntimeError): pass
class HeaderNotFoundError(error, IOError): pass
class InvalidMPEGHeader(error, IOError): pass

# Mode values.
STEREO, JOINTSTEREO, DUALCHANNEL, MONO = list(range(4))

class MPEGInfo(object):
    """MPEG audio stream information

    Parse information about an MPEG audio file. This also reads the
    Xing VBR header format.

    This code was implemented based on the format documentation at
    http://www.dv.co.yu/mpgscript/mpeghdr.htm.

    Useful attributes:
    length -- audio length, in seconds
    bitrate -- audio bitrate, in bits per second
    sketchy -- if true, the file may not be valid MPEG audio

    Useless attributes:
    version -- MPEG version (1, 2, 2.5)
    layer -- 1, 2, or 3
    mode -- One of STEREO, JOINTSTEREO, DUALCHANNEL, or MONO (0-3)
    protected -- whether or not the file is "protected"
    padding -- whether or not audio frames are padded
    sample_rate -- audio sample rate, in Hz
    encoder -- 9 character encoder string
    lame_preset -- LAME quality preset used during encoding (if any)
    lame_info -- dict containing LAME-specific metadata

    Useless LAME attributes (stored in the lame_info dict):
    vbr_method -- ABR, VBR old/VBR RH, VBR MTRH, VBR MT (2-5)
    lowpass -- lowpass filter value
    ath_type -- ATH type
    preset -- preset level (1-2047, 0 is unknown/unused)
    """

    # Map (version, layer) tuples to bitrates.
    __BITRATE = {
        (1, 1): list(range(0, 480, 32)),
        (1, 2): [0, 32, 48, 56, 64, 80, 96, 112,128,160,192,224,256,320,384],
        (1, 3): [0, 32, 40, 48, 56, 64, 80, 96, 112,128,160,192,224,256,320],
        (2, 1): [0, 32, 48, 56, 64, 80, 96, 112,128,144,160,176,192,224,256],
        (2, 2): [0,  8, 16, 24, 32, 40, 48,  56, 64, 80, 96,112,128,144,160],
        }
        
    __BITRATE[(2, 3)] = __BITRATE[(2, 2)]
    for i in range(1, 4): __BITRATE[(2.5, i)] = __BITRATE[(2, i)]

    # Map version to sample rates.
    __RATES = {
        1: [44100, 48000, 32000],
        2: [22050, 24000, 16000],
        2.5: [11025, 12000, 8000]
        }

    sketchy = False
    encoder = None
    lame_preset = None
    lame_info = None

    def __init__(self, fileobj, offset=None):
        """Parse MPEG stream information from a file-like object.

        If an offset argument is given, it is used to start looking
        for stream information and Xing headers; otherwise, ID3v2 tags
        will be skipped automatically. A correct offset can make
        loading files significantly faster.
        """

        try: size = os.path.getsize(fileobj.name)
        except (IOError, OSError, AttributeError):
            fileobj.seek(0, 2)
            size = fileobj.tell()

        # If we don't get an offset, try to skip an ID3v2 tag.
        if offset is None:
            fileobj.seek(0, 0)
            idata = fileobj.read(10)
            try: id3, insize = struct.unpack('>3sxxx4s', idata)
            except struct.error: id3, insize = '', 0
            insize = BitPaddedInt(insize)
            if id3 == 'ID3' and insize > 0:
                offset = insize
            else: offset = 0

        # Try to find two valid headers (meaning, very likely MPEG data)
        # at the given offset, 30% through the file, 60% through the file,
        # and 90% through the file.
        for i in [offset, 0.3 * size, 0.6 * size, 0.9 * size]:
            try: self.__try(fileobj, int(i), size - offset)
            except error as e: pass
            else: break
        # If we can't find any two consecutive frames, try to find just
        # one frame back at the original offset given.
        else:
            self.__try(fileobj, offset, size - offset, False)
            self.sketchy = True

    def __try(self, fileobj, offset, real_size, check_second=True):
        # This is going to be one really long function; bear with it,
        # because there's not really a sane point to cut it up.
        fileobj.seek(offset, 0)

        # We "know" we have an MPEG file if we find two frames that look like
        # valid MPEG data. If we can't find them in 32k of reads, something
        # is horribly wrong (the longest frame can only be about 4k). This
        # is assuming the offset didn't lie.
        data = fileobj.read(32768)

        frame_1 = data.find(b"\xff")
        while 0 <= frame_1 <= len(data) - 4:
            frame_data = struct.unpack(">I", data[frame_1:frame_1 + 4])[0]
            if (frame_data >> 16) & 0xE0 != 0xE0:
                frame_1 = data.find("\xff", frame_1 + 2)
            else:
                version = (frame_data >> 19) & 0x3
                layer = (frame_data >> 17) & 0x3
                protection = (frame_data >> 16) & 0x1
                bitrate = (frame_data >> 12) & 0xF
                sample_rate = (frame_data >> 10) & 0x3
                padding = (frame_data >> 9) & 0x1
                private = (frame_data >> 8) & 0x1
                self.mode = (frame_data >> 6) & 0x3
                mode_extension = (frame_data >> 4) & 0x3
                copyright = (frame_data >> 3) & 0x1
                original = (frame_data >> 2) & 0x1
                emphasis = (frame_data >> 0) & 0x3
                if (version == 1 or layer == 0 or sample_rate == 0x3 or
                    bitrate == 0 or bitrate == 0xF):
                    frame_1 = data.find("\xff", frame_1 + 2)
                else: break
        else:
            raise HeaderNotFoundError("can't sync to an MPEG frame")

        # There is a serious problem here, which is that many flags
        # in an MPEG header are backwards.
        self.version = [2.5, None, 2, 1][version]
        self.layer = 4 - layer
        self.protected = not protection
        self.padding = bool(padding)

        self.bitrate = self.__BITRATE[(self.version, self.layer)][bitrate]
        self.bitrate *= 1000
        self.sample_rate = self.__RATES[self.version][sample_rate]

        if self.layer == 1:
            frame_length = (12 * self.bitrate / self.sample_rate + padding) * 4
            frame_size = 384
        elif self.version >= 2 and self.layer == 3:
            frame_length = 72 * self.bitrate / self.sample_rate + padding
            frame_size = 576
        else:
            frame_length = 144 * self.bitrate / self.sample_rate + padding
            frame_size = 1152

        if check_second:
            possible = frame_1 + frame_length
            if possible > len(data) + 4:
                raise HeaderNotFoundError("can't sync to second MPEG frame")
            frame_data = struct.unpack(">H", data[int(possible):int(possible) + 2])[0]
            if frame_data & 0xFFE0 != 0xFFE0:
                raise HeaderNotFoundError("can't sync to second MPEG frame")

        frame_count = real_size / float(frame_length)
        samples = frame_size * frame_count
        self.length = samples / self.sample_rate

        # Try to find/parse the Xing header, which trumps the above length
        # and bitrate calculation.
        fileobj.seek(offset, 0)
        data = fileobj.read(32768)
        lame_cbr = False
        try:
            try:
                xing = data[:-4].index(b"Xing")
            except ValueError:
                xing = data[:-4].index(b"Info")
                lame_cbr = True
        except ValueError:
            # Try to find/parse the VBRI header, which trumps the above length
            # calculation.
            try:
                vbri = data[:-24].index(b"VBRI")
            except ValueError: pass
            else:
                # If a VBRI header was found, this is definitely MPEG audio.
                self.sketchy = False
                vbri_version = struct.unpack('>H', data[vbri + 4:vbri + 6])[0]
                if vbri_version == 1:
                    frame_count = struct.unpack(
                        '>I', data[vbri + 14:vbri + 18])[0]
                    samples = float(frame_size * frame_count)
                    self.length = (samples / self.sample_rate) or self.length
        else:
            # If a Xing header was found, this is definitely MPEG audio.
            self.sketchy = False
            flags = struct.unpack('>I', data[xing + 4:xing + 8])[0]
            if flags & 0x1:
                frame_count = struct.unpack('>I', data[xing + 8:xing + 12])[0]
                samples = float(frame_size * frame_count)
                self.length = (samples / self.sample_rate) or self.length
            if not lame_cbr and flags & 0x2:
                f_bytes = struct.unpack('>I', data[xing + 12:xing + 16])[0]
                self.bitrate = int((f_bytes * 8) // self.length)
            self.encoder = data[xing + 120:xing + 129]

        if self.encoder and self.encoder.startswith(b'LAME'):
            lame = xing + 120
            linfo = {}
            linfo['vbr_method'] = struct.unpack('B', bytes([data[lame + 9]]))[0] & 0xF
            linfo['lowpass'] = struct.unpack('B', bytes([data[lame + 10]]))[0]
            linfo['ath_type'] = struct.unpack('B', bytes([data[lame + 19]]))[0] & 0xF
            linfo['preset'] = struct.unpack('>H', data[lame + 26:lame + 28])[0] & 0x1FF
            self.lame_info = linfo
            self.lame_preset = self._guess_lame_preset()

        # If the bitrate * the length is nowhere near the file
        # length, recalculate using the bitrate and file length.
        # Don't do this for very small files.
        fileobj.seek(2, 0)
        size = fileobj.tell()
        expected = (self.bitrate / 8) * self.length
        if not (size / 2 < expected < size * 2) and size > 2**16:
            self.length = size / float(self.bitrate * 8)

    def pprint(self):
        s = "MPEG %s layer %d, %d bps, %s Hz, %.2f seconds" % (
            self.version, self.layer, self.bitrate, self.sample_rate,
            self.length)
        if self.sketchy: s += " (sketchy)"
        return s

    def _guess_lame_preset(self):
        vbr_method = self.lame_info['vbr_method']
        lowpass = self.lame_info['lowpass']
        ath_type = self.lame_info['ath_type']
        preset = self.lame_info['preset']

        if preset == 320:
            return '320'
        elif preset in range(410, 501, 10):
            if vbr_method == 4:
                return 'V%d' % ((500 - preset) / 10)
            else:
                return 'V%d' % ((500 - preset) / 10)
        else:
            presets = ('-r3mix', '-aps', '-ape', '-api', '-apfs', '-apfe',
                       '-apm', '-apfm')
            try:
                return presets[preset - 1001]
            except IndexError:
                pass

        try:
            major, minor = self.encoder[4:8].split(b'.', 1)
            version = (int(major), int(minor))
        except ValueError:
            version = (-1, 0)

        if version < (3, 90) and version > (0, 0):
            if vbr_method == 8 and lowpass in (97, 98) and ath_type == 0:
                return '-r3mix'
        elif version >= (3, 90) and version < (3, 97):
            if vbr_method == 3:
                if lowpass in (195, 196):
                    if ath_type in (2, 4):
                        return '-ape'
                elif lowpass == 190 and ath_type == 4:
                    return 'APS'
                elif lowpass == 180 and ath_type == 4:
                    return '-apm'
            elif vbr_method == 4:
                if lowpass in (195, 196):
                    if ath_type in (2, 4):
                        return '-apfe'
                    elif ath_type == 3:
                        return '-r3mix'
                elif lowpass == 190 and ath_type == 4:
                    return '-apfs'
                elif lowpass == 180 and ath_type == 4:
                    return '-apfm'
            elif (vbr_method in (1, 2) and lowpass in (205, 206) and
                  ath_type in (2, 4)):
                return '-api'

class MP3(ID3FileType):
    """An MPEG audio (usually MPEG-1 Layer 3) file."""

    _Info = MPEGInfo
    _mimes = ["audio/mp3", "audio/x-mp3", "audio/mpeg", "audio/mpg",
              "audio/x-mpeg"]

    def score(filename, fileobj, header):
        filename = filename.lower()
        return (header.startswith("ID3") * 2 + filename.endswith(".mp3") +
                filename.endswith(".mp2") + filename.endswith(".mpg") +
                filename.endswith(".mpeg"))
    score = staticmethod(score)

Open = MP3

class EasyMP3(MP3):
    """Like MP3, but uses EasyID3 for tags."""
    from mutagen.easyid3 import EasyID3 as ID3

