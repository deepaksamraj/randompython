import pprint
from pysphere import *
server = VIServer()
server.connect("10.5.132.109", "root", "vmware")

DSs = {}

for ds, name in server.get_datastores().items():
    props = VIProperty(server, ds)
    DSs[name] = []
    for vm in props.vm:
        DSs[name].append(vm.name)
pprint.pprint(DSs)

