#!/usr/bin/python

import requests, json, pprint, time, socket

CARBON_SERVER = '10.5.132.58'
CARBON_PORT = 2003

def send_msg(message):
    #print 'sending message: %s' % message
    sock = socket.socket()
    sock.connect((CARBON_SERVER, CARBON_PORT))
    sock.sendall(message)
    sock.close()


target_url = "https://10.5.132.58:8443/univmax/restapi/performance/Array/metrics"

requestObj = {'arrayParam': 
            {'endDate': int(time.time()*1000), #End time to specify is now.
             'startDate': int(time.time()*1000)-(3600*1000), #start time is 60 minutes before that
             'metrics': ['IO_RATE'], #array of what metrics we want
             'symmetrixId': '000194900728' #symmetrix ID (full 12 digits)
            }
          }
          
requestJSON = json.dumps(requestObj, sort_keys=True, indent=4) #turn this into a JSON string
#print requestJSON

headers = {'content-type': 'application/json','accept':'application/json'} #set the headers for how we want the response

#make the actual request, specifying the URL, the JSON from above, standard basic auth, the headers and not to verify the SSL cert.
r = requests.post(target_url, requestJSON, auth=('smc', 'smc'), headers=headers, verify=False)


#take the raw response text and deserialize it into a python object.
try:
    responseObj = json.loads(r.text)
except:
    print "Exception"
    print r.text
#print json.dumps(responseObj, sort_keys=False, indent=4)

#make sure we actually get a value back.
#data = None
if len(responseObj["iterator"]["resultList"]["result"]) > 0:
    data = float(responseObj["iterator"]["resultList"]["result"][0]['IO_RATE'])
    line = 'Symmetrix.System.IO_RATE %d %d' % (data, int(time.time()))
    send_msg(line)
    print line
else:
    print "Short response"
    pprint.pprint(responseObj)
