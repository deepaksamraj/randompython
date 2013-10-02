#!/usr/bin/python

import json
import requests
import pprint
import sys
import logging
from pyxml2obj import XMLin, XMLout
from pysphere import *





#Things for the user to set here
#vcenterip = "10.113.61.16"
#vcenteruser = "storagevcmon"
#vcenterpass = "V1!2tU@7Mo!7iT0RiN6"
#vplexip = "10.5.44.171"
#vplexip = "10.113.192.140"
vplexip = "10.5.132.105"
vplexuser = "service"
vplexpass = "Mi@Dim7T"
vcenterip = "10.5.132.109"
vcenteruser = "root"
vcenterpass = "vmware"
loggingLevel = logging.DEBUG # or logging.DEBUG
#-------------------------


logging.basicConfig(level=loggingLevel, format='%(asctime)s - %(levelname)s - %(message)s')
headers = {'username':vplexuser,'password':vplexpass}
LUNs = {}
baseURL = "https://" + vplexip + "/vplex"

logging.warning("Retrieving VPLEX Info")

def chunks(l,n):
    """
    split a list/string into groups of n-elements
    """
    return [ l[i:i+n] for i in range(0,len(l),n) ]

def decodeWWID(sWWID, lazy = False):
    """
    decode symmetrix device wwn into its device name

    returns
        sid, symdevname

    (see emc234137)
    """

    sWWID = sWWID.replace(':','')
    if len(sWWID) != 32:
        if not lazy:
            raise Exception, "uff, IMHO a WWID should be 32 digits long (%s -> %i)" % (sWWID, len(sWWID))
        else:
            logging.warning("WWID '%s' too long, took the last 32 digits..." % sWWID)
            sWWID = sWWID[-32:]

 
    sid=sWWID[9:20]
    devenc_hex = sWWID[20:]
    devenc_hex = chunks(devenc_hex,2)
    devdec=''.join(map(chr,map(int,devenc_hex,[16]*len(devenc_hex))))
    logging.debug("%s => %s , %s => %s" % (sWWID,sid,devenc_hex, devdec))

    return sid,devdec


def gimmeSomeJSON(URL):
    logging.debug("Requesting " + URL)
    r = requests.get(URL, headers=headers, verify=False)
    #logging.debug("received from server" + r.text)
    try:
        Obj = json.loads(r.text)
    except:
        print "Exception - unable to parse JSON response"
        print r.text
        sys.exit(1)
    logging.debug("parsed from server:\n" + pprint.pformat(Obj))
    return Obj


#First Get the list of all clusters

clusterObj = gimmeSomeJSON(baseURL + "/clusters")

try:
    for cluster in clusterObj['response']['context'][0]['children']:
        logging.info("Processing cluster: " + cluster['name'] + " of " + str(len(clusterObj['response']['context'][0]['children'])))
        viewsObj = gimmeSomeJSON(baseURL + "/clusters/" + cluster['name'] + "/exports/storage-views")
        for view in viewsObj['response']['context'][0]['children']:
            logging.info("    Processing view: " + view['name'])
            viewObj = gimmeSomeJSON(baseURL + "/clusters/" + cluster['name'] + "/exports/storage-views/" + view['name'])
            volumes = viewObj['response']['context'][0]['attributes'][7]['value']
            for volume in volumes:
                wwn = volume.split(",")[2].split(":")[1]
                lunid = volume.split(",")[0].replace("(","")
                name = volume.split(",")[1]
                logging.info("        Processing " + "volume: " + volume.split(",")[1])
                LUNs[wwn] = {"VPLEXName":name}
                virtualvolumeObj = gimmeSomeJSON(baseURL + "/clusters/" + cluster['name'] + "/virtual-volumes/" + name)
                supportingdev = virtualvolumeObj['response']['context'][0]['attributes'][-3]['value']
                logging.debug("supporting device for " + name + ": " + pprint.pformat(supportingdev))
                deviceObj = gimmeSomeJSON(baseURL + "/clusters/" + cluster['name'] + "/devices/" + supportingdev + "/components/")
                suppdevices = deviceObj['response']['context'][0]['children']
                LUNs[wwn]['VPLEXmembers'] = []
                for extent in suppdevices:
                    extentname = extent['name']
                    logging.info("Searching for extent " + extent['name'] + "as part of " + supportingdev + " for virtual " + name) 
                    storagevolObj = gimmeSomeJSON(baseURL + "/clusters/" + cluster['name'] + "/storage-elements/extents/" + extentname)
                    storagevol = storagevolObj['response']['context'][0]['attributes'][-7]['value']
                    logging.debug("ID'd" + pprint.pformat(storagevol))
                    svolObj = gimmeSomeJSON(baseURL + "/clusters/" + cluster['name'] + "/storage-elements/storage-volumes/" + storagevol)
                    wwnOfBackingDevice = svolObj['response']['context'][0]['attributes'][-7]['value'].split(":")[1]
                    logging.info("WWN for device backing " + storagevol + ":" + extentname + ":" + supportingdev + ":" + name + " found: " + wwnOfBackingDevice)
                    if wwnOfBackingDevice.startswith("6000097"):
                        sid,dev = decodeWWID(wwnOfBackingDevice)
                        wwnOfBackingDevice = "/".join(["Symm:",sid,dev])
                    LUNs[wwn]['VPLEXmembers'].append(wwnOfBackingDevice)
except:
    print("Exception occured - exiting VPLEX block")
    pass
            
        

#Create an object to work with
server = VIServer()
#Connect to the server
logging.warning("Retrieving vSphere Info")

logging.info("Connecting to vSphere: " + vcenterip)
server.connect(vcenterip, vcenteruser, vcenterpass)

logging.debug("Collecting data for Datastore->VM Mapping")
DSs = {}
for ds, name in server.get_datastores().items():
    props = VIProperty(server, ds)
    DSs[name] = []
    logging.debug("Recording VMs for DS: " + name)
    for vm in props.vm:
        logging.debug("Adding VM to DS list for DS " + name + ":" + vm.name)
        DSs[name].append(vm.name)


for ds_mor, name in server.get_datastores().items(): 
    props = VIProperty(server, ds_mor)
    name = props.info.name
    id = ""
    try:
        id = unicode(props.info.vmfs.extent[0].diskName.replace("naa.",""))
        logging.debug("Evaluating VMware DS: " + name + " with ID: " + id)
        logging.debug("Looking for match in the LUNs table")
        if id in LUNs:
            LUNs[id]["VMwareName"] = name
            LUNs[id]["VMwareMOR"] = ds_mor
            logging.info("Mapped " + LUNs[id]['VPLEXName'] + " to " + name + " as " + id)
            LUNs[id]["VirtualMachines"] = []
            logging.debug("Adding LUNs from DS list:")
            logging.debug(DSs[name])
            LUNs[id]["VirtualMachines"].extend(DSs[name])
        else:
            logging.debug("Not Found - no mapping performed")
    except AttributeError:
        logging.debug("Datastore " + name + " is not a VMFS (NFS or Local CDROM?)")
server.disconnect()


wholeXML = XMLout(LUNs)

print wholeXML


