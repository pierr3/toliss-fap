# Development notes

## Repository layout

```
src/            C++ plugin (fap.cpp, audio.cpp, json_mini.h)
third_party/    minimp3 (CC0 MP3 decoder, header-only)
html/           the FAP page (index.html) + img/screen_off_default.png
obj/            fap_hw.obj (+ textures) and fap_screen.obj, both generated
sounds/         shipped CC0 / public-domain audio (chimes, music)
installer/      Install-FAP.ps1 + the two .bat launchers
tools/          asset generators + package.ps1
sdk/            X-Plane SDK 4.x headers and Windows libs (own license)
docs/           user guide, this file, screenshots
```

## Building (Windows)

1. Install Visual Studio 2019 or newer with the **Desktop development with C++** workload.
2. Run `build.bat`. It finds Visual Studio through `vswhere` and produces `build\ToLissFAP.xpl`.
3. Run `powershell -File tools\package.ps1`. It produces `dist\ToLissFAP-<version>\` and the release zip.
4. Run `dist\ToLissFAP-<version>\Install FAP.bat`, or install from the command line:

```
powershell -ExecutionPolicy Bypass -File dist\ToLissFAP-<ver>\files\Install-FAP.ps1 [-Aircraft "<A320 or A321 folder>"] [-All] [-PluginOnly] [-Force]
```

- Without `-Aircraft`, it searches the usual X-Plane folders for ToLiss aircraft with the FAP housing (`kitchens.obj`). When it finds several, it asks which ones; `-All` installs into all of them without asking.

- `-PluginOnly` only refreshes `plugins\ToLissFAP` (the fast loop while working on code or HTML).
- `-Force` lets it run while X-Plane is open. A loaded `.xpl` cannot be overwritten, so the installer renames it; reload the aircraft afterwards.
- `-ExtraSounds <dir>` merges a folder of your own sounds into the plugin.

The version number is `FAP_VERSION` in `src/fap.cpp`.

macOS and Linux builds are not done yet. The code only uses the XPLM API and the C++ standard library, so porting should mostly be a build-script job (contributions welcome).

## Working on the page

`html/index.html` is self-contained. When it is opened outside X-Plane, it runs on built-in demo data.

You can choose the start page with the URL hash:
- `index.html#audio,noboot` opens the Audio page and skips the boot screen.
- The page ids are `sts light temp doors water smoke audio calls evac sys cfg caut`.
- Add `a321` (`#doors,noboot,a321`) to preview the A321 "2 OWE + door 3" layout with the demo data.

Inside X-Plane, the page talks to the plugin through functions registered with `XPLMAvionicsAddBrowserFunction`:
- `xplane.getState()` is polled every 250 ms and returns a JSON snapshot (see `state_json()` in `fap.cpp`).
- `xplane.action(json)` sends button presses (see `do_action()`).
- `xplane.log(text)` writes to X-Plane's `Log.txt`.

The plugin pushes 3D-cockpit touches into the page with `XPLMAvionicsInjectScript` as `fapTouch(x, y)`, on mouse-down.

**Performance:**
- The page re-renders from every poll.
- Identical `innerHTML` writes are skipped by a guard at the top of the script. Without it, X-Plane re-uploads the screen texture on every repaint, and clicks could land on elements being replaced.
- Click de-duplication only drops the other source's copy of a click (native vs injected), so fast repeated presses all count.

**Plugins > ToLiss FAP > Reload FAP page** reloads the HTML without restarting the sim.

## Commands

| Command | Action |
|---|---|
| `toliss_fap/toggle_popup` | show/hide the 2D popup |
| `toliss_fap/pop_out` | pop the FAP out into its own OS window |
| `toliss_fap/reload` | reload the page and rescan everything (below) |
| `toliss_fap/rescan_sounds` | rescan the sound folders, reload the chimes and the current livery's FAP content |
| `toliss_fap/toggle_debug_quad` | debug screen floating in the cockpit |
| `toliss_fap/key/emer` | hardware key: EMER call |
| `toliss_fap/key/lights` | hardware key: LIGHTS MAIN ON/OFF |
| `toliss_fap/key/lav_maint` | hardware key: LAV MAINT |
| `toliss_fap/key/screen_lock` | hardware key: SCREEN 30 sec LOCK |
| `toliss_fap/key/evac_cmd` | hardware key: EVAC CMD |
| `toliss_fap/key/evac_reset` | hardware key: EVAC RESET |
| `toliss_fap/key/smoke_reset` | hardware key: SMOKE RESET |
| `toliss_fap/key/cover` | open/close the clear cover over the hardware keys |
| `toliss_fap/keypad/0` ... `9`, `star`, `hash` | flight-deck door keypad: digits build a code, `*` clears it, `#` sends an access request (see below) |

