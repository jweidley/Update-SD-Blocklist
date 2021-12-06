#!/usr/bin/python
# Purpose: Update an Address Group in Security Director with data supplied by a text file.
# Written by: John Weidley
# Version: 0.10
############################################################################################################### 
# ChangeLog:
# 0.8: 2Oct21: Check for the group first.
# 0.9: 12Oct21: Regardless of # of entries, put them all in the same group and print a warning if > 1024
# 0.10: 23Oct21: Use single login session & cookies
############################################################################################################### 

##############################
# Modules
##############################
import argparse             
import ipaddress            ## IP Address verification
import requests             ## REST
import json                 
import datetime
import sys
from getpass import getpass
from jinja2 import Template ## Templating
from pprint import pprint   ## Debugging

# Disable SSL certificate verification warnings
# https://urllib3.readthedocs.io/en/latest/advanced-usage.html#ssl-warnings
import urllib3
urllib3.disable_warnings()

##############################
# Variables
##############################
spaceURL = "https://192.168.3.26"
AddressGroupName = "SIRT-Block-List"
# --------- dont modify any below -------------
loginURI = spaceURL + "/api/space/user-management/login"
logoutURI = spaceURL + "/api/space/user-management/logout"
headers = {'Accept': 'application/vnd.net.juniper.space.user-management.user-ref+json;version=1'}
cookies = {}    ## Custom dict to store cookies.
now = datetime.datetime.now()
timeStamp = now.strftime("%d%b%Y")
membersList = []
backSlash = "/"
badIpList = []

class style:
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    ORANGE='\033[36m'
    RED = '\033[91m'
    END = '\033[0m'

#################################################################################################################
# Functions
#################################################################################################################
# readBlockList Function:
# Read in the block list text file, remove next lines & values in list format
#################################################################################################################
def readBlockList():
    try:
        lines = []
        with open(args.file, "r") as file:
            #print("- Reading in BlockList file...")
            for line in file:
                if line.strip().startswith('#'):    # ignore comments
                    continue
                elif line == "\n":                  # ignore newlines
                    continue
                else:
                    line = line.strip()
                    lines.append(line)

            return lines
    except Exception as error:
        print("\nCould not find or read Blocklist file!!!")
        print("ERROR: Reading Blocklist file: {0}\n".format(error))
        exit()

#################################################################################################################
# searchSDbyIP Function:
# See SD DB by IP address to see if address objects already exist.
#################################################################################################################
def searchSDbyIP(ssoSession,spaceURL,ipAddress):
    apiURI = "/api/juniper/sd/address-management/addresses"
    url = spaceURL + apiURI + "?filter=(ipAddress eq '{0}')".format(ipAddress)
    headers = {'Accept': 'application/vnd.juniper.sd.address-management.address-refs+json;version=1;q=0.01'}
    try:
        searchResponse = requests.get(url, headers=headers, cookies=ssoSession.cookies, verify=False)
        searchResponse.raise_for_status()
        # Check the result total entries to see if it exists
        resultCount = searchResponse.json()['addresses']['total']
        if resultCount >= 1:
            objectID = searchResponse.json()['addresses']['address'][0]['id']
        else:
            objectID = "add"

        return objectID
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)

#################################################################################################################
# getGroupID Function:
# Search SD DB by IP address to see if address objects already exist.
#################################################################################################################
def getGroupID(ssoSession,spaceURL,AddressGroupName):
    apiURI = "/api/juniper/sd/address-management/addresses"
    url = spaceURL + apiURI + "?filter=(name eq '{0}')".format(AddressGroupName)
    headers = {'Accept': 'application/vnd.juniper.sd.address-management.address-refs+json;version=1;q=0.01'}
    try:
        groupResponse = requests.get(url, headers=headers, cookies=ssoSession.cookies, verify=False)
        groupResponse.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)  

    # Check if the group exists
    resultCount = groupResponse.json()['addresses']['total']
    if resultCount >= 1:
        group_id = groupResponse.json()['addresses']['address'][0]['id']
        return group_id
    else:
        print(style.RED + "   ! ERROR: address group \'" + AddressGroupName + "\' is not present!" + style.END)
        exit(1)

