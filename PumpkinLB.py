#!/usr/bin/python2

import os
import multiprocessing
import platform
import socket
import sys
import signal
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
        remainingListeners = listeners
        for i in xrange(3):
            remainingListeners2 = []
            for listener in remainingListeners:
                sys.stderr.write('Waiting on %d...\n' %(listener.pid,))
                sys.stderr.flush()
                listener.join(.005)
                if listener.is_alive() is True:
                    remainingListeners2.append(listener)
            remainingListeners = remainingListeners2
            sys.stderr.write('Remaining (%d) listeners are: %s\n' %(len(remainingListeners), [listener.pid for listener in remainingListeners]))
            sys.stderr.flush()
            if len(remainingListeners) == 0:
                break
            time.sleep(1)

        if len(remainingListeners) > 0:
            sys.stderr.write('After trying to clean up, %d listeners remain.\n' %(len(remainingListeners)))
            for listener in remainingListeners:
                try:
                    os.kill(listener.pid, signal.SIGKILL)
                except:
                    pass
            time.sleep(.1)
            sys.stderr.write('Starting final join\n')
            sys.stderr.flush()
            for listener in remainingListeners:
                listener.join()
            sys.stderr.write('Done\n')
            sys.stderr.flush()
         
        if '_NT' in platform.system():
            # Some issue on windows, or at least cygwin on windows, causes an infinite loop in this signal handler when trying to kill the process. CThe only way out is to cause an exception between here and the next call, so provide a function with invalid arguments.
            sys.stderr.write('You can ignore the below exception, it is used to quit on NT\n')
            signal.signal(signal.SIGTERM, sys.exit)
            signal.signal(signal.SIGINT, sys.exit)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handleSigTerm)
    signal.signal(signal.SIGINT, handleSigTerm)

    while True:
        try:
            time.sleep(2)
        except:
            os.kill(os.getpid(), signal.SIGTERM)

    # vim: ts=4 sw=4 expandtab
