#!/bin/zsh
set -e
cd -- "${0:A:h}"
/usr/bin/python3 server.py --open
