ToLiss FAP - USER GUIDE
=======================

This adds a working Flight Attendant Panel (FAP) to the ToLiss A320 in X-Plane 12.
It sits on the wall at the front door, behind the cockpit.


WHAT YOU NEED
-------------
- Windows 10 or 11
- X-Plane 12.4 or newer
- The ToLiss A320 (Neo)


INSTALL (2 minutes)
-------------------
1. Close X-Plane.
2. Unzip the download anywhere (your Desktop is fine).
3. Double-click  "Install FAP.bat".
4. If it asks, pick your ToLiss A320 folder
   (example: X-Plane 12\Aircraft\ToLissA320_V1p2p1).
5. Wait for "Done!". Press a key to close the window.
6. Start X-Plane and load the A320.

Windows might say "Windows protected your PC". Click "More info", then "Run anyway".


USE IT
------
- Walk to the front door (behind the cockpit). The FAP is on the wall.
- Click the screen. It works like a touch screen.
- Can't be bothered to walk? Menu: Plugins > ToLiss FAP > Show / hide FAP popup.
- Want it on a second monitor? Menu: Plugins > ToLiss FAP > Pop out FAP.

The buttons at the bottom of the screen switch pages:

  Audio ........ boarding music, chimes, announcements
  Lights ....... cabin lights
  Door/Slides .. open and close doors, arm/disarm slides
  Temp ......... cabin temperature
  Water/Waste .. tank levels
  Smoke Detect . smoke alarms
  ▶ ............ more pages (calls, evacuation, ...)
  Cabin Ready .. tells the pilots the cabin is ready (shows CABIN READY on the ECAM)
  Screen Off ... turns the screen off


PLAY BOARDING MUSIC
-------------------
1. Press "Audio".
2. Pick a song in the list.
3. Press "ON/OFF".


PLAY AN ANNOUNCEMENT
--------------------
1. Press "Audio".
2. Pick an announcement on the right.
3. Press "Direct Play".

To queue several: pick one, press the ← arrow to add it to MEMO, repeat,
then press "Play All".


ADD YOUR OWN SOUNDS
-------------------
Put .wav files here (inside your A320 folder):

  plugins\ToLissFAP\sounds\music            <- boarding music
  plugins\ToLissFAP\sounds\announcements    <- announcements

Then press "Rescan" on the FAP Config page (or restart).
Only 16-bit .wav files work. Convert mp3 files with any free audio converter.

Sounds for one livery only: see LIVERY_FAP.txt in plugins\ToLissFAP.


AFTER A TOLISS UPDATE
---------------------
ToLiss updates replace the files the FAP needs. Just double-click
"Install FAP.bat" again.


UNINSTALL
---------
Close X-Plane and double-click "Uninstall FAP.bat".
Everything is put back the way it was.
(Sounds you added in plugins\ToLissFAP are deleted too. Keep a copy if you want them.)


SOMETHING IS WRONG
------------------
- The screen is black: like the real one, the FAP needs ground power, the APU
  generator or the engines running. Batteries alone only light the keys.
  When power comes on, the FAP takes about 30 seconds to start.
- The screen shows a picture: it is switched off ("Screen Off"). Click it to wake it up.
- I can't click the screen: run "Install FAP.bat" again, then reload the aircraft.
- No sound: check the volume bar on the Audio page, and X-Plane's sound settings.
- Still broken: open an issue on GitHub and attach X-Plane 12\Log.txt.
