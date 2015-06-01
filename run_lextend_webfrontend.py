#!/usr/bin/env python2

# Lextend
# Copyright (c) 2014-2015 Egger Enertech <http://www.egger-enertech.ch>
# Released under the GNU Public License 3 (or higher, your choice)
# See the file COPYING for details.


import os
import time
from flask import Flask, render_template, request, session, url_for, redirect
from werkzeug.utils import secure_filename

from configuration import ConfigManager
from webfrontend import pam_helper

from utils.settings import *
from utils.sounds_utils import *
from utils.ip_utils import *

import rpyc

import ipaddress

import threading

import logging
import logging.handlers

logger = logging.getLogger()
LOG_FILENAME = "/var/log/lextend.webfrontend.log"
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, mode="a",
                                               maxBytes=1024*1024*1,
                                               backupCount=5)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
handler.setLevel(logging.INFO)
if logger.handlers:
  for handler in logger.handlers:
    logger.removeHandler(handler)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

logger.info("Starting Lextend Webfrontend.")

app = Flask(__name__, static_folder="webfrontend/static",
                      template_folder="webfrontend/templates/")

@app.route("/", methods=['GET', 'POST'])
def root():
  """ Website entry point. Redirect to signin page to check credentials.
  """
  return redirect(url_for("signin"))

@app.route("/services", methods = ['GET', 'POST'])
def services():
  """ Services page, this is the main page after login.
  """
  if not "username" in session:
    return redirect(url_for("signin"))

  return render_template("services.html")

@app.route("/settings/sonos_doorbell", methods=['GET', 'POST'])
def settings_sonos_doorbell():
  """ Settings page.
  """

  if not "username" in session:
    return redirect(url_for("signin"))

  cfg = app.config["cfg"]
  soundsManager = app.config["soundsManager"]

  # Connect to the RPC server
  remote_sonosPoolManager = None
  try:
    conn = rpyc.connect(RPC_IP, RPC_PORT)
    remote_sonosPoolManager = conn.root.get_sonosPoolManager()
  except:
    logger.error("Could not connect to RPC server.")

  if request.method == 'POST':
    rf = request.form               # just a shortcut

    try:
      action = request.form["action"]
    except:
      action = ""

    if "Save" == action:
      try:
        value = rf["sonos_doorbell.enable"]
        cfg.sonos_doorbell.enable = True if "on" == value else False
      except: pass
      try:
        value = rf["sonos_doorbell.volume_override"]
        cfg.sonos_doorbell.volume_override = True if "on" == value else False
      except: pass
      try:
        value = int(rf["sonos_doorbell.volume"])
        if value >= 0 and value <= 100:
          cfg.sonos_doorbell.volume = value
      except: pass
      try:
        value = int(rf["sonos_doorbell.default_sound"])
        # 0 = no override
        if value >= 0 and value <= 10:
          cfg.sonos_doorbell.default_sound = value
      except: pass
      try:
        cfg.sonos_doorbell.protocol = str(rf["protocol"])
      except: pass

      # Handle files
      for i in range(1, 10):
        to_delete_file = "delete_sound_file_%s" % i
        if to_delete_file in rf:
          soundsManager.delete_file_by_index(i)
          cfg.sonos_doorbell.sounds_filelist[i-1] = "default sound"
        else:
          try:
            file = request.files["sound_file_%s" % i]
            if file:
              filename = secure_filename(file.filename)
              cfg.sonos_doorbell.sounds_filelist[i-1] = filename
              soundsManager.delete_file_by_index(i)
              file.save(soundsManager.create_upload_path(i, filename))
          except:
            logger.error("Could not upload file : %s." % file.filename)

      cfg.save()
    elif "Reset" == action:
      for i in range(1, 10):
        soundsManager.delete_file_by_index(i)

      cfg.reset_sonos_doorbell()
    elif "Discover" == action:
      try:
        remote_sonosPoolManager.discover()
      except:
        logger.error("Could not run sonos discovery.", exc_info=True)
    else:
      logger.error("Unknown post action : %s" % action)

  sonos_list = None
  try:
    logger.info("Sonos devices list : " % remote_sonosPoolManager.devices_list)
    sonos_list = remote_sonosPoolManager.devices_list
  except:
    logger.error("Could not get sonos devices list.")

  return render_template("/settings/sonos_doorbell.html", cfg=cfg, sonos_list=sonos_list)

