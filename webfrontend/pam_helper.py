# Lextend
# Copyright (c) 2014-2015 Egger Enertech <http://www.egger-enertech.ch>
# Released under the GNU Public License 3 (or higher, your choice)
# See the file COPYING for details.

import pam

def pam_auth(username, password):
  ''' Accepts username and password and tried to use PAM for authentication.
    Works only with root privileges
  '''
  return pam.authenticate(username, password, service="system-auth")
  try:
    return pam.authenticate(username, password, service="system-auth")
  except:
    return False
