#!/usr/bin/env python

import os, sys, optparse, yaml, types
import wasanbon
from wasanbon.core import package as pack
from wasanbon.core import rtc, tools, repositories
from wasanbon.util import editor
from wasanbon import util


class Command(object):
    def __init__(self):
        pass

    def alternative(self):
        _package = pack.Package(os.getcwd())
        return [rtc.name for rtc in _package.rtcs]

    def get_rtc_rtno(self, _package, name, verbose=False):
        try:
            return _package.rtc(name)
        except wasanbon.RTCNotFoundException, e:
            return tools.get_rtno_package(_package, name, verbose=verbose)

    def execute_with_argv(self, argv, verbose, force, clean):
        wasanbon.arg_check(argv, 3)
        _package = pack.Package(os.getcwd())
        sys.stdout.write(' @ Pushing RTC repository  %s to upstream.\n' % argv[2])
        self.get_rtc_rtno(_package, argv[2], verbose=verbose).push(verbose=True) # when pushing always must be verbose 

