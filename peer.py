import socket
import random
import struct
import message
import pieces
import client
import time
from typing import List
from bitarray import bitarray

BLOCK_LEN = 2**14

class PeerList():
    def __init__(self, num_pieces):
        self.peers: List[Peer] = []
        self.num_pieces = num_pieces

    # Connect to each peer with the handshake
    def connect_to_peers(self, peers_list, peer_id, infohash, my_bitfield):
        for peer in peers_list:
            self.connect_to_peer(peer, peer_id, infohash, my_bitfield)
            
    
    def connect_to_peer(self, peer, peer_id, infohash, my_bitfield):
        # Handshake
        # peer[0]: hostname/ip, peer[1]: port, both are from tracker
        new_peer = Peer(self.num_pieces, peer[0], peer[1])
        retval = new_peer.handshake(peer[0], peer[1], peer_id, infohash)
        
        # Skip peer if handshake fails
        if retval == -1:
            return -1

        # Add to peers list
        #retval.setblocking(False) # Peer sockets will not block. GOOD OR NAH??
        retval.settimeout(None)
        new_peer.sock = retval
        self.peers.append(new_peer)
        
        # Send the new peer our bitfield           
        new_peer.send_bitfield(my_bitfield)

        # only used when connecting to new peers recvd from reannouncing to tracker
        return retval
    
    def get_peer_by_sock(self, sock):
        for peer in self.peers:
            if peer.sock == sock:
                return peer
    
    # returns a random peer that has the piece specified by index, if any
    def get_random_peer_by_piece(self, index):
        have_piece = [peer for peer in self.peers if peer.bitfield[index] and not peer.is_choking()]
        if len(have_piece) == 0:
            return None
        p = random.choice(have_piece)        
        return p

    def get_num_peers_by_piece(self, index):
        count = 0
        for peer in self.peers:
            if peer.bitfield[index] and not peer.is_choking():
                count += 1

        return count
    
    def unchoked_peers_exist(self):
        for peer in self.peers:
            if not peer.is_choking():
                return True
        return False
    
    def does_peer_exist(self, addr, port):
        for peer in self.peers:
            if peer.addr == addr and peer.port == port:
                return True
        return False


