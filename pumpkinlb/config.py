import sys
import socket
try:
    from ConfigParser import ConfigParser
except:
    from configparser import ConfigParser


class PumpkinMapping(object):
    '''
        Represents a mapping of a local listen to a series of workers
    '''

    def __init__(self, localAddr, localPort, workers):
        self.localAddr = localAddr or ''
        self.localPort = int(localPort)
        self.workers = workers
    
    def getListenerArgs(self):
        return [self.localAddr, self.localPort, self.workers]
    
    def addWorker(self, workerAddr, workerPort):
        self.workers.append( {'port' : int(workerPort), 'addr' : workerAddr} )

    def removeWorker(self, workerAddr, workerPort):
        newWorkers = []
        workerPort = int(workerPort)
        removedWorker = None
        for worker in self.workers:
            if worker['addr'] == workerAddr and worker['port'] == workerPort:
                removedWorker = worker
                continue
            newWorkers.append(worker)
        self.workers = newWorkers

        return removedWorker

class PumpkinConfig(ConfigParser):
    '''
        The class for managing Pumpkin's Config File
    '''

    
    def __init__(self, configFilename):
        ConfigParser.__init__(self)
        self.configFilename = configFilename

        self._options = {
            'pre_resolve_workers' : True
        }
        self._mappings = {}

    def parse(self):
        '''
            Parse the config file
        '''
        try:
            f = open(self.configFilename, 'r')
        except IOError as e:
            sys.stderr.write('Could not parse config file: "%s": %s\n' %(self.configFilename, str(e)))
            raise e
        [self.remove_section(s) for s in self.sections()]
        self.readfp(f)
        f.close()

        self._processOptions()
        self._processMappings()

    def getOptions(self):
        '''
            Gets the options dictionary
        '''
        return self._options

    def getMappings(self):
        '''
            Gets the mappings dictionary
        '''
        return self._mappings

    def _processOptions(self):
        try:
            preResolveWorkers = self.get('options', 'pre_resolve_workers')
            if preResolveWorkers == '1' or preResolveWorkers.lower() == 'true':
                self._options['pre_resolve_workers'] = True
            elif preResolveWorkers == '0' or preResolveWorkers.lower() == 'false':
                self._options['pre_resolve_workers'] = False
            else:
                sys.stderr.write('WARNING: Unknown value for [options] -> pre_resolve_workers "%s" -- ignoring value, retaining previous "%s"\n' %(str(preResolveWorkers), str(self._options['pre_resolve_workers'])))
        except:
            pass

    def _processMappings(self):
        preResolveWorkers = self._options['pre_resolve_workers']

        mappings = {}
        mappingSectionItems = self.items('mappings')
        
        for (addrPort, workers) in mappingSectionItems:
            addrPortSplit = addrPort.split(':')
            addrPortSplitLen = len(addrPortSplit)
            if not workers:
                sys.stderr.write('WARNING: Skipping, no workers defined for %s\n' %(addrPort,))
                continue
            if addrPortSplitLen == 1:
                (localAddr, localPort) = ('0.0.0.0', addrPort)
            elif addrPortSplitLen == 2:
                (localAddr, localPort) = addrPortSplit
            else:
                sys.stderr.write('WARNING: Skipping Invalid mapping: %s=%s\n' %(addrPort, workers))
                continue
            try:
                localPort = int(localPort)
            except ValueError:
                sys.stderr.write('WARNING: Skipping Invalid mapping, cannot convert port: %s\n' %(addrPort,))
                continue

            workerLst = []
            for worker in workers.split(','):
                workerSplit = worker.split(':')
                if len(workerSplit) != 2 or len(workerSplit[0]) < 3 or len(workerSplit[1]) == 0:
                    sys.stderr.write('WARNING: Skipping Invalid Worker %s\n' %(worker,))

                if preResolveWorkers is True:
                    try:
                        addr = socket.gethostbyname(workerSplit[0])
                    except:
                        sys.stderr.write('WARNING: Skipping Worker, could not resolve %s\n' %(workerSplit[0],))
                else:
                    addr = workerSplit[0]
                try:
                    port = int(workerSplit[1])
                except ValueError:
                    sys.stderr.write('WARNING: Skipping worker, could not parse port %s\n' %(workerSplit[1],))

                workerLst.append({'addr' : addr, 'port' : port})
            if mappings.has_key(localAddr + ':' + addrPort):
                sys.stderr.write('WARNING: Overriding existing mapping of %s with %s\n' %(addrPort, str(workerLst)))
            mappings[addrPort] = PumpkinMapping(localAddr, localPort, workerLst)

        self._mappings = mappings
          
# vim: ts=4 sw=4 expandtab
