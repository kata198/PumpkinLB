# PumpkinLB Copyright (c) 2014-2015 Tim Savannah under GPLv3.
# You should have received a copy of the license as LICENSE 
#
# See: https://github.com/kata198/PumpkinLB

import os
import sys

from . import __version__ as pumpkinlb_version

from .constants import DEFAULT_BUFFER_SIZE

def printUsage(toStream=sys.stdout):
    toStream.write('''Usage: %s [config file]
Starts Pumpkin Load Balancer using the given config file.

  Arguments:

    --help                         Print this message
    --help-config                  Print help regarding usage of the config file
    --version                      Show version information

  Signals:
  
    SIGTERM                        Performs a graceful shutdown

%s
''' %(os.path.basename(sys.argv[0]), getVersionStr())
    )
#    SIGUSR1                        Re-read the config, and alter service to match TODO: NOT DONE



def printConfigHelp(toStream=sys.stdout):
    toStream.write('''Config Help

Config file is broken up into sections, definable by [$SectionName], followed by variables in format of key=value.

  Sections:
  
    [options]
      pre_resolve_workers=0/1                     [Default 1]    Any workers defined with a hostname will be evaluated at the time the config is read. 
                                                                   This is preferable as it saves a DNS trip for every request, and should be enabled
                                                                   unless your DNS is likely to change and you want the workers to match the change.

      buffer_size=N                             [Default %d]   Default read/write buffer size (in bytes) used on socket operations. 4096 is a good default for most, but you may be able to tune better depending on your application.

    [mapping]
      localaddr:inport=worker1:port,worker2:port...              Listen on interface defined by "localaddr" on port "inport". Farm out to worker addresses and ports. Ex: 192.168.1.100:80=10.10.0.1:5900,10.10.0.2:5900
        or
      inport=worker1:port,worker2:port...                        Listen on all interfaces on port "inport", and farm out to worker addresses with given ports. Ex: 80=10.10.0.1:5900,10.10.0.2:5900
   
''' %(DEFAULT_BUFFER_SIZE, )
    )


def getVersionStr():
    return 'PumpkinLB Version %s (c) 2014-2015 Timothy Savannah GPLv3' %(pumpkinlb_version,)

# vim : ts=4 sw=4 expandtab