# peer class that handles the communication between peers
# each instance represents one external peer the client is connected
class Peer():
    # initialize the peer and handshake with it
    def __init__(self, num_pieces, addr, port = 6881):
        self.connected = False # if the handshake has completed yet
        self.state = {
            'am_choking': True,
            'am_interested': False,
            'peer_choking': True,
            'peer_interested': False,
        }
        self.bitfield = bitarray(num_pieces if num_pieces%8==0 else num_pieces+(8-(num_pieces%8))) # should be a multiple of 8
        self.bitfield[:] = 0 # set bits to 0
        self.sock = None # this might not need to be kept here
        self.peer_id = None # For finding peer later
        self.addr = addr
        self.port = port
        self.last_seen = time.time()
        
    # hostname and port are of the external peer this is connecting to, peer_id is the client's id
    def handshake(self, hostname, port, peer_id, info_hash):
        # TCP connection
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.2)

        try:
            s.connect((hostname, port))
        except Exception as e:
            print(f'{e}. Could not connect to {hostname}:{port}')
            s.close()
            return -1

        # Complete handshake
        data = message.Handshake(peer_id, info_hash).pack() 
        s.sendall(data)

        # If handshake times out, discard peer connection
        try:
            data = s.recv(68)
        except Exception as e:
            print(f'handshake failed with {hostname}:{port}. {e}.')
            s.close()
            return -1

        # If peer sends a b'' packet, they and suck and closed us
        if data == b'':
            print(f'handshake failed with {hostname}:{port}. Peer closed connection')
            s.close()
            return -1

        peer_shake = message.Handshake.read_handshake(data)

        # could also check against peerid recvd from tracker but compact wont have it
        if peer_shake is None or peer_shake.info_hash != info_hash:
            # something went wrong
            print(f'handshake failed with {hostname}:{port}. Infohashes do not match')
            s.close()
            return -1

        self.connected = True
        self.peer_id = f'{hostname}:{port}'
        self.sock = s

        print(f'Connected to {hostname}:{port}!')
        return s  
    
    # sends generic msg 
    def send_msg(self, msg):
        print("send msg")
        self.sock.sendall(msg)
    
    def has_piece(self, index):
        return self.bitfield[index]

    def am_choking(self):
        return self.state['am_choking']
    
    def choke_peer(self):
        self.state['am_choking'] = True
        data = message.Choke().pack() 
        print("send choke")
        self.sock.sendall(data)
    
    def unchoke_peer(self):
        self.state['am_choking'] = False
        data = message.UnChoke().pack()
        print("send unchoke")
        self.sock.sendall(data)
    
    def is_choking(self):
        return self.state['peer_choking']
    
    def choke_self(self):
        self.state['peer_choking'] = True
    
    def unchoke_self(self):
        self.state['peer_choking'] = False

    # update whether or not client should be interested in this peer.
    def update_am_interested(self, my_bitfield):
        for i, x in enumerate(my_bitfield):
            # If peers bf is set and mine is not, we want that piece
            if self.bitfield[i] and not x:
                self.state['am_interested'] = True
                return True
        self.state['am_interested'] = False
        return False
    
    def send_am_interested(self):
        data = message.Interested().pack()
        print("send interested")
        self.sock.sendall(data)
    
    def send_not_interested(self):
        data = message.NotInterested().pack()
        print("send not interested")
        self.sock.sendall(data)
    
    def check_am_interested(self):
        return self.state['am_interested']

    def check_is_interested(self):
        return self.state['is_interested']
    
    def peer_is_interested(self):
        self.state['peer_interested'] = True
    
    def peer_is_not_interested(self):
        self.state['peer_interested'] = False
    
    # notify peer that client
    def send_have(self, piece_index):
        data = message.Have(piece_index).pack()
        #print("send have")
        try:
            self.sock.sendall(data)
        except Exception as e:
            print(f'{e}. Could not send have to {self.sock}')

    def send_bitfield(self, bitfield):
        data = message.BitField(bitfield).pack()
        print("send bitfield")
        self.sock.sendall(data)
    
    def send_req(self, index, begin, length):
        data = message.Request(index, begin, length).pack()
        #print("send request")
        self.sock.sendall(data)

    def send_piece(self, index, begin, block):
        data = message.Piece(index, begin, block).pack()
        print("send piece")
        self.sock.sendall(data)
    
    def send_cancel(self, index, begin, length):
        data = message.Cancel(index, begin, length).pack()
        self.sock.sendall(data)

    def send_keep_alive(self):
        data = message.KeepAlive().pack()
        print("send keep alive")
        self.sock.sendall(data)

    def __str__(self):
        return self.peer_id
    
    def handle_message(self, bytestream, id, downloader: pieces.FileDownloader, reads, peer_list):
        if id == 0:
            print("choke")
            self.choke_self()

        elif id == 1:
            print("unchoke")
            self.unchoke_self()

            if self.check_am_interested():
                self.state['am_interested']
                # send request(s) for random piece they have and we dont
                pass

        elif id == 2:
            print("interested")
            self.peer_is_interested()
            # automatically send an unchoke back?? if we have the pieces ?
            self.unchoke_peer()

        elif id == 3:
            print("not interested")
            self.peer_is_not_interested()
            self.choke_peer()

        elif id == 4:
            print("have")
            index = message.Have.read(bytestream)
            # Set peers bitfield
            self.bitfield[index.payload] = 1
            self.state['am_interested']
            self.send_am_interested()

        elif id == 5:
            print("bitfield")
            # Update peer's bitfield
            bf = message.BitField.read(bytestream)
            self.bitfield = bf.bitfield

            if len(self.bitfield) != len(downloader.bitfield):
                print(f"Wrong bitfield length. Closing {self.getpeername()}")
                reads.remove(self.sock)
                self.sock.close()
                return

            # Check if peer has a piece we are intersted in
            if self.update_am_interested(downloader.bitfield):
                self.send_am_interested()

        elif id == 6:
            print("request")
            index, begin, length = struct.unpack("!LLL", bytestream[5:17])
            
            if not downloader.bitfield[index] or length > BLOCK_LEN:
                # they requested something we dont have, or something bigger than 14KB; ignore
                return

            # Send the correct block from the file
            with open(downloader.filename, 'rb') as file:
                file.seek((index*downloader.piece_len)+begin)
                data = file.read(length)
                self.send_piece(index, begin, data)

        elif id == 7:
            print("piece")
            raw_block = message.Piece.read(bytestream)
            block = pieces.Block(raw_block.index, raw_block.begin, len(raw_block.block), True, raw_block.block, self)
            downloader.update_block(block)

            piece = downloader.piece_list[block.index]
            '''WARNING!! - if everything is recvd but the hash doesn't pass, is_complete still marks the Piece as finished.
                as long as we check stuff with bitfield and not piece.finished this doesnt matter'''
            if piece.is_complete() and piece.checkHash():
                downloader.write_piece_to_file(piece.index)
                downloader.update_bitfield(piece.index)
                
                # send have for all peers and update interesteds
                print(f'send have {len(peer_list)}x')
                for peer in peer_list:
                    if not peer.update_am_interested(downloader.bitfield):
                        self.send_not_interested()
                    peer.send_have(piece.index)

        elif id == 8:
            print("cancel")
            index, begin, length = struct.unpack("!III", bytestream[5:17])[0]

        else:
            print("unknown packet id")