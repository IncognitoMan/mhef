# Copyright 2015 Seth VanHeulen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import array
import hashlib
import math
import random

from Crypto.Cipher import Blowfish
from Crypto.Util import Counter
from Crypto.Signature import PKCS1_v1_5
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA


MH3G_JP = 0
MH3G_NA = 1
MH3G_EU = 2
MH4_JP = 3
MH4_NA = 4
MH4_EU = 5
MH4G_JP = 6
MH4G_NA = 7
MH4G_EU = 8
MH4G_KR = 9
MH4G_TW = 10
MHX_JP = 11
MHX_NA = 12
MHX_EU = 13
MHS_JP = 14

MH4G_SD_NORMAL = 0
MH4G_SD_CARD = 1
MH4G_SD_QUEST = 2


class SavedataCipher:
    def __init__(self, game):
        if game in (MH4G_JP, MH4G_NA, MH4G_EU, MH4G_KR, MH4G_TW):
            self._cipher = Blowfish.new(b'blowfish key iorajegqmrna4itjeangmb agmwgtobjteowhv9mope')
        elif game == MH4_JP:
            self._cipher = None
        else:
            raise ValueError('Invalid game selected.')

    def _xor(self, buff, key):
        buff = array.array('H', buff)
        for i in range(len(buff)):
            if key == 0:
                key = 1
            key = key * 0xb0 % 0xff53
            buff[i] ^= key
        return buff.tobytes()

    def encrypt(self, buff, type=MH4G_SD_NORMAL):
        csum = sum(bytearray(buff)) & 0xffffffff
        buff = array.array('I', buff)
        buff.insert(0, csum)
        seed = random.getrandbits(16)
        buff = array.array('I', self._xor(buff.tobytes(), seed))
        buff.insert(0, (seed << 16) + 0x10)
        header = buff[:6]
        if type == MH4G_SD_CARD:
            buff = buff[6:]
        if self._cipher:
            buff.byteswap()
            buff = array.array('I', self._cipher.encrypt(buff.tobytes()))
            buff.byteswap()
        if type == MH4G_SD_CARD:
            buff = header + buff
        buff = buff.tobytes()
        if type == MH4G_SD_QUEST:
            buff += b'\x00' * 0x100
        return buff

    def decrypt(self, buff, type=MH4G_SD_NORMAL):
        if type == MH4G_SD_QUEST:
            buff = buff[:-0x100]
        buff = array.array('I', buff)
        header = buff[:6]
        if type == MH4G_SD_CARD:
            buff = buff[6:]
        if self._cipher:
            buff.byteswap()
            buff = array.array('I', self._cipher.decrypt(buff.tobytes()))
            buff.byteswap()
        if type == MH4G_SD_CARD:
            buff = header + buff
        seed = buff.pop(0) >> 16
        buff = array.array('I', self._xor(buff.tobytes(), seed))
        csum = buff.pop(0)
        buff = buff.tobytes()
        if csum != (sum(bytearray(buff)) & 0xffffffff):
            raise ValueError('Invalid checksum in header.')
        return buff

    def encrypt_file(self, savedata_file, out_file, type=MH4G_SD_NORMAL):
        savedata = open(savedata_file, 'rb').read()
        savedata = self.encrypt(savedata, type)
        open(out_file, 'wb').write(savedata)

    def decrypt_file(self, savedata_file, out_file, type=MH4G_SD_NORMAL):
        savedata = open(savedata_file, 'rb').read()
        savedata = self.decrypt(savedata, type)
        open(out_file, 'wb').write(savedata)


