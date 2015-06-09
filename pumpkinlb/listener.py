import multiprocessing
import os
import random
import socket
import sys
import signal
import time
import threading

from .worker import PumpkinWorker



class PumpkinListener(multiprocessing.Process):
    '''
        Class that listens on a local port and forwards requests to workers
    '''


    def __init__(self, localAddr, localPort, workers):
        multiprocessing.Process.__init__(self)
        self.localAddr = localAddr
        self.localPort = localPort
        self.workers = workers

        self.pumpkinWorkers = []

        self.listenSocket = None

        self.cleanupThread = None

        self.keepGoing = True

    def cleanup(self):
        time.sleep(2) # Wait for things to kick off
        while self.keepGoing is True:
            currentWorkers = self.pumpkinWorkers[:]
            for worker in currentWorkers:
                worker.join(.02)
                if worker.is_alive() == False:
                    self.pumpkinWorkers.remove(worker)
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

        if not self.pumpkinWorkers:
            self.cleanupThread and self.cleanupThread.join(3)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            sys.exit(0)

        for pumpkinWorker in self.pumpkinWorkers:
            try:
                pumpkinWorker.terminate()
                os.kill(pumpkinWorker.pid, signal.SIGTERM)
            except:
                pass

        time.sleep(1)


        remainingWorkers = []
        for pumpkinWorker in self.pumpkinWorkers:
            pumpkinWorker.join(.03)
            if pumpkinWorker.is_alive() is True:
                remainingWorkers.append(pumpkinWorker)

        if len(remainingWorkers) > 0:
            time.sleep(1)
            for pumpkinWorker in remainingWorkers:
                pumpkinWorker.join(.2)

        self.cleanupThread and self.cleanupThread.join(2)

        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        sys.exit(0)

    def retryFailedWorkers(self, *args):
        time.sleep(2)
        successfulRuns = 0 # We use this to differ between long waits in between successful periods and short waits when there is a failing host in the mix.
        while self.keepGoing is True:
            currentWorkers = self.pumpkinWorkers[:]
            for worker in currentWorkers:
                if worker.failedToConnect.value == 1:
                    successfulRuns = -1
                    sys.stdout.write('Found a failure to connect to worker\n')
                    sys.stdout.flush()
                    numWorkers = len(self.workers)
                    nextWorkerInfo = None
                    while (nextWorkerInfo is None) or (worker.workerAddr == nextWorkerInfo['addr'] and worker.workerPort == nextWorkerInfo['port']):
                        nextWorkerInfo = self.workers[random.randint(0, numWorkers-1)]
                    sys.stdout.write('Retrying request from %s from %s:%d on %s:%d\n' %(worker.clientAddr, worker.workerAddr, worker.workerPort, nextWorkerInfo['addr'], nextWorkerInfo['port']))
                    sys.stdout.flush()
                    nextWorker = PumpkinWorker(worker.clientSocket, worker.clientAddr, nextWorkerInfo['addr'], nextWorkerInfo['port'])
                    nextWorker.start()
                    self.pumpkinWorkers.append(nextWorker)
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
                listenSocket.bind( (self.localAddr, self.localPort) )
                self.listenSocket = listenSocket
                break
            except Exception as e:
                sys.stderr.write('Failed to bind to %s:%d. "%s" Retrying in 5 seconds.\n' %(self.localAddr, self.localPort, str(e)))
                time.sleep(5)

        listenSocket.listen(5)

        self.cleanupThread = cleanupThread = threading.Thread(target=self.cleanup)
        cleanupThread.start()
        if len(self.workers) > 1:
            retryThread = threading.Thread(target=self.retryFailedWorkers)
            retryThread.start()

        try:
            while True:
                for workerInfo in self.workers:
                    if self.keepGoing is False:
                        break
                    try:
                        (clientConnection, clientAddr) = listenSocket.accept()
                    except:
                        sys.stderr.write('Cannot bind to %s:%s\n' %(self.localAddr, self.localPort))
                        if self.keepGoing is True:
                            time.sleep(3)
                            continue
                        
                        raise
                    worker = PumpkinWorker(clientConnection, clientAddr, workerInfo['addr'], workerInfo['port'])
                    self.pumpkinWorkers.append(worker)
                    worker.start()
        except Exception as e:
            sys.stderr.write('Got exception: %s, shutting down worker on %s:%d\n' %(str(e), self.localAddr, self.localPort))
            self.closeWorkers()
            return


        self.closeWorkers()

 
