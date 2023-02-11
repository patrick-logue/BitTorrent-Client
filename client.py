import sys
import os
import tracker
import peer
import pieces
import time
import message
import socket
import select
import struct
import random
from bitarray import bitarray

def receive(sock, size=4096):
    data= b''
    while True:
        try:
            buf = sock.recv(size)
            if not buf:
                break

            data += buf
        except Exception as e:
            # No more data to receive
            break

    return data

def receive_msg(sock):
    data = b''
    buf = 0
    recved = 0
    msg_len = 0
    while recved < 4:
        try:
            buf = sock.recv(4)
            if not buf:
                break # No data

            msg_len = struct.unpack('!L', buf)[0]
            data += buf
            recved += len(buf)
        except Exception as e:
            print(e, 'recved < 4')
            break
    
    recved = 0

    while recved < msg_len:
        try:
            buf = sock.recv(msg_len-recved)
            if not buf:
                break

            data += buf
            recved += len(buf)
        except Exception as e:
            print(e, 'recved < msg_len')
            break
    
    return data


    
class Client():
    def __init__(self, torrent, compact, port = 6881, seeder = 0):
        self.tracker = tracker.Tracker(torrent, compact, port)
        self.peers_manager = peer.PeerList(self.tracker.torrent_num_pieces)
        self.pieces = pieces.FileDownloader(self.tracker.torrent_name, self.tracker.torrent_length,
                                            self.tracker.torrent_piece_length, self.tracker.torrent_pieces_hash,
                                            self.tracker.torrent_num_pieces)
        self.num_requests = 0
        self.port = port
        self.seed = seeder

        if seeder == 1:
            print("client running as seeder")
            if not os.path.isfile(self.pieces.filename):
                print("file to seed not found")
                exit()

    def run(self):
        # If we are seeding the file, set bitfield to all 1
        if self.seed == 1:
            self.pieces.bitfield.setall(1)
                    
        # Init the peers list then connect to each peer
        self.peers_manager.connect_to_peers(self.tracker.peer_list, self.tracker.peer_id, self.tracker.info_hash, self.pieces.bitfield)

        # establish the port to listen for new connections
        HOST = "0.0.0.0"  # I think this works for what we want?? idk it shows up in the connection as a real ipv4 addr but a random port
        PORT = self.port  # should be 6881-6889
        master_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        master_sock.setblocking(0)
        master_sock.bind((HOST, PORT))
        master_sock.listen()
        
        # sockets for reading incoming messages
        reads = [peer.sock for peer in self.peers_manager.peers]
        reads.append(master_sock)
        new_conns = []

        # initialize the timeout
        tr_timedout = False
        ka_timedout = False
        tracker_timeout = self.tracker.interval
        print(f"tracker_timeout: {tracker_timeout}")
        keep_alive_timeout = 60 # in seconds

        # Unchoke
        for peerUn in self.peers_manager.peers:
            peerUn.unchoke_peer()
        
        while not self.pieces.is_completed() or self.seed == 1:
            time0 = time.time()
            if(tracker_timeout < keep_alive_timeout):
                timeout = tracker_timeout
                tr_timedout = True
            else:
                timeout = keep_alive_timeout
                ka_timedout = True

            # Check for broken pipes and unconnected transport endpoints
            for socket_ in reads:
                # skip listening socket
                if socket_ == master_sock:
                    continue

                try:
                    socket_.getpeername()
                except Exception as e:
                    peer__ = self.peers_manager.get_peer_by_sock(socket_)
                    print(f'{e}. closing {peer__.addr}:{peer__.port}')
                    self.peers_manager.peers.remove(peer__)
                    reads.remove(socket_)
                    socket_.close()
            

            print(f'num req in pipeline: {self.num_requests}')
            # Requests are sent here
            if self.peers_manager.unchoked_peers_exist() and not self.pieces.is_completed() and self.num_requests < 50:
                #piece = self.pieces.get_rarest_piece(self.peers_manager) <---- END GAME IMPLEMENTATION
                for piece in self.pieces.piece_list:

                    if piece.finished:
                        continue

                    p0 = 0
                    peer0 = self.peers_manager.get_random_peer_by_piece(piece.index) 
                    peer1 = self.peers_manager.get_random_peer_by_piece(piece.index)                  

                    for block in piece.block_list:
                        # resend request if block hasnt been received after 10 seconds
                        if block.gathered == False and block.sent_to != None and time0 - block.time > 10 and self.num_requests > 0:
                            block.sent_to = None
                            self.num_requests -= 1
                            print(self.num_requests)
                        # Send request for blocks we still need
                        if block.gathered == False and self.num_requests < 50 and block.sent_to == None:
                            if p0 < 25:
                                peer0.send_req(block.index, block.begin, block.length)
                                block.sent_to = peer0
                            else:
                                peer1.send_req(block.index, block.begin, block.length)
                                block.sent_to = peer1
                            
                            block.time = time.time()
                            print(f'Sent {peer_} a request for {block}')
                            self.num_requests += 1
                            print(self.num_requests)

            r, w, e, = select.select(reads, [], [], timeout)
            for sock in r:
                if sock is master_sock:
                    # new peer connection
                    new_sock, addr = sock.accept()
                    print(f"got new peer: {addr}")
                    new_sock.setblocking(0)
                
                    reads.append(new_sock)
                    new_conns.append(new_sock)

                    new_peer = peer.Peer(self.peers_manager.num_pieces, addr[0], addr[1])
                    new_peer.sock = new_sock
                    self.peers_manager.peers.append(new_peer)

                elif sock in new_conns:
                    # if its a new connection, this will be a handshake
                    data = receive(sock) # NOT receive_msg
                    peer_ = self.peers_manager.get_peer_by_sock(sock)

                    handshake = message.Handshake.read_handshake(data)
                    if (handshake != None):
                        print(f"handshake from {peer_.addr}:{peer_.port}!")
                        peer_.peer_id = handshake.peer_id
                        # reply to the handshake
                        reply = message.Handshake(self.tracker.peer_id, self.tracker.info_hash).pack()
                        peer_.send_msg(reply)

                        peer_.send_bitfield(self.pieces.bitfield)
                    else:
                        # something wrong with handshake
                        print("wrong handshake recvd. terminating connection")
                        self.peers_manager.peers.remove(peer_)
                        reads.remove(sock)
                        sock.close()
                    
                    new_conns.remove(sock)
                   
                else:
                    before_time = time.time()
                    data = receive_msg(sock)
                    after_time = time.time()

                    data_len = len(data)
                    print(f"recv'd data of len:{data_len}")
                    if data:
                        # peer with data
                        peer_ = self.peers_manager.get_peer_by_sock(sock) #peer_ instead of peer to differentiate between module

                        # update the time last seen
                        peer_.last_seen = time.time()
                        
                        msg_len = struct.unpack('!L', data[:4])[0]
                        
                        if msg_len == 0:
                            print("keep alive")
                        else:                  
                            id = struct.unpack('!b', data[4:5])[0]
                            id = int(id)
                            peer_.handle_message(data, id, self.pieces, reads, self.peers_manager.peers)
                            # Validate bitfield length. Drop peer if lengths unequal
                            if id == 5 and len(peer_.bitfield) != len(self.pieces.bitfield):
                                break
                            if id == 7:
                                self.num_requests -= 1
                            
                        # Remove slow connections
                        if after_time - before_time >= 1.0:
                            print(f'SLOW CONNECTION CLOSING: {sock}')
                            peer_ = self.peers_manager.get_peer_by_sock(sock)
                            self.peers_manager.peers.remove(peer_)
                            reads.remove(sock)
                            for piece in self.pieces.piece_list:
                                if piece.finished:
                                    continue
                                
                                for block in piece.block_list:
                                    if block.gathered == False and block.sent_to != None and block.sent_to.peer_id == peer_.peer_id:
                                        block.sent_to = None
                                        self.num_requests -= 1
                            sock.close()

                    else:
                        # peer closing connection
                        print(f"closing {sock}")
                        peer_ = self.peers_manager.get_peer_by_sock(sock)
                        self.peers_manager.peers.remove(peer_)
                        reads.remove(sock)

                        # Remove block requests sent to closed peer
                        for piece in self.pieces.piece_list:
                            if piece.finished:
                                continue
                            
                            for block in piece.block_list:
                                if block.gathered == False and block.sent_to != None and block.sent_to.peer_id == peer_.peer_id:
                                    block.sent_to = None
                                    self.num_requests -= 1

                        sock.close()

            time1 = time.time()
            keep_alive_timeout -= time1 - time0
            tracker_timeout -= time1 - time0
            if keep_alive_timeout < 0:
                keep_alive_timeout = 0
            if tracker_timeout < 0:
                tracker_timeout = 0
            

            for sock in e:
                print(f"if you're seeing this, idk man the socket machine broke on {sock.getpeername()}")
                reads.remove(sock)
                sock.close()
            
            if not (r or w or e):
                print("timeout")
                time1 = time.time()
                if ka_timedout:
                    # print("ka")
                    # send keep alive to peers
                    # for p in self.peers_manager.peers:
                    #     p.send_keep_alive()
                    ka_timedout = False
                    keep_alive_timeout = 5
                    tracker_timeout -= time1 - time0
                    if tracker_timeout < 0:
                        tracker_timeout = 0
                    # print(f'new tr time: {tracker_timeout}')

                elif tr_timedout:
                    # print("tr")
                    # connect to any new peers from tracker and add to reads
                    self.tracker.get_peer_list()
                    for p in self.tracker.peer_list:
                        print(f'peer from tracker: {p[0]}:{p[1]}')

                        if not self.peers_manager.does_peer_exist(p[0], p[1]):
                            print('peer does not exist, attempting to add to peer list')
                            p_ = self.peers_manager.connect_to_peer((p[0], p[1]), self.tracker.peer_id, self.tracker.info_hash, self.pieces.bitfield)
                            if p_ != -1:
                                reads.append(p_)

                    tr_timedout = False
                    tracker_timeout = self.tracker.interval
                    keep_alive_timeout -= time1 - time0
                    if keep_alive_timeout < 0:
                        keep_alive_timeout = 0
                    # print(f'new ka time: {keep_alive_timeout}')
                
                # take out all the peers we haven't seen in >2min
                for p in self.peers_manager.peers:
                    if time1 - p.last_seen > 120:
                        self.peers_manager.peers.remove(p)
                        reads.remove(p.sock)
                        p.sock.close()

        # the file has been completely obtained from peers
        print("file all downloaded!")
        self.tracker.get_peer_list(3)

        # disconnect from peers - i dont think we should stay to become a seeder, right?
        for s in reads:
            s.close()
        
        print("done.")
        

if __name__ == '__main__':
    # Check correct number of args
    if len(sys.argv) < 2 or len(sys.argv) > 5:
        print(f'Wrong number of args: {len(sys.argv)}')
        print('To run: client.py <path to torrent> <compact format (0 or 1)> <port (optional)> <file to seed (optional)>')
        exit()

    # Check compact is safe
    if (not sys.argv[2].isdigit()) or (int(sys.argv[2]) not in [0, 1]):
        print('compact must be 0 (off) or 1 (on)')
        print('To run: client.py <path to torrent> <compact format (0 or 1)> <port (optional)> <seed (0 or 1)(default 0)>')
        exit()

    if len(sys.argv) == 3:
        # running client normally
        client = Client(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 4:
        # run client on specific port
        client = Client(sys.argv[1], sys.argv[2], int(sys.argv[3]))
    else:
        # run client as seeder (port must be specified)
        client = Client(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))

    client.run()
