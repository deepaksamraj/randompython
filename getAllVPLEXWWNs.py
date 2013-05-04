#!/usr/bin/python

import json
import requests
import pprint
import sys
import logging
from pysphere import *






#Things for the user to set here
vcenterip = "10.5.132.109"
vcenteruser = "AWESOMESAUCE\mcowger"
vcenterpass = "Habloo12"
vplexip = "10.5.132.105"
vplexip = "10.64.188.52"
vplexuser = "service"
vplexpass = "Mi@Dim7T"
loggingLevel = logging.INFO # or logging.DEBUG
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
                storagevol = storagevolObj['response']['context'][0]['attributes'][-6]['value']
                logging.debug("ID'd" + pprint.pformat(storagevol))
                svolObj = gimmeSomeJSON(baseURL + "/clusters/" + cluster['name'] + "/storage-elements/storage-volumes/" + storagevol)
                wwnOfBackingDevice = svolObj['response']['context'][0]['attributes'][-6]['value'].split(":")[1]
                logging.info("WWN for device backing " + storagevol + ":" + extentname + ":" + supportingdev + ":" + name + " found: " + wwnOfBackingDevice)
                
                LUNs[wwn]['VPLEXmembers'].append(wwnOfBackingDevice)

            
        

#Create an object to work with
server = VIServer()
#Connect to the server
logging.warning("Retrieving vSphere Info")

logging.info("Connecting to vSphere: " + vcenterip)
server.connect(vcenterip, vcenteruser, vcenterpass)

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
        else:
            logging.debug("Not Found - no mapping performed")
    except AttributeError:
        logging.debug("Datastore " + name + " is not a VMFS (NFS?)")
server.disconnect()

pprint.pprint(LUNs)

# logging.debug("Finding VNX and Symmetrix Member Devices in the List")
# 
# for WWN in LUNs.keys():
#     for memberWWN in LUNs[WWN]['VPLEXmembers']:
#         if memberWWN.startswith("6000097"): #make sure before we go searching that its a VMAX device
#             sid,dev = decodeWWID(memberWWN)
#             dev = dev[-4:]
#             logging.info("Decoded memberWWN " + memberWWN + " as " + dev + " on VMAX array " + sid)
#             
#             
# 
