#!/usr/bin/python
#
# PumpkinLB Copyright (c) 2014-2015, 2017, 2018 Tim Savannah under GPLv3.
# You should have received a copy of the license as LICENSE 
#
# See: https://github.com/kata198/PumpkinLB

import math
import multiprocessing
import os
import sys
import signal
import threading
import traceback
import time

from pumpkinlb import __version__ as pumpkin_version

from pumpkinlb.config import PumpkinConfig, PumpkinMapping, PumpkinConfigException
from pumpkinlb.usage import printUsage, printConfigHelp, getVersionStr
from pumpkinlb.listener import PumpkinListener
from pumpkinlb.constants import GRACEFUL_SHUTDOWN_TIME

from pumpkinlb.log import logmsg, logerr


if __name__ == '__main__':

    # Parse arguments
    configFilename = None
    for arg in sys.argv[1:]:
        if arg == '--help':
            printUsage(sys.stdout)
            sys.exit(0)
        elif arg == '--help-config':
            printConfigHelp(sys.stdout)
            sys.exit(0)
        elif arg == '--version':
            sys.stdout.write(getVersionStr() + '\n')
            sys.exit(0)
        elif configFilename is not None:
            sys.stderr.write('Too many arguments.\n\n')
            printUsage(sys.stderr)
            sys.exit(0)
        else:
            configFilename = arg


    if not configFilename:
        # No config? No Pumpkin!
        sys.stderr.write('No config file provided\n\n')
        printUsage(sys.stderr)
        sys.exit(1)

    # Parse config
    pumpkinConfig = PumpkinConfig(configFilename)
    try:
        pumpkinConfig.parse()
    except PumpkinConfigException as configError:
        # Cannot ignore error (like missing mapping section)
        sys.stderr.write(str(configError) + '\n\n\n')
        printConfigHelp()
        sys.exit(1)
    except IOError as ioe:
        # Catch file not found / invalid permissions on config file
        sys.stderr.write(str(ioe) + '\n\n')
        sys.exit(1)
    except Exception as e:
        # Generic exception in parsing
        traceback.print_exc(file=sys.stderr)
        printConfigHelp(sys.stderr)
        sys.exit(1)

    bufferSize = pumpkinConfig.getOptionValue('buffer_size')
    logmsg('Configured buffer size = %d bytes\n' %(bufferSize,))

    # Grab mappings and startup a listener process for each
    mappings = pumpkinConfig.getMappings()
    listeners = []
    for mappingAddr, pumpkinMapping in mappings.items():
        logmsg('Starting up listener on %s:%d with mappings: %s\n' %(pumpkinMapping.localAddr, pumpkinMapping.localPort, str(pumpkinMapping.workers)))

        listenerArgs = pumpkinMapping.getListenerArgs()

        # Create and start subprocess, add to #listeners array
        #  (which is a global to be referenced in graceful cleanup below)
        listener = PumpkinListener(*listenerArgs, bufferSize=bufferSize)
        listener.start()
        listeners.append(listener)


    # Now that we've forked, setup signal handlers on this (main process)
    #   to do graceful shutdown of subprocesses

    # globalIsTerminating - Global terminator flag so we don't start multiple
    #   graceful cleanups
    globalIsTerminating = False

    def handleSigTerm(*args):
        '''
            handleSigTerm - Handle signal and perform graceful shutdown
        '''
        global listeners
        global globalIsTerminating
#        sys.stderr.write('CALLED\n')

        # Set terminator so we don't get called multiple times
        #   from multiple signals. Just once.
        if globalIsTerminating is True:
            return # Already terminating
        globalIsTerminating = True

        # Send each of the listener's SIGTERM
        #  (they will all have a handler to graceful shutdown on TERM)
        logerr('Caught signal, shutting down listeners...\n')
        for listener in listeners:
            try:
                os.kill(listener.pid, signal.SIGTERM)
            except:
                pass

        logerr('Sent signal to children, waiting up to %d seconds then trying to clean up\n' %(GRACEFUL_SHUTDOWN_TIME, ) )
        time.sleep(1)
        startTime = time.time()
        time.sleep(2) # This covers the minimum time for listeners to shut down

        # Iterate through listeners and attempt to join them
        #  (if they have completed graceful shutdown)
        remainingListeners = listeners
        remainingListeners2 = []
        for listener in remainingListeners:
            logerr('Waiting on %d...\n' %(listener.pid,))
            listener.join(.05)
            if listener.is_alive() is True:
                remainingListeners2.append(listener)
        remainingListeners = remainingListeners2
        logerr('Remaining (%d) listeners are: %s\n' %(len(remainingListeners), [listener.pid for listener in remainingListeners]))

        afterJoinTime = time.time()

        # If we still have listeners running, we will go through all
        #   subprocesses and try to join
        if remainingListeners:
            delta = afterJoinTime - startTime

            # Round up to number of seconds remaining to stop all the things
            remainingSleep = int(GRACEFUL_SHUTDOWN_TIME - math.floor(afterJoinTime - startTime))
            if remainingSleep > 0:
                anyAlive = False
                # If we still have time left, see if we are just done or if there are children to clean up using remaining time allotment
                if threading.activeCount() > 1 or len(multiprocessing.active_children()) > 0:
                    logerr('Listener closed in %1.2f seconds. Waiting up to %d seconds before terminating.\n' %(delta, remainingSleep))
                    thisThread = threading.current_thread()

                    # In half-second increments (minimum, as we will add 50ms
                    #   per open thread/process), try to cleanup
                    for i in range(remainingSleep * 2):
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
                        time.sleep(.5)

                if anyAlive is True:
                    logerr('Could not kill in time.\n')
                else:
                    logerr('Shutdown successful after %1.2f seconds.\n' %( time.time() - startTime ) )

            else:
                logerr('Listener timed out in closing, exiting uncleanly.\n')
                time.sleep(.05) # Why not? :P

        logmsg('exiting...\n')
        # Disable our signal interceptions
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        # Terminate
        sys.exit(0)
        # Send SIGTERM through standard handler if we survived the above exit
        os.kill(os.getpid(), signal.SIGTERM)
        return 0
    # END handleSigTerm


    # Intercept signals and pass to graceful shutdown
    signal.signal(signal.SIGTERM, handleSigTerm)
    signal.signal(signal.SIGINT, handleSigTerm)

    # Busy loop on this main thread, and listen for
    #   control+c or SystemExit (From above handler sys.exit(0)
    #   and if so, convert to a SIGTERM call,
    #    which will either invoke our handler above or quit
    #    if above handler already completed
    while True:
        try:
            time.sleep(2)
        except:
            os.kill(os.getpid(), signal.SIGTERM)

# vim: set ts=4 sw=4 expandtab