## Datarefs published

| Dataref | Type | Meaning |
|---|---|---|
| `toliss_fap/key_light` | float[8] | key legend light level (0 = EMER, 1..6 = keys): 0.42 backlight with DC power, 1 when the function is active, alerts blink |
| `toliss_fap/key_backlight` | float | door keypad legend backlight: 1 whenever any DC bus is powered |
| `toliss_fap/key_cover` | float | key cover position, 0 closed .. 1 open (animated) |
| `toliss_fap/door_request` | int | 1 while a door-keypad access request is beeping in the cockpit |
| `toliss_fap/hw_lit_off` | float | always 0 (LIT channel for unlit decals) |
| `toliss_fap/water_pct`, `toliss_fap/waste_pct` | float | simulated tank levels |
| `toliss_fap/cabin_ready` | int | cabin ready sent |
| `toliss_fap/cockpit_call` | int | a cabin-to-cockpit call is pending |
| `toliss_fap/debug_quad` | int (rw) | show the debug screen |

## ToLiss datarefs and commands used

All names below are `AirbusFBW/...` unless noted.

**Doors:**
- `PaxDoorModeArray` (0 = CLOSE, 1 = AUTO, 2 = OPEN)
- `PaxDoorArray`, `CargoDoorModeArray`, `CargoDoorArray`, `BulkDoor`, `EmerExitArray`
- Slides: `SlideArmedArray`, `PaxDoorSlidesDeployRatio`, `EmerSlidesDeployRatio`
- Commands: `toliss_airbus/door_commands/*` (all doors to close/auto/open, arm/disarm slides)
- The arrays hold door pairs in slot order (1L 1R 2L 2R ...): 4 slots on the A320 and 8 on the A321, where some slots are dummies depending on the exit configuration.
- A321 exit configuration (`A321ExitConfig`, ToLiss "Cabin Flex"). The plugin only sends the doors and overwing exits that exist (`exit_layout()` in `fap.cpp`):

| Value | Livery setting (`exit_Configuration`) | Doors | Overwing exits per side |
|---|---|---|---|
| 0 | `CLASSIC` | 1 2 3 4 | 0 |
| 1 | `2_OWE` | 1 3 4 | 2 |
| 2 | `1_OWE` | 1 3 4 | 1 |
| 3 | `NO_DOOR_3` | 1 4 | 2 |


**Cabin:**
- Lights: `cabinLightLevel_perc`, `CabinLightLevel`
- Temperature: `FwdCabinTemp`, `AftCabinTemp`, `CabinZone1Temperature_degC`, `CabinZone2Temperature_degC`, `CockpitTemp`, `CockpitTemperature_degC`
- Other: `CabinAlt`, `NoPax`, `SeatBeltSignsOn`, `NoSmokingSignsOn`, `PaxOxyMask`

**Calls and evacuation:**
- `purser/fwd`, `purser/aft`, `purser/all`, `purser/mech`
- `EmerCallOHPButton`, `EmerEvacButton`, `EmerEvacLight`, `EmerEvacCaptPursSelSwitch`, `EvacHornShutOff`

**Cockpit door:**
- `CockpitDoorAngle`, `CockpitDoorLockState`, and `ckpt/door` (used to attenuate the PA in the cockpit)

**Power:**
- `ACBusVoltages` (index 0/1 = AC1/AC2): the screen is on when either is powered, i.e. external power, APU generator or engine generators. It boots for 32 s after every AC loss longer than 2 s (shorter breaks, like a GPU-to-APU transfer, are ignored). Power that is already there when the aircraft loads skips the boot.
- `DCBusVoltages`: any DC bus powered (batteries on) lights the key legends.

**Cockpit door** (keypad access request):
- `CockpitDoorSwitch`: pedestal switch, 0 = UNLOCK, 1 = NORM, 2 = LOCK (probed in the sim: only 2 sets `CockpitDoorLockState`, which is read-only).
- What `#` does:
  1. It beeps in the cockpit for 5 s.
  2. If the switch is still in NORM after that, the plugin moves it to UNLOCK for 5 s, then back to NORM. It only moves it back if nobody touched the switch in between.
  3. If LOCK is selected during the beeps, the request is denied.

**ECAM:**
- `ECAMFlightPhase`
- Command `AirbusFBW/CheckCabin`, which produces the CABIN READY memo

## Why the cockpit OBJ is patched

X-Plane only sends mouse clicks to the **cockpit object** (attachment `_obja/0`).

