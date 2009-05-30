#!/usr/bin/python

import sys
import os
import time
import subprocess

version = "0.5"
debugging = False
quiet = False

# defaults for parameters
default_window    =  50000 # 50 milliseconds
default_width     =   1000 #  1 milliseconds
default_threshold =     10 #  10 microseconds

def debug(str):
    if debugging: print(str)

def info(str):
    if not quiet: print(str)

#
# Class used to manage mounting and umounting the debugfs
# filesystem. Note that if an instance of this class mounts
# the debufs, it will unmount when cleaning up, but if it 
# discovers that debugfs is already mounted, it will leave
# it mounted.
#
class DebugFS(object):
    '''class to manage mounting/umounting the debugfs'''
    def __init__(self):
        self.premounted = False
        self.mounted = False
        self.mountpoint = ''
        f = open('/proc/mounts')
        for l in f:
            field = l.split()
            if field[2] == "debugfs":
                self.premounted = True
                self.mountpoint = field[1]
                break
        f.close()

    def mount(self, path='/sys/kernel/debug'):
        if self.premounted or self.mounted:
            return True
        self.mountpoint = path
        cmd = ['/bin/mount', '-t', 'debugfs', 'none', path]
        self.mounted = (subprocess.call(cmd) == 0)
        return self.mounted

    def umount(self):
        if self.premounted or not self.mounted:
            return True
        cmd = ['/bin/umount', self.mountpoint]
        self.mounted = not (subprocess.call(cmd) == 0)
        return not self.mounted

    def getval(self, item):
        path = os.path.join(self.mountpoint, item)
        f = open(path)
        val = f.readline()
        f.close()
        return val

    def putval(self, item, value):
        path = os.path.join(self.mountpoint, item)
        f = open(path, "w")
        f.write(str(value))
        f.close()

#
# Class used to manage loading and unloading of the 
# smi_detector kernel module. Like the debugfs class 
# above, if the module is already loaded, this class will
# leave it alone when cleaning up.
#
class Kmod(object):
    ''' class to manage loading and unloading smi_detector.ko'''
    def __init__(self, module='smi_detector'):
        self.modname = module
        self.preloaded = False
        f = open ('/proc/modules')
        for l in f:
            field = l.split()
            if field[0] == self.modname:
                self.preloaded = True
                break
        f.close

    def load(self):
        if self.preloaded:
            return True
        cmd = ['/sbin/modprobe', self.modname]
        return (subprocess.call(cmd) == 0)

    def unload(self):
        if self.preloaded:
            return True
        cmd = ['/sbin/modprobe', '-r', self.modname]
        return (subprocess.call(cmd) == 0)

#
# Class to simplify running the smi_detector kernel module
#
class SMI_Detector(object):
    '''class to wrap access to smi_detector debugfs files'''
    def __init__(self):
        if os.getuid() != 0:
            raise RuntimeError, "Must be root"
        self.debugfs = DebugFS()
        self.kmod = Kmod()
        self.setup()
        self.testduration = 10 # ten seconds
        self.samples = []

    def force_cleanup(self):
        debug("forcing unload of smi_detector module")
        self.kmod.preloaded = False
        debug("forcing unmount of debugfs")
        self.debugfs.premounted = False
        self.cleanup()
        debug("exiting")
        sys.exit(0)

    def setup(self):
        if not self.debugfs.mount():
            raise RuntimeError, "Failed to mount debugfs"
        if not self.kmod.load():
            raise RuntimeError, "Failed to unload smi_detector"

    def cleanup(self):
        if not self.kmod.unload():
            raise RuntimeError, "Failed to unload smi_detector"
        if not self.debugfs.umount():
            raise RuntimeError, "Failed to unmount debugfs"

    def get_enable(self):
        return int(self.debugfs.getval("smi_detector/enable"))

    def set_enable(self, value):
        self.debugfs.putval("smi_detector/enable", value)

    def get_threshold(self):
        return int(self.debugfs.getval("smi_detector/threshold"))

    def set_threshold(self, value):
        self.debugfs.putval("smi_detector/threshold", value)

    def get_max(self):
        return int(self.debugfs.getval("smi_detector/max"))

    def set_max(self, value):
        self.debugfs.putval("smi_detector/max", value)

    def get_window(self):
        return int(self.debugfs.getval("smi_detector/window"))

    def set_window(self, value):
        self.debugfs.putval("smi_detector/window", value)

    def get_width(self):
        return int(self.debugfs.getval("smi_detector/width"))

    def set_width(self, value):
        self.debugfs.putval("smi_detector/width", value)

    def get_sample(self):
        return int(self.debugfs.getval("smi_detector/sample"))

    def get_count(self):
        return int(self.debugfs.getval("smi_detector/count"))

    def start(self):
        self.set_enable(1)

    def stop(self):
        self.set_enable(0)
        while self.get_enable() == 1:
            time.sleep(0.1)
            self.set_enable(0)

    def detect(self):
        self.samples = []
        testend = time.time() + self.testduration
        debug("Starting SMI detection for %d seconds" % (self.testduration))
        try:
            self.start()
            while time.time() < testend:
                val = self.get_sample()
                self.samples.append(val)
        finally:
            debug("Stopping SMI detection")
            self.stop()
        debug("SMI detection done (%d samples)" % len(self.samples))

