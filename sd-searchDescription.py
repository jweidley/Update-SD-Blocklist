#!/usr/bin/python
# Purpose: This script provides the ability to search the description fields of address objects, since 
#   Security Director currently does not have that functionality.
# Written by: John Weidley
# Version: 0.1
############################################################################################################### 

##############################
# Modules
##############################
import argparse
import requests     # REST
import json         # JSON
from getpass import getpass
from pprint import pprint ## used for debugging

# Disable SSL certificate verification warnings
# https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
import urllib3
urllib3.disable_warnings()

##############################
# Variables
##############################
spaceURL = "https://192.168.3.26"
# --------- dont modify any below -------------
addressURI = spaceURL + "/api/juniper/sd/address-management/addresses?includeDynamicAddresses=boolean"
headers = {'Accept': 'application/vnd.juniper.sd.address-management.address-refs+json;version=1;q=0.01'}
searchList = []

class style:
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    ORANGE='\033[36m'
    RED = '\033[91m'
    END = '\033[0m'

##############################
# Functions
##############################
def search(addDate):
    for p in sdAddrs:
        p.setdefault('description', 'Not Present')  # workaround for missing key.
        #if addDate in p['description']:
        if addDate.lower() in p['description'].lower():
            searchList.append(p)    # Add objects to a list

    return searchList

##############################
# Main
##############################
print(style.BOLD + "==================================================================" + style.END)
print(style.BOLD + " Security Director: Search Address Object Descriptions Fields" + style.END)
print(style.BOLD + "==================================================================" + style.END)
parser = argparse.ArgumentParser(description='Search address object description fields in Security Director')
parser.add_argument("-s", "--search", required=True, type=str, help="String to search for")
parser.add_argument("-u", "--user", required=True, type=str, help="Login name for Security Director")
args = parser.parse_args()

# Prompt for password
print("Enter password for user '{0}': ".format(args.user))
passwd = getpass()
auth = (args.user, passwd)

# Make REST request
resp = requests.get(addressURI, headers=headers, auth=auth, verify=False)

# Load JSON output (Produces a list of dictionaries)
sdAddrs = json.loads(resp.text)['addresses']['address']

# Search the result for desired string
searchResult = search(args.search)

# Display results
print("=====================================================")
print(" The following objects contain a description of '{0}'".format(args.search))
print("=====================================================")
for i in searchResult:
    print(i['name'])

print("")

## End of file ##
