import sys
from pysphere import *
server = VIServer()
server.connect("192.168.56.128", "root", "vmware")
lines = []
for ds, name in server.get_datastores().items():
    props = VIProperty(server, ds)
    curline = name
    for vm in props.vm:
        curline = curline + "," + vm.name
    print curline
