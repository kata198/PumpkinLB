# PumpkinLB Copyright (c) 2014-2015, 2017, 2018 Tim Savannah under GPLv3.
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

__all__ = ('PumpkinListener', )

class PumpkinListener(multiprocessing.Process):
    '''
        PumpkinListener - Class that listens on a local port and forwards requests to workers
    '''


    def __init__(self, localAddr, localPort, workers, bufferSize=DEFAULT_BUFFER_SIZE):
        '''
            __init__ - Create this object.

                @param localAddr <str> - Local address on which to bind

                @param localPort <int> - Local port on which to bind

                @param workers list< dict< 'addr' : <str>worker address, 'port' : <int>worker port > > -

                    List of worker infos that are assigned to handle requests to this addr:port

                @param bufferSize <int> - Default constants.DEFAULT_BUFFER_SIZE [4096] - 

                    The buffer size for read/write socket requests.
        '''
        # Setup Process specifics
        multiprocessing.Process.__init__(self)

        # Instance variables
        self.localAddr = localAddr
        self.localPort = localPort
        self.workers = workers
        self.bufferSize = bufferSize

        # list< PumpkinWorker >
        self.activeWorkers = []   # Workers currently processing a job

        self.listenSocket = None  # Socket for incoming connections

        self.cleanupThread = None # Cleans up completed workers

        self.retryThread = None   # Retries failed requests

        self.keepGoing = True     # Flips to False when the application is set to terminate


    def cleanup(self):
        '''
            cleanup - Target of the "cleanup thread" which will run 1:1 with
                this process, and cleanup connections and join completed workers
        '''

        time.sleep(2) # Wait for things to kick off

        while self.keepGoing is True:
            # Until the global terminator (#keepGoing) is False,
            #  cleanup any workers that have completed their task
            currentWorkers = self.activeWorkers[:]
            for worker in currentWorkers:
                worker.join(.02)
                if worker.is_alive() == False: # Completed
                    self.activeWorkers.remove(worker)

            if self.keepGoing is True:
                # Instead of a full 1.5s sleep, split into 3 for quicker
                #  termination worse-case time
                time.sleep(.5)
                if self.keepGoing is False:
                    break
                time.sleep(.5)
                if self.keepGoing is False:
                    break
                time.sleep(.5)


    def closeWorkers(self, *args):
        '''
            closeWorkers - Close down the incoming socket,
              cleanup/terminate any active workers, and
              terminate the cleanup thread.

            This also serves as the SIGTERM handler for this listener
        '''
        # Set the loop terminator for all active thread loops
        self.keepGoing = False

        # Wait a second
        time.sleep(1)

        # Shutdown the incoming port
        try:
            self.listenSocket.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            self.listenSocket.close()
        except:
            pass


        if not self.activeWorkers:
            # If no active workers, close the cleanup thread, restore SIGTERM
            #  to default, and send SystemExit to this process
            self.cleanupThread and self.cleanupThread.join(3)
            self.retryThread and self.retryThread.join(3)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            sys.exit(0)


        # Otherwise, send SIGTERM to each of the PumpkinWorker instances
        #  that are active.
        for pumpkinWorker in self.activeWorkers:
            try:
                pumpkinWorker.terminate()
            except:
                pass
            try:
                os.kill(pumpkinWorker.pid, signal.SIGTERM)
            except:
                pass

        # Wait a second
        time.sleep(1)

        # Go through our workers and try to join any that have terminated
        remainingWorkers = []
        for pumpkinWorker in self.activeWorkers:
            pumpkinWorker.join(.05)

            if pumpkinWorker.is_alive() is True:
                # Worker is still running
                remainingWorkers.append(pumpkinWorker)

        # If we didn't cleanup all workers:
        if len(remainingWorkers) > 0:
            # One last chance to complete, then we kill
            time.sleep(1)

            for pumpkinWorker in remainingWorkers:
                pumpkinWorker.join(.2)

                # If join failed, send it the kill switch
                if pumpkinWorker.is_alive() is True:

                    try:
                        pumpkinWorker.kill()
                    except:
                        pass
                    try:
                        os.kill(pumpkinWorker.pid, signal.SIGKILL)
                    except:
                        pass

                    try:
                        pumpkinWorker.join(.2)
                    except:
                        pass


        # Give cleanup thread 2 more seconds to finish up and join
        self.cleanupThread and self.cleanupThread.join(2)
        self.retryThread and self.retryThread.join(2)

        # Restore default SIGTERM handler
        signal.signal(signal.SIGTERM, signal.SIG_DFL)

        # Post that SystemExit
        sys.exit(0)


    def retryFailedWorkers(self, *args):
        '''
            retryFailedWorkers - 

                This function loops over current running workers and scans them for a multiprocess shared field called "failedToConnect".
                  If this is set to 1, then we failed to connect to the backend worker. If that happens, we pick a different worker from the pool at random,
                  and assign the client to that new worker.

                Target of the "retry thread"
        '''


        time.sleep(2)
        successfulRuns = 0 # We use this to differ between long waits in between successful periods and short waits when there is a failing host in the mix.


        while self.keepGoing is True:

            # Iterate over all active workers
            currentWorkers = self.activeWorkers[:]
            for worker in currentWorkers:

                # Check if we failed to connect
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

                    # Start up a new worker based on the old worker, and add to the active list
                    nextWorker = PumpkinWorker(worker.clientSocket, worker.clientAddr, nextWorkerInfo['addr'], nextWorkerInfo['port'], self.bufferSize)
                    nextWorker.start()
                    self.activeWorkers.append(nextWorker)

                    worker.failedToConnect.value = 0 # Clean now

            # Check the terminator
            if self.keepGoing is False:
                break

            # Depending on how many successes we've had in a row
            #   determines how long we wait before checking for failure again
            successfulRuns += 1
            if successfulRuns > 1000000: # Make sure we don't overrun
                successfulRuns = 6

            if successfulRuns > 5:
                # 2 total seconds of sleep, with checks every .5
                #   for global terminator
                time.sleep(.5)
                if self.keepGoing is False:
                    break
                time.sleep(.5)
                if self.keepGoing is False:
                    break
                time.sleep(.5)
                if self.keepGoing is False:
                    break
                time.sleep(.5)

            else:
                # Under 5 successes in a row, short-sleep to expect retry
                time.sleep(.1)


    def run(self):
        '''
            run - process start point
        '''

        # Setup signal handler on this process to call closeWorkers

        self.keepGoing = True
        signal.signal(signal.SIGTERM, self.closeWorkers)

        # Loop until we can bind to the socket, or terminator is set
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

                # Successful bind, exit loop
                break
            except Exception as e:
                logerr('Failed to bind to %s:%d. "%s" Retrying in 5 seconds.\n' %(self.localAddr, self.localPort, str(e)))

                # Sleep in 1-second intervals for up to 5 seconds,
                #   unless we terminate
                for i in range(5):
                    time.sleep(1)
                    if self.keepGoing is False:
                        return

        # Max listen backlog (5 connections)
        listenSocket.listen(5)

        # Create thread that will cleanup completed tasks
        self.cleanupThread = cleanupThread = threading.Thread(target=self.cleanup)
        cleanupThread.start()

        # Create thread that will retry failed tasks
        self.retryThread = retryThread = threading.Thread(target=self.retryFailedWorkers)
        retryThread.start()


        logmsg('Successful bind to %s:%d. Awaiting connections...\n' %( self.localAddr, self.localPort ) )

        try:
            # Run until terminator is set
            while self.keepGoing is True:

                # Round-robin circle the workers
                for workerInfo in self.workers:

                    if self.keepGoing is False:
                        break

                    try:
                        # Wait here until we have an incoming connection
                        (clientConnection, clientAddr) = listenSocket.accept()
                    except:
                        logerr('Cannot bind to %s:%s\n' %(self.localAddr, self.localPort))
                        if self.keepGoing is True:
                            # Exception did not come from termination process, so keep rollin'
                            time.sleep(1)
                            if self.keepGoing is False:
                                break
                            time.sleep(1)
                            if self.keepGoing is False:
                                break
                            time.sleep(1)
                            if self.keepGoing is False:
                                break

                            continue

                        raise # Termination DID come from termination process, so abort.

                    # Got successful incoming connection, pass off to a worker
                    worker = PumpkinWorker(clientConnection, clientAddr, workerInfo['addr'], workerInfo['port'], self.bufferSize)
                    worker.start()
                    self.activeWorkers.append(worker)

        except Exception as e:
            logerr('Got exception: %s, shutting down workers on %s:%d\n' %(str(e), self.localAddr, self.localPort))
            self.closeWorkers()
            return

        # Shut it down if not already shut down
        self.closeWorkers()


# vim: set ts=4 sw=4 st=4 expandtab :
