# PumpkinLB Copyright (c) 2014-2015, 2017, 2018 Tim Savannah under GPLv3.
# You should have received a copy of the license as LICENSE 
#
# See: https://github.com/kata198/PumpkinLB

import copy
import sys
import socket
try:
    from ConfigParser import ConfigParser
except:
    from configparser import ConfigParser

from .constants import DEFAULT_BUFFER_SIZE
from .log import logmsg, logerr

__all__ = ( 'PumpkinMapping', 'PumpkinConfig', 'PumpkinConfigException' )


class PumpkinMapping(object):
    '''
        PumpkinMapping - Represents a mapping of a local listen to a series of workers
    '''

    def __init__(self, localAddr, localPort, workers):
        '''
            __init__ - Create this object

                @param localAddr <str> - Local address on which to bind (interface address or '0.0.0.0' for all interfaces)

                @param localPort <int> - Local port on which to bind

                @param workers list< dict< 'port' : <int> worker port, 'addr' : <str> worker addr > > - 

                    A list of workers to handle requests on #localAddr:#localPort
        '''
        self.localAddr = localAddr or ''
        self.localPort = int(localPort)
        self.workers = workers


    def getListenerArgs(self):
        '''
            getListenerArgs - Get the arguments (in order) to create a PumpkinListener object

                @return list< <str>local addr, <str>local port, list<dict< 'port', 'addr'>>workers
        '''
        return [self.localAddr, self.localPort, self.workers]


    def addWorker(self, workerAddr, workerPort):
        '''
            addWorker - Add a worker to this mapping

                @param workerAddr <str> - Internet address of worker

                @param workerPort <int> - Port on worker
        '''
        self.workers.append( {'port' : int(workerPort), 'addr' : workerAddr} )


    def removeWorker(self, workerAddr, workerPort):
        '''
            removeWorker - Remove a worker from this mapping's handlers

                @param workerAddr <str> - Internet address of worker

                @param workerPort <int> - Port on worker


                @return <None/dict<'port', 'addr'>> - The worker matched
        '''

        workerPort = int(workerPort)

        tryRemoveWorker = { 'port' : workerPort, 'addr' : workerAddr }
        try:
            self.workers.remove( tryRemoveWorker )
        except ValueError:
            # No such worker in list
            return None

        return tryRemoveWorker


# _DEFAULT_CONFIG_OPTIONS - Default values for the "options" section of config
_DEFAULT_CONFIG_OPTIONS = {
    'pre_resolve_workers'  : True,
    'buffer_size'          : DEFAULT_BUFFER_SIZE,
}

