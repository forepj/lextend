# lextend

lextend is a generic, UDP based home automation gateway. Any system, device or tool which is able to send and receive
UDP packets can use the features implemented by lextend.

Currently the following feature is implemented: 
Sonos Gateway (Sonos Soundsystem can be controlled by sending UDP packets by any system, device or tool. Based on this, the Sonos multiroom soundsystem can be used as doorbell, security alarm system, text to speech etc.)

All the features of lextend can be controlled by a web interface and the settings are saved in an XML file, which can be easily extended for additional lextend features.

## Installation

* Make sure you are in a python2 environment.
* Install dependencies using: pip install -r requirements.txt

## UDP Protocol definition

See protocol.txt

## Usage

You can run lextend by just executing run_lextend_engine.py.

You can start the web frontend with run_lextend_webfrontend.py

## Contributing

1. Fork it!
2. Create your feature branch: `git checkout -b my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin my-new-feature`
5. Submit a pull request :D

## License

The lextend package is made available under the terms of the GNU Public License v3 (or any higher version at your choice). See the file COPYING for the licensing terms for all modules.

