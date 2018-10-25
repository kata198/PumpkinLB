# PumpkinLB Copyright (c) 2014-2015, 2017, 2018 Tim Savannah under GPLv3.
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


__all__ = ( 'PumpkinWorker', )

class PumpkinWorker(multiprocessing.Process):
    '''
        PumpkinWorker - A class which handles the worker-side of processing a request 
          (communicating between the back-end worker and the requesting client)

        Runs as an independent process
    '''

    def __init__(self, clientSocket, clientAddr, workerAddr, workerPort, bufferSize=DEFAULT_BUFFER_SIZE):
        '''
            __init__ - Create this object

                @param clientSocket <socket.socket> - The socket for the client's connection

                @param clientAddr <str> - The address of the client

                @param workerAddr <str> - The address of the worker

                @param workerPort <int> - The port of the worker

                @param bufferSize <int> Default DEFAULT_BUFFER_SIZE [4096] - Buffer size to use for reads/writes
        '''
        # Init the Process
        multiprocessing.Process.__init__(self)

        # Set instance attributes
        self.clientSocket = clientSocket
        self.clientAddr = clientAddr

        self.workerAddr = workerAddr
        self.workerPort = workerPort

        self.bufferSize = bufferSize

        # workerSocket - This will be set to the socket we open to the worker
        self.workerSocket = None

        # failedToConnect - A shared-memory integer, 0 or 1 for whether
        #    connection failed
        self.failedToConnect = multiprocessing.Value('i', 0)

        self.isTerminating = False


    def closeConnections(self):
        '''
            closeConnections - Close connections to the worker and client
        '''

        self.isTerminating = True

        # Close worker socket
        try:
            self.workerSocket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            self.workerSocket.close()
        except:
            pass

        # Close client socket
        try:
            self.clientSocket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            self.clientSocket.close()
        except:
            pass



    def closeConnectionsAndExit(self, *args):
        '''
            closeConnectionsAndExit - Close connections and exit

                This will restore the default SIGTERM handler

                This should be the SIGTERM handler for this process
        '''
        # Close connections
        self.closeConnections()

        # Restore default SIGTERM handler
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        # Exit
        sys.exit(0)


    def run(self):
        '''
            run - process start point
        '''

        self.isTerminating = False

        clientSocket = self.clientSocket
        bufferSize = self.bufferSize

        # Create a socket to the worker
        workerSocket = self.workerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            workerSocket.connect( (self.workerAddr, self.workerPort) )
        except:
            # Failed to connect to the worker
            logerr('Could not connect to worker %s:%d\n' %(self.workerAddr, self.workerPort))

            # Set the retry value
            self.failedToConnect.value = 1
            time.sleep(GRACEFUL_SHUTDOWN_TIME) # Give a few seconds for the "fail" reader to pick this guy up before we are removed by the joining thread
            return


        # Set the SIGTERM handler
        signal.signal(signal.SIGTERM, self.closeConnectionsAndExit)

        try:
            dataToClient = b''
            dataFromClient = b''

            # Loop until socket is closed
            while True:
                waitingToWrite = []

                # If we have data to or from the client, put that socket
                #   into #waitingToWrite array to pass to select
                if dataToClient:
                    waitingToWrite.append(clientSocket)
                if dataFromClient:
                    waitingToWrite.append(workerSocket)


                try:
                    # Determine which sockets are ready for read, write, or are in error
                    (hasDataForRead, readyForWrite, hasError) = select.select( [clientSocket, workerSocket], waitingToWrite, [clientSocket, workerSocket], .3)
                except KeyboardInterrupt:
                    break

                # If any sockets in error, we are done.
                if hasError:
                    break

                # If we have data to read from client, pull in up to #bufferSize
                if clientSocket in hasDataForRead:
                    nextData = clientSocket.recv(bufferSize)
                    if not nextData:
                        break
                    dataFromClient += nextData

                # If we have data to read from worker, pull in up to #bufferSize
                if workerSocket in hasDataForRead:
                    nextData = workerSocket.recv(bufferSize)
                    if not nextData:
                        break
                    dataToClient += nextData

                # If worker socket is ready for write,
                #   send in #bufferSize chunks until done
                if workerSocket in readyForWrite:
                    while dataFromClient:
                        workerSocket.send(dataFromClient[:bufferSize])
                        dataFromClient = dataFromClient[bufferSize:]


                # If client socket is ready for write,
                #   send in #bufferSize chunks until done
                if clientSocket in readyForWrite:
                    while dataToClient:
                        clientSocket.send(dataToClient[:bufferSize])
                        dataToClient = dataToClient[bufferSize:]


        except Exception as e:
            # If we are expecting termination, don't show errors from closing socket
            if not self.isTerminating:
                logerr('Error on %s:%d: %s\n' %(self.workerAddr, self.workerPort, str(e)))

        # Close all connections and exit if hasn't yet been done
        self.closeConnectionsAndExit()