- **Why not a separate object?** Flagging another object as cockpit makes X-Plane ignore it ("two interior cockpit objects").
- **What gets patched:** the clickable screen (`ATTR_cockpit_device TOLISS_FAP` + `ATTR_manip_device`) and the invisible click boxes (keys, key cover, door keypad) are appended to the user's local cockpit OBJ. The DWSim ATR uses the same approach for its cabin FAP.
- **Re-running the installer:** it always starts again from the pristine copy (`*.fap-original`, path recorded in `*.fapinfo`), so the patch never stacks.
- **ToLiss updates:** when an update installs a fresh OBJ with no FAP block, that fresh OBJ becomes the new original.
- **Animated click zones:** the installer offsets vertices into the cockpit frame but copies animation lines unchanged, so pivots would be wrong. The key cover therefore uses two static click boxes (closed / open) swapped with `ANIM_hide` on `toliss_fap/key_cover`; only the visual cover in `fap_hw.obj` rotates.

The visible 3D hardware (`fap_hw.obj`) is a normal misc object. The installer adds it to every `.acf` that uses the same cockpit, by cloning the `kitchens.obj` attachment.

## 3D asset pipeline

Every asset is generated from code, so it can be reviewed and changed in a diff. Run the steps in this order:

| Step | Script | Output |
|---|---|---|
| 1 | `python tools/build_fap_hw.py` | `obj/fap_hw.obj`, `obj/fap_screen.obj`, preview meshes, `build/bake/fap_bake.obj` (Python 3, no packages) |
| 2 | `python tools/fetch_cc0_textures.py` | CC0 material scans from [ambientCG](https://ambientcg.com) into `build/cc0/` (once) |
| 3 | `blender -b --factory-startup -P tools/bake_fap_ao.py` | `build/bake/ao.png`: ambient occlusion baked with Cycles |
| 4 | `python tools/gen_hw_tex.py` | `obj/fap_hw.png`, `_LIT.png`, `_NML.png` (2048², Pillow + numpy) |
| - | `blender -b --factory-startup -P tools/preview_fap.py -- <abs out dir> [open]` | preview renders (pass an absolute path) |
| - | `tools/gen_screen_off.ps1` | `html/img/screen_off_default.png` |

Steps 2 and 3 are optional: without them `gen_hw_tex.py` falls back to procedural grain and a blurred-footprint shadow.

**Textures:**
- **Colours and legends** are our own.
- **Surface grain** (luminance variation and normals only) comes from the CC0 ambientCG scans Plastic010, Plastic006 and Plastic011. The scans themselves are not committed.
- **Ambient occlusion** darkens the bezel and keypad faces, and gives the transparent contact-shadow decal on the ToLiss housing.

**Real-panel references:**
- The keys are black and only EMER is red. Their legends glow in colour whenever there is DC power: LIGHTS in green, the others in red.
- The clear cover over the keys lifts up from a top hinge (`HINGE` in `build_fap_hw.py`).
- The door keypad sits on the flat right side face of the housing, facing the cockpit door. It is built flat and then mapped onto that face (`to_side`).
- The screen has no dark outline: the glass meets the bezel.

Geometry is expressed in the ToLiss `kitchens.obj` frame and wrapped in the same `1-sim/fus` fuselage-length animation, so it follows the body length.
- **A320 vs A321:** `kitchens.obj` is identical in both.
- **Click-zone shift:** the installer shifts the screen and the click zones into the cockpit-object frame using the attachment offsets read from the `.acf`. The shift is zero on the A320 and 13.97 ft on the A321, where the cockpit is attached at z = 6.78 ft and `kitchens.obj` at 20.75 ft.

## Release

1. Bump `FAP_VERSION` in `src/fap.cpp`.
2. Run `build.bat`.
3. Run `tools\package.ps1`.
4. Attach `dist\ToLissFAP-<version>.zip` to a GitHub release (`gh release upload v<version> dist\ToLissFAP-<version>.zip --clobber`).

## Sound format

- **Format:** WAV (PCM 8/16/24-bit or float) or MP3, mono or stereo, any sample rate. MP3 is decoded with [minimp3](https://github.com/lieff/minimp3) (CC0, vendored in `third_party/minimp3`).
- **Folders:** each folder under `sounds/announcements` becomes a tree node on the Audio page.
- **Multi-language announcements:** use `<NN Name>/<Language>.wav` to group languages under one announcement. The page also tidies names for display: underscores become spaces, and a file named like its folder plus a language code (`08_after_landing/after_landing_en.mp3`) is shown as the language ("English").
- **Updates keep user sounds:** the installer only adds sound files that are not there yet.
- **Shipped audio:** only CC0 or public-domain sounds go into `sounds/`. Never commit audio you cannot redistribute. Personal sound packs belong outside the repo; use `-ExtraSounds` to install them.
