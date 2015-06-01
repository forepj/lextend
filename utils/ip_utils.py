# Lextend
# Copyright (c) 2014-2015 Egger Enertech <http://www.egger-enertech.ch>
# Released under the GNU Public License 3 (or higher, your choice)
# See the file COPYING for details.

import netifaces as ni
import fileinput
import shutil

def get_local_ip():
  """ Returns the first IP address.
  Returns:
    ip_address (str) : ip address if found, "" elsewhere.
  """
  interfaces = ni.interfaces()
  ethernet_interface = ""
  ipv4_address = ""
  for interface in interfaces:
    if "eth" in interface or "enp" in interface:
      ethernet_addresses = ni.ifaddresses(interface)
      if 2 in ethernet_addresses:
        ipv4_address = ethernet_addresses[2][0]["addr"]
        break

  return ipv4_address

def change_ip_address(new_ip_address):
  """ Changes the ip address in /etc/network/interfaces file.
  A backup file is created before .
  """
  src_file = "/etc/network/interfaces"
  # Create a backup, don't use .bak, overwritten by fileinput
  shutil.copyfile(src_file, src_file + ".backup")
  eth_found = False
  for line in fileinput.input(src_file, inplace=True):
    if "eth" in line:
      eth_found = True
    if eth_found:
      if "address" in line and "hwaddress" not in line:
        position = line.find("address")
        line = line[:position] + "address %s" % str(new_ip_address)
        print line
        continue
    print line,
