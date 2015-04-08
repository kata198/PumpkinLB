# PumpkinLB
A simple, fast, pure-python load balancer

Description
===========

PumpkinLB is a fast multi-process TCP load balancer, compatible with: Linux, Cygwin, and Windows environments. It listens for requests on local ports, and farms them out to any number of workers. You can use it to very quickly setup a load balancer, e.x. from 1 front point to 5 different apache servers.

Each incoming port is waited-on by a distinct process, and each connection is yet another process, thus it performs very well even under heavy load.

Usage
=====

Execute by running PumpkinLB.py [cfgFile]

Where cfgFile is the path to your config file. There is a sample "example.cfg" included.

Config file is broken up into sections, definable by [$SectionName], followed by variables in format of key=value.

  Sections:

    [options]
      pre_resolve_workers=0/1                     [Default 1]    Any workers defined with a hostname will be evaluated at the time the config is read.
                                                                   This is preferable as it saves a DNS trip for every request, and should be enabled
                                                                   unless your DNS is likely to change and you want the workers to match the change.

    [mapping]
      localaddr:inport=worker1:port,worker2:port...              Listen on interface defined by "localaddr" on port "inport". Farm out to worker addresses and ports. Ex: 192.168.1.100:80=10.10.0.1:5900,10.10.0.2:5900
        or
      inport=worker1:port,worker2:port...                        Listen on all interfaces on port "inport", and farm out to worker addresses with given ports. Ex: 80=10.10.0.1:5900,10.10.0.2:5900


So an example to listen on port 80 localhost and farm out to 3 apache servers on your local subnet:

80=192.168.1.100:80,192.168.1.101:80,192.168.1.102:80



Sending SIGTERM, SIGINT, or pressing control+c will do a graceful shutdown (it will wait for up to 4 seconds to finish any active requests, and then terminate).


Requests are generally handled round-robin between the various workers. If a request fails on a backend worker, it will be retried on another random worker until it succeeds, and a message will be logged.


Installation
============

PumpkinLB comes with an install.sh script, which will install in the default location for python 2.7, or python 2.6.

As an alternative, you can copy the "pumpkinlb" folder to your site packages folder, and "PumpkinLB.py" to your bin folder.

As yet another alternative, this can run standalone anywhere, so long as "pumpkinlb" folder is within the same directory (or otherwise PYTHONPATH) as PumpkinLB.py