class PumpkinConfig(ConfigParser):
    '''
        PumpkinConfig - The class for managing Pumpkin's Config File
    '''


    def __init__(self, configFilename):
        '''
            __init__ - Create this object

                @param configFilename <str> - Path to the config file

             This method will initialize default options, but #configFilename
               will not be parsed until .parse() is called
        '''
        ConfigParser.__init__(self)
        self.configFilename = configFilename

        self._options = copy.deepcopy(_DEFAULT_CONFIG_OPTIONS)
        self._mappings = {}


    def parse(self):
        '''
            parse - Parse the config file. 

              This will replace existing options with those extracted
               from the config file.

                @raises <IOError> - If #configFilename on this
                    class does not point to a file we can read.

                    On python3 you'll get a subclass of IOError
                      (e.x. FileNotFoundError or PermissionError)
                    catching IOError will cover all cases in both py2/py3
        '''
        try:
            f = open(self.configFilename, 'rt')
        except IOError as e:
            # NOTE: FileNotFoundError is subclass of IOError so this works on py3
            #   As is PermissionError
            logerr('Could not open config file: "%s": %s\n' %(self.configFilename, str(e)))
            raise e

        # Clear existing config sections, if any
        [self.remove_section(s) for s in self.sections()]
        # Call ConfigParser.readfp
        self.readfp(f)
        # Close file
        f.close()

        # Process the options section
        self._processOptions()
        # Process the mappings section
        self._processMappings()


    def getOptions(self):
        '''
            getOptions - Gets a copy of the options dictionary

                @return <dict> - Keys of "pre_resolve_workers", "buffer_size"
        '''
        return copy.deepcopy(self._options)


    def getOptionValue(self, optionName):
        '''
            getOptionValue - Gets the value of an option

                @param optionName <str> - One of the option names

                    ( "pre_resolve_workers" or "buffer_size" )


                @return <type> - The value of the option at #optionName
        '''

        return self._options[optionName]


    def getMappings(self):
        '''
            getMappings - Gets a copy of the mappings dictionary

                @return <dict> - <str>"${localaddr}:${localport}" : PumpkinMapping object
        '''
        return copy.deepcopy(self._mappings)


    def _processOptions(self):
        '''
            _processOptions - Process the [options] section of the config
        '''
        # Restore default options before parsing fresh
        self._options = copy.deepcopy(_DEFAULT_CONFIG_OPTIONS)


        # I personally think the config parser interface sucks...
        if 'options' not in self._sections:
            return

        try:
            preResolveWorkers = self.get('options', 'pre_resolve_workers')
            if preResolveWorkers == '1' or preResolveWorkers.lower() == 'true':
                self._options['pre_resolve_workers'] = True
            elif preResolveWorkers == '0' or preResolveWorkers.lower() == 'false':
                self._options['pre_resolve_workers'] = False
            else:
                logerr('WARNING: Unknown value for [options] -> pre_resolve_workers "%s" -- ignoring value, retaining previous "%s"\n' %(str(preResolveWorkers), str(self._options['pre_resolve_workers'])) )
        except:
            pass

        try:
            bufferSize = self.get('options', 'buffer_size')
            if bufferSize.isdigit() and int(bufferSize) > 0:
                self._options['buffer_size'] = int(bufferSize)
            else:
                logerr('WARNING: buffer_size must be an integer > 0 (bytes). Got "%s" -- ignoring value, retaining previous "%s"\n' %(bufferSize, str(self._options['buffer_size'])) )
        except Exception as e:
            logerr('Error parsing [options]->buffer_size : %s. Retaining default, %s\n' %(str(e),str(DEFAULT_BUFFER_SIZE)) )


    def _processMappings(self):
        '''
            _processMappings - Process the [mappings] section of the config

                NOTE: _processOptions should be called FIRST, as values therein
                  change how the mappings are processed/handled
        '''

        # Restore default options before parsing fresh
        self._mappings = {}

        if 'mappings' not in self._sections:
            raise PumpkinConfigException('ERROR: Config is missing required "mappings" section.\n')

        preResolveWorkers = self._options['pre_resolve_workers']

        mappings = {}
        mappingSectionItems = self.items('mappings')

        # Iterate through each mapping line, which should be
        #  inAddr:inPort = workers or inPort = workers
        for (addrPort, workers) in mappingSectionItems:
            # addrPort - left side of "="
            # workers  - right side of "="

            addrPortSplit = addrPort.split(':')
            addrPortSplitLen = len(addrPortSplit)
            if not workers:
                # If blank right-side
                logerr('WARNING: Skipping, no workers defined for %s\n' %(addrPort,))
                continue
            if addrPortSplitLen == 1:
                # Port only on left side
                (localAddr, localPort) = ('0.0.0.0', addrPort)
            elif addrPortSplitLen == 2:
                # addr:port on left side
                (localAddr, localPort) = addrPortSplit
            else:
                # TODO: Handle ipv6 address which is going to have a ton of :

                # Error on left side (too many ':')
                logerr('WARNING: Skipping Invalid mapping: "%s=%s" left side should be localAddr:localPort= or localPort=\n' %(addrPort, workers))
                continue

            try:
                localPort = int(localPort)
            except ValueError:
                logerr('WARNING: Skipping Invalid mapping "%s=%s", cannot convert port to integer: %s\n' %(addrPort, workers, localPort))
                continue

            if localPort < 1 or localPort > 65535:
                logerr('WARNING: Skipping Invalid mapping "%s=%s", port "%d" is not valid ( 1 - 65535 )\n' %(addrPort, workers, localPort) )
                continue

            workerLst = []

            # Multiple workers separated by commas.
            #  Split them out and validate, printing a warning if
            #   validation fails, otherwise adding as dict to #workerLst
            for worker in workers.split(','):

                # Clear any whitespace
                worker = worker.strip()
                workerSplit = worker.split(':')

                # Ensure worker is in addr:port format.
                #   Minimum valid addr is 3 characters, minimum valid port is 1
                if len(workerSplit) != 2 or len(workerSplit[0]) < 3 or len(workerSplit[1]) == 0:
                    logerr('WARNING: Skipping Invalid Worker "%s". Should be in format addr:port.\n' %(worker,) )
                    continue

                if preResolveWorkers is True:
                    # If we are pre-resolving, unroll DNS now
                    #   NOTE: This works if IP is passed or valid DNS,
                    #    otherwise exception
                    try:
                        addr = socket.gethostbyname(workerSplit[0])
                    except:
                        logerr('WARNING: Skipping Worker "%s", could not resolve "%s"\n' %(worker, workerSplit[0]) )
                        continue

                else:
                    # If pre-resolve is disabled,
                    #  we will resolve at connect-time
                    addr = workerSplit[0]

                # Ensure "port" is a valid integer
                try:
                    port = int(workerSplit[1])
                except ValueError:
                    logerr('WARNING: Skipping worker "%s", could not parse port %s\n' %(worker, workerSplit[1]) )
                    continue

                # Ensure "port" is in range
                if port < 1 or port > 65535:
                    logerr('WARNING: Skipping worker "%s", port "%d" is not valid ( 1 - 65535 )\n' %(worker, port) )
                    continue

                # Everything is valid, add to the list of workers
                workerLst.append( {'addr' : addr, 'port' : port} )

                # END - looping over each worker in this mapping

            # Generate this mapping's key
            keyName = "%s:%s" %(localAddr, addrPort)
            if keyName in mappings:
                # Someone defined this mapping multiple times.
                #  Could maybe append uniques here, but for now just replace
                logerr('WARNING: Overriding existing mapping of %s ( %s ) with %s\n' %(keyName, str(workerLst)))

            # Set this mapping
            mappings[keyName] = PumpkinMapping(localAddr, localPort, workerLst)

        # Set _mappings on this object
        self._mappings = mappings


class PumpkinConfigException(Exception):
    '''
        PumpkinConfigException - A configuration exception that cannot be ignored.

            Generally, any errors in your config will be logged to stderr upon start/parse,
              and ignored (for outage-prevention reasons). 

            If you have no [mappings] section, for example, there is nothing for pumpkinlb to do
             and it cannot be ignored.
    '''
    pass

# vim: ts=4 sw=4 expandtab
