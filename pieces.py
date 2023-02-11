import time
import math
import os
from hashlib import sha1
from typing import List
from bitarray import bitarray

BLOCK_LEN = 2**14

class Block():
    def __init__(self, index, begin, length, gathered = False, data = b'', send_to = None) -> None:
        self.index = index
        self.begin = begin
        self.data = data
        self.length = length
        self.gathered = gathered
        self.sent_to = send_to
        self.time = 0

    
    def __str__(self) -> str:
        return f'Piece {self.index}: Block offset {self.begin} and Block length {self.length}'

class Piece():
    def __init__(self, index, length, hash) -> None:
        self.index = index
        self.length = length
        self.hash = hash
        self.num_blocks = math.ceil(length / BLOCK_LEN)
        self.block_list = self.build_block_list()
        self.data = bytearray(length)
        self.finished = False
    
    def __str__(self) -> str:
        return f'Piece {self.index}: len={self.length}, hash={self.hash}'

    def build_block_list(self) -> List[Block]:
        block_list = []
        for i in range(self.num_blocks - 1):
            block_list.append(Block(self.index, i*BLOCK_LEN, BLOCK_LEN))

        final_block_offset = ((self.num_blocks-1)*BLOCK_LEN)

        block_list.append(Block(self.index, final_block_offset, self.length - final_block_offset))
        return block_list

    def is_complete(self):
        for block in self.block_list:
            if not block.gathered:
                return False

        self.finished = True
        return True
    
    def checkHash(self):
        if not self.finished:
            print('missing data')
            return False
        
        return self.hash == sha1(self.data).digest()

    def reset(self):
        self.block_list = self.build_block_list()
        self.data = bytearray(self.length)
        self.finished = False

        


class FileDownloader():
    def __init__(self, filename, file_len, piece_len, pieces, num_pieces) -> None:
        self.filename = filename
        self.filesize = file_len
        self.num_pieces = num_pieces
        self.piece_len = piece_len
        self.final_piece_len = file_len - ((num_pieces - 1) * piece_len)
        self.bitfield = bitarray(num_pieces if num_pieces%8==0 else num_pieces+(8-(num_pieces%8)))
        self.bitfield.setall(0)
        self.piecehash = self.cutPieceHash(pieces)
        self.piece_list = self.build_piece_list()
    
    def __str__(self) -> str:
        return f"FileDownloader for {self.filename}:[{self.piecehash}]"

    def is_completed(self):
        # Use all() ?
        for i in range(self.num_pieces):
            if not self.bitfield[i]:
                return False
        return True

    def update_block(self, recv_block: Block):
        piece = self.piece_list[recv_block.index]
        old_block = piece.block_list[int(recv_block.begin / BLOCK_LEN)]
        if old_block.length == recv_block.length:
            piece.data[recv_block.begin:recv_block.begin+recv_block.length] = recv_block.data
            piece.block_list[int(recv_block.begin / BLOCK_LEN)] = recv_block
        else:
            print('block lengths not equal')
            
    def cutPieceHash(self, pieces):
        hashList = []
        offset = 0
        while offset<len(pieces):
            #SHA1 always returns 20 byte result
            hashList.append(pieces[offset:offset+20])
            offset+=20
        
        return hashList

    def build_piece_list(self) -> List[Piece]:
        piece_list = []
        for i in range(self.num_pieces - 1):
            piece_list.append(Piece(i,self.piece_len, self.piecehash[i]))
        
        piece_list.append(Piece(self.num_pieces-1, self.final_piece_len, self.piecehash[self.num_pieces-1]))
        
        return piece_list
    

    def update_bitfield(self, piece_index):
        piece = self.piece_list[piece_index]
        if piece.finished:
            self.bitfield[piece_index] = 1
            print(f'Updated bitfield: {self.bitfield}')
            return True
        else:
            print('Piece not complete')
            return False

    def write_piece_to_file(self, piece_index):
        piece = self.piece_list[piece_index]
       
        if not os.path.isfile(self.filename):
            f = open(self.filename, 'wb')

        else:
            f = open(self.filename, 'r+b')
        
        f.seek(piece_index*self.piece_len)
        f.write(piece.data)
        f.close()

    def get_rarest_piece(self, peers_manager):
        least_peers = 0
        rare_index = 0
        for piece in self.piece_list:
            if piece.finished:
                continue

            num_peers_at_i = peers_manager.get_num_peers_by_piece(piece.index)
            # print(f"{piece.index}:{num_peers_at_i} ", end="")
            if num_peers_at_i > 0 and (num_peers_at_i < least_peers or least_peers == 0):
                least_peers = num_peers_at_i
                rare_index = piece.index
        
        if least_peers == 0:
            print("no peer has any piece???")
            return None
        return self.piece_list[rare_index]




if __name__ == '__main__':
    s = FileDownloader(b'pg201.txt', 227172, 32768, b"A\xaf\x1bW\xca}]\x01\xc9\xd0\xdf\x87\xdcS\xa2\xb7\x16\xaf\xc0mj\x83\x9e\xabm\xefp\x01\x08v\xbez0ZQYn\xf0#s\x80\xc2\xe9I\xcf,\xa5\xf1\xac\x1c\x1a'\xba\xf8j\x11l\xc0\x8e\x07L\xde\x8f\x0c\x9a\xf4#\x07\xf9=t\x95\xe8\xe0\xe0\x9d\x15\x8f`g\xcf\x8el\xcf\xa8\xa3\xaf\xf9 \x92\x9c\x02\xaa\xbe\xa3\xd5\xa4\x8c\x87B\x04g\xf2;7$~\xb9\x07\r'\xb1\x99A\\v\x95\xc1\xf4\xde\xb5\x08]}\xe86\xbb\x13\xa4\x9c\xbfuC\xaf\xd1\xd2# \xd6:",
                       7)
    for piece in s.piece_list:
        print(piece)