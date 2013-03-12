#!/usr/bin/python

import subprocess
from pprint import pprint
import time
import socket

CARBON_SERVER = '0.0.0.0'
CARBON_PORT = 2003

def send_msg(message):
    #print 'sending message: %s' % message
    sock = socket.socket()
    sock.connect((CARBON_SERVER, CARBON_PORT))
    sock.sendall(message)
    sock.close()

while True:
	directors = subprocess.Popen(["symstat","-type","PORT","-dir","ALL","-i","10","-c","1"],stdout=subprocess.PIPE)
	for line in directors.stdout:
		if len(line) > 1 and "FA" in line:
			current = line.strip().rsplit(None,4)
			current.pop(0)
			timestamp = int(time.time())
			lines = [
				'Symmetrix.Director.%s.Port.%s.IOPs %d %d' % (current[0], current[1], float(current[2]), timestamp),
				'Symmetrix.Director.%s.Port.%s.KBsec %d %d' % (current[0], current[1], float(current[3]), timestamp),
			]
			#print lines
			message = '\n'.join(lines) + '\n'
			send_msg(message)
