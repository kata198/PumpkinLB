#!/bin/bash


if [ -d $PREFIX/usr/lib/python2.7/site-packages ];
then
	cp -r pumpkinlb $PREFIX/usr/lib/python2.7/site-packages
elif [ -d $PREFIX/usr/lib/python2.6/site-packages ];
then
	cp -r pumpkinlb $PREFIX/usr/lib/python2.6/site-packages
else
	echo "Could not determine path for python site packages." >&2
	exit 1;
fi
	
cp PumpkinLB.py $PREFIX/usr/sbin/
