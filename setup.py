from setuptools import setup

long_description = """
PumpkinLB is a fast multi-process TCP load balancer / port forwarder, compatible with: Linux, Cygwin, and Windows environments.
It listens for requests on ports local to the machine on which it is running, and farms them out to any number of workers.
You can use it to very quickly setup a load balancer, e.x. from 1 entry-point to 5 different apache servers.

Each incoming port is waited-on by a distinct process, and each connection is yet another process, thus it performs very well even under heavy load.
Usage

Execute by running PumpkinLB.py [cfgFile]

Where cfgFile is the path to your config file. There is a sample "example.cfg" included.

Config file is broken up into sections, definable by [$SectionName], followed by variables in format of key=value.

Sections:

 | [options]
 |   pre_resolve_workers=0/1                     [Default 1]    Any workers defined with a hostname will be evaluated at the time the config is read.
 |                                                               This is preferable as it saves a DNS trip for every request, and should be enabled
 |                                                               unless your DNS is likely to change and you want the workers to match the change.
 |
 | [mapping]
 |   localaddr:inport=worker1:port,worker2:port...              Listen on interface defined by "localaddr" on port "inport". Farm out to worker addresses and ports. Ex: 192.168.1.100:80=10.10.0.1:5900,10.10.0.2:5900
 |     or
 |   inport=worker1:port,worker2:port...                        Listen on all interfaces on port "inport", and farm out to worker addresses with given ports. Ex: 80=10.10.0.1:5900,10.10.0.2:5900


So an example to listen on port 80 localhost and farm out to 3 apache servers on your local subnet:

 | 80=192.168.1.100:80,192.168.1.101:80,192.168.1.102:80

Sending SIGTERM, SIGINT, or pressing control+c will do a graceful shutdown (it will wait for up to 4 seconds to finish any active requests, and then terminate).

Requests are generally handled round-robin between the various workers. If a request fails on a backend worker, it will be retried on another random worker until it succeeds, and a message will be logged.
"""

setup(name='PumpkinLB',
        version='1.3',
        scripts=['PumpkinLB.py'],
        packages=['pumpkinlb'],
        author='Tim Savannah',
        author_email='kata198@gmail.com',
        maintainer='Tim Savannah',
        maintainer_email='kata198@gmail.com',
        provides=['PumpkinLB'],
        description='A simple, fast, pure-python load balancer',
        url='https://github.com/kata198/PumpkinLB',
        long_description=long_description,
        license='GPLv3',
        keywords=['load balancer', 'load balance', 'python', 'balance', 'lb', 'http', 'socket', 'port', 'forward', 'tcp', 'fast', 'server', 'network'],
        classifiers=['Development Status :: 4 - Beta',
                     'Programming Language :: Python',
                     'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
                     'Programming Language :: Python :: 2',
                      'Programming Language :: Python :: 2.7',
                     'Topic :: Internet',
                     'Topic :: Internet :: WWW/HTTP',
                     'Topic :: System :: Distributed Computing',
                     'Topic :: System :: Networking',
        ]
)
