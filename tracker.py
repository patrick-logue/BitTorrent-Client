import bencoder
import socket
import random
import string
import struct
import math
from urllib.parse import urlparse, quote
from hashlib import sha1

# Tracker class holds the torrent info for use in its GET request
class Tracker():
    def __init__(self, torrent, compact, port):
        self.port = port
        # Parse metadata in the .torrent file
        torrent = parse_torrent(torrent)

        # Metadata
        self.torrent_announce = torrent[b'announce']
        self.torrent_announce_list = torrent[b'announce-list'] if b'announce-list' in torrent else []
        self.torrent_created_by = torrent[b'created by'] if b'created by' in torrent else ''
        self.torrent_creation_date = torrent[b'creation date'] if b'creation date' in torrent else 0
        self.torrent_encoding = torrent[b'encoding'] if b'encoding' in torrent else ''
        # Keys in the Info dict
        self.torrent_name = torrent[b'info'][b'name']
        self.torrent_length = torrent[b'info'][b'length']
        self.torrent_piece_length = torrent[b'info'][b'piece length']
        self.torrent_pieces_hash = torrent[b'info'][b'pieces']
        print(self.torrent_piece_length)
        self.torrent_num_pieces = math.ceil(self.torrent_length / self.torrent_piece_length)
        # Optional key in Info dict
        self.torrent_private = torrent[b'info'][b'private'] if b'private' in torrent[b'info'] else 0
        # info_hash to send to tracker
        torrent_info = bencoder.encode(torrent[b'info'])
        self.info_hash = sha1(torrent_info).digest()
        # unique peer_id to send to tracker
        r = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        self.peer_id = f'-PB0417-{r}'
        # compact format
        self.compact = int(compact)

        # Interval in seconds that the client should wait between sending regular requests to the tracker
        self.interval = 900

        self.peer_list = []
        self.get_peer_list(1)

    # Announce presence as peer and retrieve list of peers
    def get_peer_list(self, event=0):
        host = urlparse(self.torrent_announce)
        path = host.path.decode('utf8')
        netloc = host.netloc.decode('utf8')
        info_hash = quote(self.info_hash)

        if event == 1:
            ev = "started"
        elif event == 2:
            ev = "stopped"
        elif event == 3:
            ev = "completed"
        else:
            ev = "" # interval check-in

        # Ports reserved for BT are 6881-6889. try all of them if necessary?
        data = (f'GET {path}?info_hash={info_hash}&peer_id={self.peer_id}&port={self.port}'
                f'&uploaded=0&downloaded=0&left={self.torrent_length}&compact={self.compact}'
                f'&event={ev} HTTP/1.1\r\nHost: {netloc}\r\n\r\n')

        resp = send_http_req(data, host.hostname.decode('utf-8'), host.port)
        resp = bencoder.decode(resp[-1])
        
        self.interval = resp[b'interval']

        if self.compact == 1:
            self.peer_list = [(socket.inet_ntoa(resp[b'peers'][i:i+4]), 
                               struct.unpack('>H',resp[b'peers'][i+4:i+6])[0]) 
                               for i in range(0, len(resp[b'peers']), 6)]
        else:
            self.peer_list = [(resp[b'peers'][i][b'ip'].decode(), resp[b'peers'][i][b'port'],
                               resp[b'peers'][i][b'peer id'].decode()) for i in range(0, len(resp[b'peers']))]

# Open and parse torrent file 
def parse_torrent(torrent):
    try:
        f = open(torrent,'rb')
    except IOError as err: 
        print(err)
        print('To run: client.py <path to torrent> <compact format (0 or 1)>')
        exit()
    else:
        contents = bencoder.decode(f.read())
        # error check for bad bencoded files?
        return contents

# General http request function (closes socket). Returns a list of HTTP headers and contents
def send_http_req(data, hostname, port):
    # loop through announce list or just use announce?
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, port))
    s.sendall(data.encode())

    # Receive data into list since byte strings are immutable
    buffer = []
    while True:
        data = s.recv(4096)
        if not data:
            break
        buffer.append(data)

    s.close()
    
    # Join all response data into one
    response = b''.join(buffer)
    # Split HTML on CRLF
    resp_split = response.split(b'\r\n')
    if resp_split[0].find(b'20') == -1:
        print(f'GET request failed {resp_split[0]}')
        exit()

    return resp_split
