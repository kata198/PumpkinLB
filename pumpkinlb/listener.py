# PumpkinLB Copyright (c) 2014-2015, 2017 Tim Savannah under GPLv3.
# You should have received a copy of the license as LICENSE 
#
# See: https://github.com/kata198/PumpkinLB

import multiprocessing
import os
import random
import socket
import sys
import signal
import time
import threading

from .log import logmsg, logerr
from .worker import PumpkinWorker
from .constants import DEFAULT_BUFFER_SIZE


class PumpkinListener(multiprocessing.Process):
    '''
        Class that listens on a local port and forwards requests to workers
    '''


    def __init__(self, localAddr, localPort, workers, bufferSize=DEFAULT_BUFFER_SIZE):
        multiprocessing.Process.__init__(self)
        self.localAddr = localAddr
        self.localPort = localPort
        self.workers = workers
        self.bufferSize = bufferSize

        self.activeWorkers = []   # Workers currently processing a job

        self.listenSocket = None  # Socket for incoming connections

        self.cleanupThread = None # Cleans up completed workers

        self.keepGoing = True     # Flips to False when the application is set to terminate

    def cleanup(self):
        time.sleep(2) # Wait for things to kick off
        while self.keepGoing is True:
            currentWorkers = self.activeWorkers[:]
            for worker in currentWorkers:
                worker.join(.02)
                if worker.is_alive() == False: # Completed
                    self.activeWorkers.remove(worker)
            time.sleep(1.5)

    def closeWorkers(self, *args):
        self.keepGoing = False

        time.sleep(1)

        try:
            self.listenSocket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            self.listenSocket.close()
        except:
            pass

        if not self.activeWorkers:
            self.cleanupThread and self.cleanupThread.join(3)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            sys.exit(0)

        for pumpkinWorker in self.activeWorkers:
            try:
                pumpkinWorker.terminate()
                os.kill(pumpkinWorker.pid, signal.SIGTERM)
            except:
                pass

        time.sleep(1)


        remainingWorkers = []
        for pumpkinWorker in self.activeWorkers:
            pumpkinWorker.join(.03)
            if pumpkinWorker.is_alive() is True: # Still running
                remainingWorkers.append(pumpkinWorker)

        if len(remainingWorkers) > 0:
            # One last chance to complete, then we kill
            time.sleep(1)
            for pumpkinWorker in remainingWorkers:
                pumpkinWorker.join(.2)

        self.cleanupThread and self.cleanupThread.join(2)

        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        sys.exit(0)

    def retryFailedWorkers(self, *args):
        '''
            retryFailedWorkers - 

                This function loops over current running workers and scans them for a multiprocess shared field called "failedToConnect".
                  If this is set to 1, then we failed to connect to the backend worker. If that happens, we pick a different worker from the pool at random,
                  and assign the client to that new worker.
        '''


        time.sleep(2)
        successfulRuns = 0 # We use this to differ between long waits in between successful periods and short waits when there is a failing host in the mix.
        while self.keepGoing is True:
            currentWorkers = self.activeWorkers[:]
            for worker in currentWorkers:
                if worker.failedToConnect.value == 1:
                    successfulRuns = -1 # Reset the "roll" of successful runs so we start doing shorter sleeps
                    logmsg('Found a failure to connect to worker\n')
                    numWorkers = len(self.workers)
                    if numWorkers > 1:
                        nextWorkerInfo = None
                        while (nextWorkerInfo is None) or (worker.workerAddr == nextWorkerInfo['addr'] and worker.workerPort == nextWorkerInfo['port']):
                            nextWorkerInfo = self.workers[random.randint(0, numWorkers-1)]
                    else:
                        # In this case, we have no option but to try on the same host.
                        nextWorkerInfo = self.workers[0]

                    logmsg('Retrying request from %s from %s:%d on %s:%d\n' %(worker.clientAddr, worker.workerAddr, worker.workerPort, nextWorkerInfo['addr'], nextWorkerInfo['port']))

                    nextWorker = PumpkinWorker(worker.clientSocket, worker.clientAddr, nextWorkerInfo['addr'], nextWorkerInfo['port'], self.bufferSize)
                    nextWorker.start()
                    self.activeWorkers.append(nextWorker)
                    worker.failedToConnect.value = 0 # Clean now
            successfulRuns += 1
            if successfulRuns > 1000000: # Make sure we don't overrun
                successfulRuns = 6
            if successfulRuns > 5:
                time.sleep(2)
            else:
                time.sleep(.05)
                    
        

    def run(self):
        signal.signal(signal.SIGTERM, self.closeWorkers)

        while True:
            try:
                listenSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                # If on UNIX, bind to port even if connections are still in TIME_WAIT state
                #  (from previous connections, which don't ever be served...)
                # Happens when PumpkinLB Restarts.
                try:
                    listenSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                except:
                    pass
                listenSocket.bind( (self.localAddr, self.localPort) )
                self.listenSocket = listenSocket
                break
            except Exception as e:
                logerr('Failed to bind to %s:%d. "%s" Retrying in 5 seconds.\n' %(self.localAddr, self.localPort, str(e)))
                time.sleep(5)

        listenSocket.listen(5)

        # Create thread that will cleanup completed tasks
        self.cleanupThread = cleanupThread = threading.Thread(target=self.cleanup)
        cleanupThread.start()

        # Create thread that will retry failed tasks
        retryThread = threading.Thread(target=self.retryFailedWorkers)
        retryThread.start()

        try:
            while self.keepGoing is True:
                for workerInfo in self.workers:
                    if self.keepGoing is False:
                        break
                    try:
                        (clientConnection, clientAddr) = listenSocket.accept()
                    except:
                        logerr('Cannot bind to %s:%s\n' %(self.localAddr, self.localPort))
                        if self.keepGoing is True:
                            # Exception did not come from termination process, so keep rollin'
                            time.sleep(3)
                            continue
                        
                        raise # Termination DID come from termination process, so abort.

                    worker = PumpkinWorker(clientConnection, clientAddr, workerInfo['addr'], workerInfo['port'], self.bufferSize)
                    self.activeWorkers.append(worker)
                    worker.start()
        except Exception as e:
            logerr('Got exception: %s, shutting down workers on %s:%d\n' %(str(e), self.localAddr, self.localPort))
            self.closeWorkers()
            return


        self.closeWorkers()

 