def seconds(str):
    "convert input string to value in seconds"
    if str.isdigit():
        return int(str)
    elif str[-2].isalpha():
        raise RuntimeError, "illegal suffix for seconds: '%s'" % str[-2:-1]
    elif str[-1] == 's':
        return int(str[0:-1])
    elif str[-1] == 'm':
        return int(str[0:-1]) * 60
    elif str[-1] == 'h':
        return int(str[0:-1]) * 3600
    elif str[-1] == 'd':
        return int(str[0:-1]) * 86400
    elif str[-1] == 'w':
        return int(str[0:-1]) * 86400 * 7
    else:
        raise RuntimeError, "unknown suffix for second conversion: '%s'" % str[-1]


def milliseconds(str):
    "convert input string to millsecond value"

    if str.isdigit():
        return int(str)
    elif str[-2:] == 'ms':
        return int(str[0:-2])
    elif str[-1] == 's':
        return int(str[0:-2]) * 1000
    elif str[-1] == 'm':
        return int(str[0:-1]) * 1000 * 60
    elif str[-1] == 'h':
        return int(str[0:-1]) * 1000 * 60 * 60
    elif str[-1].isalpha():
        raise RuntimeError, "unknown suffix for millisecond conversion: '%s'" % str[-1]
    else:
        return int(str)

def microseconds(str):
    "convert input string to microsecond value"
    if str[-2:] == 'ms':
        return int(str[0:-2] * 1000)
    elif str[-1] == 's':
        return int(str[0:-1] * 1000 * 1000)
    elif str[-1].isalpha():
        raise RuntimeError, "unknown suffix for microsecond conversion: '%s'" % str[-1]
    else:
        return int(str)

if __name__ == '__main__':
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option("--duration", default=None, type="string",
                      dest="duration",
                      help="total time to test for SMIs (<n>{smdw})")

    parser.add_option("--threshold", default=None, type="string",
                      dest="threshold",
                      help="value above which is considered an SMI")

    parser.add_option("--window", default=None, type="string",
                      dest="window",
                      help="time between samples")

    parser.add_option("--width", default=None, type="string",
                      dest="width",
                      help="time to actually measure")

    parser.add_option("--report", default=None, type="string",
                      dest="report",
                      help="filename for sample data")

    parser.add_option("--cleanup", action="store_true", default=False,
                      dest="cleanup",
                      help="force unload of module and umount of debugfs")

    parser.add_option("--debug", action="store_true", default=False,
                      dest="debug",
                      help="turn on debugging prints")

    parser.add_option("--quiet", action="store_true", default=False,
                      dest="quiet",
                      help="turn off all screen output")

#    parser.add_option("--walk", action="store_true", default=False,
#                      dest="walk")

    (o, a) = parser.parse_args()

    smi = SMI_Detector()

    if o.debug: 
        debugging = True

    if o.quiet:
        quiet = True

    if o.cleanup:
        debug("forcing cleanup of debugfs and SMI module")
        smi.force_cleanup()
        sys.exit(0)

    if o.threshold:
        t = microseconds(o.threshold)
        smi.set_threshold(t)
        debug("threshold set to %dus" % t)
    else:
	smi.set_threshold(default_threshold)
        debug("threshold defaulted to %dus" % default_threshold)

    if o.window:
        i = microseconds(o.window)
        smi.set_window(i)
        debug("window for sampling set to %dus" % i)
    else:
	smi.set_window(default_window)
        debug("window defaulted to %dus" % default_window)

    if o.width:
        w = microseconds(o.width)
        smi.set_width(w)
        debug("sample width set to %dus" % w)
    else:
	smi.set_width(default_width)
        debug("sample width defaulted to %dus" % default_width)

    if o.duration:
        smi.testduration = seconds(o.duration)
    else:
        smi.testduration = 120 # 2 minutes
    debug("test duration is %ds" % smi.testduration)

    reportfile = o.report

    info("smidetect:  test duration %d seconds" % smi.testduration)
    info("   parameters:")
    info("        Latency threshold: %dus" % smi.get_threshold())
    info("        Sample window:     %dus" % smi.get_window())
    info("        Sample width:      %dus" % smi.get_width())
    info("     Non-sampling period:  %dus" % (smi.get_window() - smi.get_width()))
    info("        Output File:       %s" % reportfile)
    info("\nStarting test")

    smi.detect()

    info("test finished")

    exceeding = smi.get_count()
    info("Max Latency: %dus" % smi.get_max())
    info("Samples recorded: %d" % len(smi.samples))
    info("Samples exceeding threshold: %d" % exceeding)

    if reportfile:
        f = open(reportfile, "w")
        for s in smi.samples:
            f.write("%d\n" % s)
        f.close()
        info("sample data written to %s" % reportfile)
    else:
        for s in smi.samples:
            print "%d" % s

    smi.cleanup()
    sys.exit(exceeding)
