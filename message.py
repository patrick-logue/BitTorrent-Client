import struct
from bitarray import bitarray

class Handshake():
    def __init__(self, peer_id, info_hash):
        # BitTorrent Protocol v1.0
        self.pstrlen = 19
        self.pstr = b"BitTorrent protocol"

        # Eight reserved bytes (for implementing extensions)
        self.reserved = bytes(8)

        self.info_hash = info_hash
        self.peer_id = peer_id

    def pack(self):
        if len(self.info_hash) != 20:
            print('Wrong info_hash len')
            exit()

        temp_peer_id = self.peer_id
        if not isinstance(temp_peer_id, (bytes, bytearray)):
            temp_peer_id = str.encode(temp_peer_id)
            
        buf = struct.pack('!B19s8s20s20s', self.pstrlen, self.pstr, self.reserved, self.info_hash, temp_peer_id)
        
        return buf

    # Read a handshake from a peer. Change to class method?
    def read_handshake(bytestream):
        pstrlen, pstr = struct.unpack('!B19s', bytestream[:20])
        if pstr != b"BitTorrent protocol":
            print('Not a BitTorrent handshake message')
            return None

        packet = struct.unpack('!B19s8s20s20s', bytestream)
        try:
            peer_id = packet[4].decode('utf8')
        except Exception as e:
            #print(f'{e}. peer_id will stay as a bytestream')
            peer_id = packet[4]

        return Handshake(peer_id, packet[3])


class KeepAlive():
    def __init__(self):
        self.len = 0
        self.ID = None
        self.payload = None
    
    def pack(self):
        return struct.pack('!L', self.len) # No msgID or payload

    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 0:
            print('Not a KeepAlive msg')
            return None
        
        return KeepAlive()


class Choke():
    def __init__(self):
        self.len = 1
        self.ID = 0
        self.payload = None
    
    def pack(self):
        return struct.pack('!Lb', self.len, self.ID)

    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 1:
            print('Wrong msg len (in Choke)')
            return None

        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 0:
            print('Not a Choke msg')
            return None
        
        return Choke()
    

class UnChoke():
    def __init__(self):
        self.len = 1
        self.ID = 1
        self.payload = None

    def pack(self):
        return struct.pack('!Lb', self.len, self.ID)
    
    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 1:
            print('Wrong msg len (in UnChoke)')
            return None
        
        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 1:
            print('Not an Unchoke msg')
            return None
        
        return UnChoke()


class Interested():
    def __init__(self):
        self.len = 1
        self.ID = 2
        self.payload = None

    def pack(self):
        return struct.pack('!Lb', self.len, self.ID)
    
    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 1:
            print('Wrong msg len (in Interested)')
            return None
        
        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 2:
            print('Not an Interested msg')
            return None
        
        return Interested()


class NotInterested():
    def __init__(self):
        self.len = 1
        self.ID = 3
        self.payload = None

    def pack(self):
        return struct.pack('!Lb', self.len, self.ID)

    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 1:
            print('Wrong msg len (in NotInterested)')
            return None

        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 3:
            print('Not an NotInterested msg')
            return None
        
        return NotInterested()


class Have():
    def __init__(self, piece_index):
        self.len = 5
        self.ID = 4
        self.payload = piece_index

    def pack(self):
        return struct.pack('!LbL', self.len, self.ID, self.payload)
    
    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 5:
            print('Wrong msg len (in Have)')
            return None

        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 4:
            print('Not a Have msg')
            return None

        payload = struct.unpack('!L', bytestream[5:9])[0]

        return Have(payload)


# A bitfield of the wrong length is considered an error. Clients should drop the 
# connection if they receive bitfields that are not of the correct size, 
# or if the bitfield has any of the spare bits set. 
class BitField():
    def __init__(self, bitfield):
        self.ID = 5
        self.bitfield = bitfield
        self.bitfield_bytes = bitfield.tobytes()
        self.len = 1 + len(self.bitfield_bytes) # Calculates bytes needed to hold bitfield + 1

    # Bitfield should be an int
    def pack(self):
        pack_format = '!Lb{}s'.format(self.len - 1)
        return struct.pack(pack_format, self.len, self.ID, self.bitfield_bytes)

    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]

        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 5:
            print('Not a BitField msg')
            return None

        payload_format = '!{}s'.format(len - 1)
        payload = struct.unpack(payload_format, bytestream[5:len+4])[0]
        bitfield = bitarray(''.join(format(byte, '08b') for byte in payload))

        return BitField(bitfield)


class Request():
    def __init__(self, index, begin, length):
        self.len = 13
        self.ID = 6
        self.payload = (index, begin, length)

    def pack(self):
        return struct.pack('!LbLLL', self.len, self.ID, self.payload[0], self.payload[1], self.payload[2])

    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 13:
            print('Wrong msg len (in Request)')
            return None
        
        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 6:
            print('Not an Request msg')
            return None

        payload = struct.unpack('!LLL', bytestream[5:17])
        
        return Request(payload[0], payload[1], payload[2])


class Piece():
    def __init__(self, index, begin, block):
        self.ID = 7
        self.index = index
        self.begin = begin
        self.block = block # raw bytestream of the actual file data
        self.len = 9 + len(block)

    def pack(self):
        pack_format = '!LbLL{}s'.format(self.len - 9)

        block = self.block
        if not isinstance(block, (bytes, bytearray)):
            block = str.encode(block)

        return struct.pack(pack_format, self.len, self.ID, self.index, self.begin, block)

    @classmethod
    def read(cls, bytestream):
        length = struct.unpack('!L', bytestream[:4])[0]

        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 7:
            print('Not a Piece msg')
            return None

        payload_format = '!bLL{}s'.format(length - 9)
        payload = struct.unpack(payload_format, bytestream[4:length + 4])
        
        return Piece(payload[1], payload[2], payload[3])

    #new constructor for Piece using incoming Piece message
    @classmethod
    def fromMsg(cls, bytestream):
        return cls(Piece.parse(cls, bytestream))
    
    


class Cancel():
    def __init__(self, index, begin, length):
        self.len = 13
        self.ID = 8
        self.payload = (index, begin, length)

    def pack(self):
        return struct.pack('!LbLLL', self.len, self.ID, self.payload[0], self.payload[1], self.payload[2])

    @classmethod
    def read(cls, bytestream):
        len = struct.unpack('!L', bytestream[:4])[0]
        if len != 13:
            print('Wrong msg len (in Cancel)')
            return None
        
        id = struct.unpack('!b', bytestream[4:5])[0]
        if id != 8:
            print('Not a Cancel msg')
            return None

        payload = struct.unpack('!LLL', bytestream[5:18])
        
        return Request(payload[0], payload[1], payload[2])

# For testing

# if __name__ == '__main__':
#     hand = Handshake('-PB0417-gmauwmwf5c65',b'\xd4Cz\xedh\x1c\xb0l^\xcb\xcf,\x7fY\n\xe8\xa3\xf7:\xeb')
#     bytestream = hand.pack()

#     new_hand = read_handshake(bytestream)
#     s = BitField(1).pack()
#     print(s)

#     ss = BitField.read(s)
#     print(ss)