class DLCCipher:
    def __init__(self, game):
        if game == MH4G_NA or game == MH4G_EU:
            self._cipher = Blowfish.new(b'AgK2DYheaCjyHGPB')
        elif game == MH4G_JP:
            self._cipher = Blowfish.new(b'AgK2DYheaCjyHGP8')
        elif game == MH4G_KR:
            self._cipher = Blowfish.new(b'AgK2DYheaOjyHGP8')
        elif game == MH4G_TW:
            self._cipher = Blowfish.new(b'Capcom123 ')
        else:
            raise ValueError('Invalid game selected.')

    def encrypt(self, buff):
        buff += hashlib.sha1(buff).digest()
        size = len(buff)
        if len(buff) % 8 != 0:
            buff += b'\x00' * (8 - len(buff) % 8)
        buff = array.array('I', buff)
        buff.byteswap()
        buff = array.array('I', self._cipher.encrypt(buff.tobytes()))
        buff.append(size)
        buff.byteswap()
        return buff.tobytes()

    def decrypt(self, buff):
        buff = array.array('I', buff)
        buff.byteswap()
        size = buff.pop()
        if size > len(buff) * 4:
            raise ValueError('Invalid file size in footer.')
        buff = array.array('I', self._cipher.decrypt(buff.tobytes()))
        buff.byteswap()
        buff = buff.tobytes()[:size]
        md = buff[-20:]
        buff = buff[:-20]
        if md != hashlib.sha1(buff).digest():
            raise ValueError('Invalid SHA1 hash in footer.')
        return buff

    def encrypt_file(self, dlc_file, out_file):
        dlc = open(dlc_file, 'rb').read()
        dlc = self.encrypt(dlc)
        open(out_file, 'wb').write(dlc)

    def decrypt_file(self, dlc_file, out_file):
        dlc = open(dlc_file, 'rb').read()
        dlc = self.decrypt(dlc)
        open(out_file, 'wb').write(dlc)


