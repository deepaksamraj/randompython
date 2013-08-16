#!/usr/bin/python

import json
import requests
import pprint
import sys
import logging
from pysphere import *





#Things for the user to set here
vcenterip = "10.5.132.109"
vcenteruser = "root"
vcenterpass = "vmware"
#vplexip = "10.5.44.171"
vplexip = "10.5.132.105"
#vplexip = "10.5.132.105"
vplexuser = "service"
vplexpass = "Mi@Dim7T"
loggingLevel = logging.CRITICAL # or logging.DEBUG
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

#pprint.pprint(LUNs)

print "VPLEXWWN,VMwareMOR,DSName,VPLEXVVName,SymmMember1,SymmMember2,SymmMember3,SymmMember4,SymmMember5,SymmMember6,SymmMember7,SymmMember8"

for WWN in LUNs.keys():
    VPLEXWWN = WWN
    VMwareMOR = LUNs[WWN]['VMwareMOR']
    DSName = LUNs[WWN]['VMwareName']
    VPLEXVVName = LUNs[WWN]['VPLEXName']
    SymmID1 = ""
    SymmID2 = ""
    SymmID3 = ""
    SymmID4 = ""
    SymmID5 = ""
    SymmID6 = ""
    SymmID7 = ""
    SymmID8 = ""
    try:

        SymmID1 = LUNs[WWN]['VPLEXmembers'][0]
        if SymmID1.startswith("6000097"):
            sid,dev = decodeWWID(SymmID1)
            SymmID1 = "/".join([sid,dev])
        SymmID2 = LUNs[WWN]['VPLEXmembers'][1]
        if SymmID2.startswith("6000097"):
            sid,dev = decodeWWID(SymmID2)
            SymmID2 = "/".join([sid,dev])
        SymmID3 = LUNs[WWN]['VPLEXmembers'][2]
        if SymmID3.startswith("6000097"):
            sid,dev = decodeWWID(SymmID3)
            SymmID3 = "/".join([sid,dev])
        SymmID4 = LUNs[WWN]['VPLEXmembers'][3]
        if SymmID4.startswith("6000097"):
            sid,dev = decodeWWID(SymmID4)
            SymmID4 = "/".join([sid,dev])
        SymmID5 = LUNs[WWN]['VPLEXmembers'][4]
        if SymmID5.startswith("6000097"):
            sid,dev = decodeWWID(SymmID5)
            SymmID5 = "/".join([sid,dev])
        SymmID6 = LUNs[WWN]['VPLEXmembers'][5]
        if SymmID6.startswith("6000097"):
            sid,dev = decodeWWID(SymmID6)
            SymmID6 = "/".join([sid,dev])
        SymmID7 = LUNs[WWN]['VPLEXmembers'][6]
        if SymmID7.startswith("6000097"):
            sid,dev = decodeWWID(SymmID7)
            SymmID7 = "/".join([sid,dev])
        SymmID8 = LUNs[WWN]['VPLEXmembers'][7]
        if SymmID8.startswith("6000097"):
            sid,dev = decodeWWID(SymmID8)
            SymmID8 = "/".join([sid,dev])
    except:
        pass
    
    print ",".join([VPLEXWWN,VMwareMOR,DSName,VPLEXVVName,SymmID1,SymmID2,SymmID3,SymmID4,SymmID5,SymmID6,SymmID7,SymmID8])

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