#################################################################################################################
# getGroupMembers Function:
# Get get members for a specific address group ID
#################################################################################################################
def getGroupMembers(ssoSession,spaceURL,groupID,membersList):
    apiURI = "/api/juniper/sd/address-management/addresses"
    url = spaceURL + apiURI + "/{0}".format(groupID)
    headers = {'Accept': 'application/vnd.juniper.sd.address-management.address+json;version=1;q=0.01'}
    try:
        groupMemResponse = requests.get(url, headers=headers, cookies=ssoSession.cookies, verify=False)
        groupMemResponse.raise_for_status()
        edit_version = groupMemResponse.json()['address']['edit-version']
        members = groupMemResponse.json()['address']['members']['member']
        existing_address_members = [member['id'] for member in members]
        addressMembers = existing_address_members

        # Add New Address To Group Member List (If Not Aleady A Member)
        for objID in membersList:
            if objID not in addressMembers:
                addressMembers = addressMembers + [objID]
        return edit_version, addressMembers, existing_address_members

    except requests.exceptions.RequestException as e:
        raise SystemExit(e)  

#################################################################################################################
# addAddresstObject Function:
# Add a host IP address object
#################################################################################################################
def addAddressObject(ssoSession,spaceURL,ip,addressType,timeStamp):
    # Render the jinja template
    payload = Template(open('add_address.j2').read()).render(ipAddress=ip, addressType=addressType, timeStamp=timeStamp)
    apiURI = "/api/juniper/sd/address-management/addresses"
    url = spaceURL + apiURI
    headers = {'content-type': 'application/vnd.juniper.sd.address-management.address+json;version=1;charset=UTF-8'}
    try:
        addHostResponse = requests.post(url, headers=headers, data=payload, cookies=ssoSession.cookies, verify=False)
        addHostResponse.raise_for_status()

    except requests.exceptions.RequestException as e:
        raise SystemExit(e)

#################################################################################################################
# renderGroupModPayload Function:
# Render the jinja payload for the group modification
#################################################################################################################
def renderGroupModPayload(AddressGroupName, edit_version, addressMembers, groupID):
    groupPayload = Template(open('modify_address_group.j2').read()).render(
        address_group_name=AddressGroupName,
        edit_version=edit_version,
        address_members=addressMembers,
        group_id=groupID
        )
    return groupPayload

#################################################################################################################
# modAddressGroup Function:
# Modify the address group with the updated information from groupPayload
#################################################################################################################
def modAddressGroup(ssoSession,spaceURL,groupPayload, groupID):
    apiURI = "/api/juniper/sd/address-management/addresses"
    url = spaceURL + apiURI + "/{0}".format(groupID)
    headers = {
                'content-type': 'application/vnd.juniper.sd.address-management.address+json;version=1;charset=UTF-8',
                'accept-type':  'application/vnd.juniper.sd.address-management.address+json;version=1;q=0.01'
    }
    try:
        put_address_group_response = requests.put(url, headers=headers, data=groupPayload, cookies=ssoSession.cookies, verify=False)
        put_address_group_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)


##############################
# Main
##############################
print(style.BOLD + "=============================================================" + style.END)
print(style.BOLD + " Update Blocklist in Security Director" + style.END)
print(style.BOLD + "=============================================================" + style.END)
parser = argparse.ArgumentParser(description='Update Blocklist on Security Director')
parser.add_argument("-f", "--file", required=True, type=str, help="File that contains the IPs/subnets")
parser.add_argument("-u", "--user", required=True, type=str, help="Login name for Security Director")
args = parser.parse_args()

# Prompt for password
print("Enter password for user '{0}': ".format(args.user))
passwd = getpass()
auth = (args.user, passwd)

# Create initial login session with Space/SD
print("- Creating SSO Session with Space/SD")
try:
    ssoSession = requests.post(loginURI, headers=headers, auth=auth, verify=False)
    ssoSession.raise_for_status()
    # Save session cookies to local dict
    cookies['JSESSIONID'] = ssoSession.cookies['JSESSIONID']
    cookies['JSESSIONIDSSO'] = ssoSession.cookies['JSESSIONIDSSO']