@app.route("/settings/general", methods = ['GET', 'POST'])
def settings_general():
  if not "username" in session:
    return redirect(url_for("signin"))

  cfg = app.config["cfg"]

  require_reboot = False
  if request.method == 'POST':
    rf = request.form               # just a shortcut

    try:
      action = request.form["action"]
    except:
      action = ""

    if "Save" == action:
      try:
        value = str(rf["lextend.ip"])
        new = ipaddress.ip_address(unicode(value))
        if ipaddress.ip_address(unicode(cfg.general.lextend.ip)) != new:
          cfg.general.lextend.ip = str(new)
          change_ip_address(new)
          require_reboot = True
      except: pass
      try:
        value = int(rf["lextend.port"])
        if value < 1 or value > 65535: raise Exception()
        if value != cfg.general.lextend.port:
          require_reboot = True
        cfg.general.lextend.port = value
      except: pass
      try:
        value = str(rf["miniserver.ip"])
        new = ipaddress.ip_address(unicode(value)) # Validate ip address
        cfg.general.miniserver.ip = str(new)
      except: pass
      try:
        value = int(rf["miniport.port"])
        if value < 1 or value > 65535: raise Exception()
        cfg.general.miniserver.port = value
      except: pass

      cfg.save()

    elif "Reset" == action:
      cfg.reset_general()
      require_reboot = True         # Always reboot, no change check is done.

    if require_reboot:
      def reboot():
        logger.info("rebooting in 4 seconds ...")
        time.sleep(4)
        logger.info("rebooting now")
        os.system("reboot")

      threading.Thread(target=reboot).start()

  return render_template("/settings/general.html", cfg=cfg, require_reboot=require_reboot)

@app.route("/signin", methods = ['GET', 'POST'])
def signin():
  """ Signin page
  """

  def goto_page_after_login():
    return redirect(url_for("services"))

  if request.method == "POST":
    rf = request.form               # just a shortcut
    username = rf["username"]
    password = rf["password"]

    # username = "" => false authentication, could be used for dev.
    if not DEBUG_ENABLE_EMPTY_AUTH:
      if username == "":
        return render_template("signin.html", error=True)
    if pam_helper.pam_auth(username, password):
      session["username"] = username
      return goto_page_after_login()
    else:
      return render_template("signin.html", error=True)
  elif request.method == "GET":
    if "username" in session:
      return goto_page_after_login()
    else:
      return render_template("signin.html", error=False)

@app.route("/signout")
def signout():
  """ Signout page
  """

  if "username" not in session:
    return redirect(url_for("signin"))

  session.pop("username", None)
  return redirect(url_for("root"))

def main():
  # Create and add ConfigManager and SoundsManager to app global space.
  try:
    local_ip = get_local_ip()
  except:
    local_ip = ""
  app.config["cfg"] = ConfigManager(CONFIGURATION_SUBDIRECTORY,
                                    CONFIGURATION_FILENAME,
                                    lextend_ip = local_ip)
  app.config["soundsManager"] = SoundsManager(CONFIGURATION_SUBDIRECTORY)

  # Create and run the web app.
  app.secret_key                   = "Ag~EpxZ3&,h28fA.Ze;iZ1EO,F4e5dRZ)"
  app.debug                        = FLASK_DEBUG
  app.config['MAX_CONTENT_LENGTH'] = FLASK_MAX_UPLOAD_SIZE
  app.run(host=SERVER_ADDRESS,
          port=SERVER_PORT,
          use_reloader=FLASK_USE_RELOADER)

if __name__ == "__main__":
  main()
