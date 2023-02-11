# Python BitTorrent Client

A CLI tool for downloading and seeding files using the BitTorrent protocol.

Written from scratch in Python 3.8.

### Installation
pip install bitarray

### Usage
Run: “python3 ./client \<path to torrent file> \<compact> \<port> \<seed>”

* Path to torrent file is the local path to a .torrent file.

* Compact is either 0 (not compact) or 1 (compact formatted when communicating with the tracker). 

* Port is the port number to listen on.

* Seed is 0 (do not seed) or 1 (seed).

Example: `python3 ./client.py ./debian-11.5.0-amd64-netinst.iso.torrent 1 6881 0`