except requests.exceptions.RequestException as e:
    raise SystemExit(e)

# Check to see if the provided address group exists
print("- Getting Object ID of " + AddressGroupName + "...")
groupID = getGroupID(ssoSession,spaceURL,AddressGroupName);

# Read in IP addresses from file
ipList = readBlockList()

print("- Processing IP List...")
for ip in ipList:
    
    print("    + {:20s} :".format(ip), end = "")
    # Separate subnets & hosts and verify
    # Find subnet, if entry contains a /
    if ip.find(backSlash) != -1:
        try:
            verifiedIP = ipaddress.ip_network(ip, strict=True)
            print(style.GREEN + "Format=passed | " + style.END,end = "")
            objectID = searchSDbyIP(ssoSession,spaceURL,verifiedIP)
            addressType = "NETWORK"
            if objectID == "add":
                print(style.ORANGE + "New", end = "")
                addAddressObject(ssoSession,spaceURL,verifiedIP,addressType,timeStamp)
                newObjectID = searchSDbyIP(ssoSession,spaceURL,verifiedIP)
                print("(" + str(newObjectID) + ")" + style.END)
                membersList.append(newObjectID)
            else:
                print(style.YELLOW + "Existing(" + str(objectID) + ")" + style.END)
                membersList.append(objectID)

        except ValueError as e:
            print(style.RED + "Format=ERROR: " + str(e) + style.END)
            badIpList.append(ip)
    # All other entries should be hosts
    else:
        try:
            verifiedIP = ipaddress.ip_address(ip)
            print(style.GREEN + "Format=passed | " + style.END,end = "")
            objectID = searchSDbyIP(ssoSession,spaceURL,verifiedIP)
            addressType = "IPADDRESS"
            if objectID == "add":
                print(style.ORANGE + "New", end = "")
                addAddressObject(ssoSession,spaceURL,verifiedIP,addressType,timeStamp)
                newObjectID = searchSDbyIP(ssoSession,spaceURL,verifiedIP)
                print("(" + str(newObjectID) + ")" + style.END)
                membersList.append(newObjectID)
            else:
                print(style.YELLOW + "Existing(" + str(objectID) + ")" + style.END)
                membersList.append(objectID)

        except ValueError as e:
            print(style.RED + "Format=ERROR: " + str(e) + style.END)
            badIpList.append(ip)

print("- New member ID list to add to group...")
print("   + Current number of members: ", len(membersList))

print("- Current Objects in " + AddressGroupName + "...")
edit_version, addressMembers, existingMembers = getGroupMembers(ssoSession,spaceURL,groupID,membersList)
print("   + Current number of members: ", len(existingMembers))

# Update addressbook entry with new memberList
print("- Updating " + AddressGroupName + " with new entries...")
if len(addressMembers) >= 1024:
    print(style.RED + "   !! Address Group Object count exceeds 1024 which could be problematic for some branch SRX devices." + style.END)
else:
    print("   + Total member list is less than 1024")

groupPayload = renderGroupModPayload(AddressGroupName, edit_version, addressMembers, groupID)
modAddressGroup(ssoSession,spaceURL,groupPayload, groupID)

print("- Closing SSO session")
try:
    ssoClose = requests.post(logoutURI, headers=headers, cookies=ssoSession.cookies, verify=False)
    ssoClose.raise_for_status()
except requests.exceptions.RequestException as e:
    raise SystemExit(e)

print("")
print("=============================== C O M P L E T E ==================================")
print(" The address group has been updated with the IPs from the text file. Login")
print(" to Security Director and verify the additions to the " + AddressGroupName)
print(" address group. Once satisified, push the updates to the firewalls.")
print(" ")
if len(badIpList) >= 1:
    print(" !!! NOTE: The following IP addresses had bad formatting and were NOT added:")
    for ip in badIpList:
        print("    - " + ip)

## End of Script ##
