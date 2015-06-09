#!/usr/bin/python2

import math
import multiprocessing
import os
import platform
import socket
import sys
import signal
import threading
import traceback
import time

from pumpkinlb.config import PumpkinConfig, PumpkinMapping
from pumpkinlb.usage import printUsage, printConfigHelp
from pumpkinlb.listener import PumpkinListener

if __name__ == '__main__':

    configFilename = None
    for arg in sys.argv[1:]:
        if arg == '--help':
            printUsage(sys.stdout)
            sys.exit(0)
        elif arg == '--help-config':
            printConfigHelp(sys.stdout)
            sys.exit(0)
        elif configFilename is not None:
            sys.stderr.write('Too many arguments.\n\n')
            printUsage(sys.stderr)
            sys.exit(0)
        else:
            configFilename = arg

    if not configFilename:
        sys.stderr.write('No config file provided\n\n')
        printUsage(sys.stderr)
        sys.exit(1)

    pumpkinConfig = PumpkinConfig(configFilename)
    try:
        pumpkinConfig.parse()
    except:
        traceback.print_exc(file=sys.stderr)
        printConfigHelp(sys.stderr)
        sys.exit(1)

    mappings = pumpkinConfig.getMappings()
    listeners = []
    for mappingAddr, mapping in mappings.iteritems():
        listenerArgs = mapping.getListenerArgs()
        sys.stdout.write('Starting up listener: ' + str(listenerArgs) + '\n')
        listener = PumpkinListener(*listenerArgs)
        listener.start()
        listeners.append(listener)


    globalIsTerminating = False

    def handleSigTerm(*args):
        global listeners
        global globalIsTerminating
        sys.stderr.write('CALLED\n')
        if globalIsTerminating is True:
            return # Already terminating
        globalIsTerminating = True
        sys.stdout.write('Caught signal, shutting down listeners...\n')
        for listener in listeners:
            try:
                os.kill(listener.pid, signal.SIGTERM)
            except:
                pass
        sys.stderr.write('Sent signal to children, waiting up to 4 seconds then trying to clean up\n')
        time.sleep(1)
        startTime = time.time()
        remainingListeners = listeners
        remainingListeners2 = []
        for listener in remainingListeners:
            sys.stderr.write('Waiting on %d...\n' %(listener.pid,))
            sys.stderr.flush()
            listener.join(.05)
            if listener.is_alive() is True:
                remainingListeners2.append(listener)
        remainingListeners = remainingListeners2
        sys.stderr.write('Remaining (%d) listeners are: %s\n' %(len(remainingListeners), [listener.pid for listener in remainingListeners]))
        sys.stderr.flush()

        afterJoinTime = time.time()

        if remainingListeners:
            delta = afterJoinTime - startTime
            remainingSleep = int(6 - math.floor(afterJoinTime - startTime))
            if remainingSleep > 0:
                anyAlive = False
                # If we still have time left, see if we are just done or if there are children to clean up using remaining time allotment
                if threading.activeCount() > 1 or len(multiprocessing.active_children()) > 0:
                    sys.stderr.write('Listener closed in %1.2f seconds. Waiting up to %d seconds before terminating.\n' %(delta, remainingSleep))
                    sys.stderr.flush()
                    thisThread = threading.current_thread()
                    for i in range(remainingSleep):
                        allThreads = threading.enumerate()
                        anyAlive = False
                        for thread in allThreads:
                            if thread is thisThread or thread.name == 'MainThread':
                                continue
                            thread.join(.05)
                            if thread.is_alive() == True:
                                anyAlive = True

                        allChildren = multiprocessing.active_children()
                        for child in allChildren:
                            child.join(.05)
                            if child.is_alive() == True:
                                anyAlive = True
                        if anyAlive is False:
                            break
                        time.sleep(1)

                if anyAlive is True:
                    sys.stderr.write('Could not kill in time.\n')
                else:
                    sys.stderr.write('Shutdown successful after %1.2f seconds.\n' %( time.time() - startTime))
                sys.stderr.flush()
                    
            else:
                sys.stderr.write('Listener timed out in closing, exiting uncleanly.\n')
                sys.stderr.flush()
                time.sleep(.05) # Why not? :P

        sys.stdout.write('exiting...\n')
        sys.stdout.flush()
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        sys.exit(0)
        os.kill(os.getpid(), signal.SIGTERM)
        return 0
    # END handleSigTerm
        

    signal.signal(signal.SIGTERM, handleSigTerm)
    signal.signal(signal.SIGINT, handleSigTerm)

    while True:
        try:
            time.sleep(2)
        except:
            os.kill(os.getpid(), signal.SIGTERM)

# vim: set ts=4 sw=4 expandtab
