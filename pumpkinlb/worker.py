# PumpkinLB Copyright (c) 2014-2015 Tim Savannah under GPLv3.
# You should have received a copy of the license as LICENSE 
#
# See: https://github.com/kata198/PumpkinLB

import multiprocessing
import select
import signal
import socket
import sys
import time

from .constants import GRACEFUL_SHUTDOWN_TIME, DEFAULT_BUFFER_SIZE
from .log import logmsg, logerr

class PumpkinWorker(multiprocessing.Process):
    '''
        A class which handles the worker-side of processing a request (communicating between the back-end worker and the requesting client)
    '''

    def __init__(self, clientSocket, clientAddr, workerAddr, workerPort, bufferSize=DEFAULT_BUFFER_SIZE):
        multiprocessing.Process.__init__(self)

        self.clientSocket = clientSocket
        self.clientAddr = clientAddr
        
        self.workerAddr = workerAddr
        self.workerPort = workerPort

        self.workerSocket = None

        self.bufferSize = bufferSize


        self.failedToConnect = multiprocessing.Value('i', 0)

    def closeConnections(self):
        try:
            self.workerSocket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            self.workerSocket.close()
        except:
            pass
        try:
            self.clientSocket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            self.clientSocket.close()
        except:
            pass
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

    def closeConnectionsAndExit(self, *args):
        self.closeConnections()
        sys.exit(0)

    def run(self):
        workerSocket = self.workerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        clientSocket = self.clientSocket

        bufferSize = self.bufferSize

        try:
            workerSocket.connect( (self.workerAddr, self.workerPort) )
        except:
            logerr('Could not connect to worker %s:%d\n' %(self.workerAddr, self.workerPort))
            self.failedToConnect.value = 1
            time.sleep(GRACEFUL_SHUTDOWN_TIME) # Give a few seconds for the "fail" reader to pick this guy up before we are removed by the joining thread
            return

        signal.signal(signal.SIGTERM, self.closeConnectionsAndExit)

        try:
            dataToClient = ''
            dataFromClient = ''
            while True:
                waitingToWrite = []

                if dataToClient:
                    waitingToWrite.append(clientSocket)
                if dataFromClient:
                    waitingToWrite.append(workerSocket)
                

                (hasDataForRead, readyForWrite, hasError) = select.select( [clientSocket, workerSocket], waitingToWrite, [clientSocket, workerSocket], .3)

                if hasError:
                    break
            
                if clientSocket in hasDataForRead:
                    nextData = clientSocket.recv(bufferSize)
                    if not nextData:
                        break
                    dataFromClient += nextData

                if workerSocket in hasDataForRead:
                    nextData = workerSocket.recv(bufferSize)
                    if not nextData:
                        break
                    dataToClient += nextData
            
                if workerSocket in readyForWrite:
                    while dataFromClient:
                        workerSocket.send(dataFromClient[:bufferSize])
                        dataFromClient = dataFromClient[bufferSize:]

                if clientSocket in readyForWrite:
                    while dataToClient:
                        clientSocket.send(dataToClient[:bufferSize])
                        dataToClient = dataToClient[bufferSize:]

        except Exception as e:
            logerr('Error on %s:%d: %s\n' %(self.workerAddr, self.workerPort, str(e)))

        self.closeConnectionsAndExit()

