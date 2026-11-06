# ToLiss FAP: Flight Attendant Panel for the ToLiss A320 and A321

A working Airbus CIDS **Flight Attendant Panel** for the ToLiss A320 and A321 in X-Plane 12.
It sits on the forward-entry wall behind the cockpit. You can click it in 3D or open it as a popup or a separate window.

![The FAP on the forward galley wall, Audio page, in the sim](docs/img/sim_cockpit.jpg)

> [!NOTE]
> This is a free community add-on. It is **not affiliated with ToLiss or Airbus**.
> No ToLiss files are shipped. The installer patches the copy on your own machine and always makes backups first.

**Video:** coming soon.

## Features

- **CIDS-style touch screen**, built with X-Plane 12's browser avionics (HTML/JS rendered by X-Plane's built-in browser and driven by a C++ plugin):
  - Cabin Status overview
  - Cabin Lighting
  - Doors / Slides
  - Temperature
  - Water / Waste
  - Smoke Detection
  - Audio
  - Calls
  - Evacuation
  - System Info
  - FAP Config
  - Caution list
- **Hooked into the ToLiss systems:**
  - Door modes (Close / Auto / Open), including cargo doors
  - A321 exit configurations (classic 4 doors and the three "Cabin Flex" overwing-exit layouts): the Doors page shows the doors and exits of the current configuration
  - Cabin light level
  - Forward and aft cabin temperature (the cockpit knobs move with it)
  - The **Cabin Ready** button raises *CABIN READY* on the ECAM.
- **Audio:**
  - Boarding music with channels and volume
  - Real A320 chimes: hi, lo, hi-lo and tri-tone
  - Prerecorded announcements in a folder tree, with a MEMO queue, Play Next and Play All
  - Cabin PA is quieter in the cockpit and depends on whether the cockpit door is open.
- **Realistic power-up:** the keys are backlit as soon as the batteries are on. The screen needs AC power (ground power, APU or engines) and runs a CIDS start-up sequence first.
- **3D panel hardware**:
  - Metal bezel set into the ToLiss FAP housing, with baked ambient occlusion
  - Black keys with colour-backlit legends (brighter or blinking when active): EMER, LIGHTS MAIN ON/OFF, LAV MAINT, SCREEN LOCK, EVAC CMD/RESET, SMOKE RESET
  - Clear lift-up cover over the keys: open it before pressing them
  - USB port
  - Flight-deck door keypad on the panel edge: enter a code and press # to make it beep in the cockpit. If the pedestal COCKPIT DOOR switch is in NORM, the door unlocks after 5 s (LOCK denies entry).
  - Night lighting matched to the ToLiss cabin
  - Screen brightness follows the ambient light.
- **Per-livery content:** a livery can bring its own boarding music, announcements and screen-off image.
- **Plugins menu:**
  - Show/hide the popup
  - Pop out into its own window (second monitor)
  - Rescan sounds
  - Reload the page

| | |
|---|---|
| ![Cabin status](docs/img/page_sts.png) | ![Audio](docs/img/page_audio.png) |
| ![Doors](docs/img/page_doors.png) | ![Lighting](docs/img/page_light.png) |
| ![The panel and the cockpit door keypad in the sim](docs/img/sim_panel.jpg) | ![Night lighting in the sim](docs/img/sim_lighting.jpg) |

## Install

**Just want to fly?** Read the [User Guide](docs/USER_GUIDE.md). In short:

1. Download the latest zip from [Releases](../../releases).
2. Close X-Plane.
3. Unzip the download.
4. Double-click **`Install FAP.bat`**.

**Requirements:**
- Windows 10/11
- X-Plane **12.4+** (needed for the browser avionics API)
- ToLiss A320 (Neo) and/or ToLiss A321 (Neo/LR). The installer finds both and asks which ones to install into.

**After every ToLiss update,** run the installer again. ToLiss updates replace the cockpit object and the `.acf`.

**To uninstall,** run `Uninstall FAP.bat`. It restores the original cockpit object and `.acf` attachments.

## How it works

| Piece | What it does |
|---|---|
| `src/fap.cpp` | X-Plane plugin. Creates a browser avionics device (`XPLMCreateAvionicsEx`, `xplm_WindowContentTypeBrowser`) that loads `html/index.html`. It exposes `xplane.getState` / `xplane.action` to the page, reads and writes the ToLiss datarefs, and runs the commands, chimes and sound playback. |
| `src/audio.cpp` | Small WAV mixer on top of X-Plane's FMOD sound API (`XPLMSound`). |
| `html/index.html` | The whole FAP UI: one self-contained page with no external dependencies. Open it in a desktop browser to preview it with demo data. |
| `obj/fap_screen.obj` | Screen surface (`ATTR_cockpit_device`) and click zones. In X-Plane only the cockpit object receives clicks, so the installer appends this to your local ToLiss cockpit OBJ. The original is kept as `*.fap-original`. |
| `obj/fap_hw.*` | Our own 3D model of the panel hardware with albedo, LIT and normal textures, attached as an extra object in the `.acf`. |
| `installer/Install-FAP.ps1` | Install, update and uninstall. Plain Windows PowerShell 5.1 with nothing else to install. Every file it touches gets a timestamped `.fapbak-*` backup. |

Commands, datarefs, the build and the asset pipeline are covered in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Adding sounds

Supported audio is `.wav` or `.mp3`.

- **Your own sounds:** drop the files into `plugins/ToLissFAP/sounds/music` or `sounds/announcements`.
- **Per-livery content:** see [LIVERY_FAP.txt](LIVERY_FAP.txt).
- **Livery painters:** you are welcome to ship a `FAP/` folder with your livery.

## Contributing

Issues and pull requests are welcome. These would help most:
- A321 support
- macOS and Linux builds
- More pages and system hooks
- Translations

## License

- **Code, UI and 3D model:** [GPL-3.0-or-later](LICENSE).
- **Shipped audio:** public domain / CC0. Details in [sounds/CREDITS.txt](sounds/CREDITS.txt).
- **Texture grain:** derived from CC0 material scans by [ambientCG](https://ambientcg.com) (Plastic006, Plastic010, Plastic011).
- **MP3 decoder:** [minimp3](https://github.com/lieff/minimp3), CC0, in `third_party/minimp3`.
- **X-Plane SDK headers and libraries** in `sdk/`: their own permissive license ([sdk/license.txt](sdk/license.txt)).
- **Trademarks:** ToLiss, Airbus and X-Plane belong to their owners and are used here only to describe compatibility.