class DLCXCipher:
    def __init__(self, game, key, pubkey=None):
        self._key = key.encode()
        self._pubkey = None
        if pubkey is not None:
            self._pubkey = RSA.importKey(pubkey)
        if game == MHX_NA or game == MHX_EU or game == MHX_JP:
            self._static_pubkey = RSA.importKey(b'0\x82\x01"0\r\x06\t*\x86H\x86\xf7\r\x01\x01\x01\x05\x00\x03\x82\x01\x0f\x000\x82\x01\n\x02\x82\x01\x01\x00\xa9\x88\x82{\xc7\xbeV\xbe\xaa(\x89\xb0\x96\x18\x82\xab\x96U\xb3q\x89\xbd\xff\x83\xbe\x03\x1aJ8s\xce\xe8S\xc9+\xf2N\xfa\xf9\x0c!\xeaj\xf3&\x1e)\x10n[\xf5L\xac\x03\x06\x8c\xddW\xe1\xf80g&\x17/\x0cT\x18\x8e\x1f\xbc\xec\xab\x11\x11/)S\x06\x9c\x05\xa6t\xd2\x8f\x9c\xca\x80\x02yy,\x89\xb02\x16\x91.\xca\xe2\xd3\xcb]z\xab\xa5_\x85\xb9\xe1\xf7v\x1c\x02D\x7fC\x8f\x0c\x1bc\x885{\x1e\xab\xe0AH\x9b\xe5@\xf0n\x01]\x17a\x1f\x82X\xed\'L\xee!\xd2~\xbd\x9eb\x8d\'\x8d\x8c+CH\xd3\xa1\x1d\x03\xcb\x06\x9a\x80\xd7\xf7\x0c,\xfc\x1a=j\xce\xea\xfb\xa0\xeb\r\x022\x93\x7f\xc7x\x164\xf1\'\xe6.\x16|\xefn!\xe2Z\xef\xb7\xb6<:\x8b;\xaf\xd4X\xa1\xb0p\x92\r\x8f\nKg d\xf7\xdb\xb6\xe8\xae\x92,\xa1\xd9\xaa\xa31\xda\xe7\xbc`#-R\xccp\x99|\x1c\xfb\xbf6\x1ck\x8eBj\xb4S\xe9\xfb\x02\x03\x01\x00\x01')
        elif game == MHS_JP:
            self._static_pubkey = RSA.importKey(b'0\x82\x01"0\r\x06\t*\x86H\x86\xf7\r\x01\x01\x01\x05\x00\x03\x82\x01\x0f\x000\x82\x01\n\x02\x82\x01\x01\x00\xaf\xbc\xf3\x95\x0c\xca-\x97\xf5\x13\xf2\xd3\xf8\xfd\x95x3_\x11+\x84\x86\xbb[\x10m\x16\x03e\xfd\x9chO]\r-\x1e?\x13d\xa5\xde\xa8\x94\r\x98l`\x85\xfa\xf5\xddA{\xfc\xd6\xa3\x88r\x18BU\x9a\xb5\xec\t\xb9\x10\xe0vx\xf7\x86\x11Ao3\xa3*<\xafI5M\xa0d\xd4\xe0\x97\xa2v\xb0hNk2\xab\xc3\x0c\xed\xba\xe4\xed\xd6\xe4;\x10?f\xcf\xaf\xcd\xf1\xbe`+\xda\x83{\x8f(\xc2x.;\x11\x08K\xea\x88\x0f\xdeB\xb5\x1d\xda\xfa\xfb\xa3U\x19\xef\x18\xb91\tQ\xe7\xbe\xc1\x15\x903\n\x88\x82\xb4\x16\xb5\xa8\x87\x06j\xfa\xce\xcd\xb6\x04\xc9\xef\xc1\x14\x1e(:\x88\xea9\xa3\x84\xe2\xe3\xd1\x8c\xee\x1a\xf7{j\x99\xe2B\xcf\x11\x82\xdbLc\xbcF6\xbd\x8b\xef\xcd\xbe\xcfl\x15\n\x03\xae\xd8\xa6\xcf;6)}f\xc1\xc68)\x8d\xc3\xfe]\xd1D\x14gj\\\xb8\xb4\xcd!30\xc9s\xc2\x9fn\xdb\x1bfAnof\x08\xd2\xbb\x9d\x02\x03\x01\x00\x01')
        else:
            raise ValueError('Invalid game selected.')

    def encrypt(self, buff):
        nonce = array.array('I', [random.getrandbits(32)])
        buff += hashlib.sha1(buff).digest()
        length = len(buff)
        buff = array.array('I', buff + b'\x00' * (8 - length % 8))
        buff.byteswap()
        counter = Counter.new(32, prefix=nonce.tobytes(), initial_value=0, little_endian=True)
        cipher = Blowfish.new(self._key, Blowfish.MODE_CTR, counter=counter)
        buff = array.array('I', cipher.encrypt(buff.tobytes()))
        buff.byteswap()
        buff = buff.tobytes()[:length]
        nonce.byteswap()
        return buff + nonce.tobytes() + b'\x00' * 0x200

    def decrypt(self, buff):
        md = SHA256.new(buff[:-0x100])
        verifier = PKCS1_v1_5.new(self._static_pubkey)
        if verifier.verify(md, buff[-0x100:]) == False:
            raise ValueError('Invalid signature in footer.')
        if self._pubkey is not None:
            md = SHA256.new(buff[:-0x200])
            verifier = PKCS1_v1_5.new(self._pubkey)
            if verifier.verify(md, buff[-0x200:-0x100]) == False:
                raise ValueError('Invalid signature in footer.')
        buff = buff[:-0x200]
        nonce = array.array('I', buff[-4:])
        nonce.byteswap()
        length = len(buff) - 4
        buff = array.array('I', buff[:-4] + b'\x00' * (8 - length % 8))
        buff.byteswap()
        counter = Counter.new(32, prefix=nonce.tobytes(), initial_value=0, little_endian=True)
        cipher = Blowfish.new(self._key, Blowfish.MODE_CTR, counter=counter)
        buff = array.array('I', cipher.decrypt(buff.tobytes()))
        buff.byteswap()
        buff = buff.tobytes()[:length]
        md = buff[-20:]
        buff = buff[:-20]
        if md != hashlib.sha1(buff).digest():
            raise ValueError('Invalid SHA1 hash in footer.')
        return buff

    def encrypt_file(self, dlc_file, out_file):
        dlc = open(dlc_file, 'rb').read()
        dlc = self.encrypt(dlc)
        open(out_file, 'wb').write(dlc)

    def decrypt_file(self, dlc_file, out_file):
        dlc = open(dlc_file, 'rb').read()
        dlc = self.decrypt(dlc)
        open(out_file, 'wb').write(dlc)

