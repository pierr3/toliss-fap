# Development notes

## Repository layout

```
src/            C++ plugin (fap.cpp, audio.cpp, json_mini.h)
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
powershell -ExecutionPolicy Bypass -File dist\ToLissFAP-<ver>\files\Install-FAP.ps1 -Aircraft "<A320 folder>" [-PluginOnly] [-Force]
```

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

Inside X-Plane, the page talks to the plugin through functions registered with `XPLMAvionicsAddBrowserFunction`:
- `xplane.getState()` is polled every 250 ms and returns a JSON snapshot (see `state_json()` in `fap.cpp`).
- `xplane.action(json)` sends button presses (see `do_action()`).
- `xplane.log(text)` writes to X-Plane's `Log.txt`.

The plugin pushes 3D-cockpit touches into the page with `XPLMAvionicsInjectScript` as `fapTouch(x, y)`.

**Plugins > ToLiss FAP > Reload FAP page** reloads the HTML without restarting the sim.

## Commands

| Command | Action |
|---|---|
| `toliss_fap/toggle_popup` | show/hide the 2D popup |
| `toliss_fap/pop_out` | pop the FAP out into its own OS window |
| `toliss_fap/reload` | reload the page and rescan sounds |
| `toliss_fap/rescan_sounds` | rescan sound folders |
| `toliss_fap/toggle_debug_quad` | debug screen floating in the cockpit |
| `toliss_fap/key/emer` | hardware key: EMER call |
| `toliss_fap/key/lights` | hardware key: LIGHTS MAIN ON/OFF |
| `toliss_fap/key/lav_maint` | hardware key: LAV MAINT |
| `toliss_fap/key/screen_lock` | hardware key: SCREEN 30 sec LOCK |
| `toliss_fap/key/evac_cmd` | hardware key: EVAC CMD |
| `toliss_fap/key/evac_reset` | hardware key: EVAC RESET |
| `toliss_fap/key/smoke_reset` | hardware key: SMOKE RESET |

## Datarefs published

| Dataref | Type | Meaning |
|---|---|---|
| `toliss_fap/key_light` | float[8] | hardware key indicator bars, lit when the key's function is active (0 = EMER) |
| `toliss_fap/key_backlight` | float | key legend backlight: 1 whenever any DC bus is powered |
| `toliss_fap/hw_lit_off` | float | always 0 (LIT channel for unlit decals) |
| `toliss_fap/water_pct`, `toliss_fap/waste_pct` | float | simulated tank levels |
| `toliss_fap/cabin_ready` | int | cabin ready sent |
| `toliss_fap/cockpit_call` | int | a cabin-to-cockpit call is pending |
| `toliss_fap/debug_quad` | int (rw) | show the debug screen |

## ToLiss datarefs and commands used

All names below are `AirbusFBW/...` unless noted.

**Doors:**
- `PaxDoorModeArray` (0 = CLOSE, 1 = AUTO, 2 = OPEN; indices L1, R1, L2, R2)
- `PaxDoorArray`, `CargoDoorModeArray`, `CargoDoorArray`, `BulkDoor`, `EmerExitArray`
- Slides: `SlideArmedArray`, `PaxDoorSlidesDeployRatio`, `EmerSlidesDeployRatio`
- Commands: `toliss_airbus/door_commands/*` (all doors to close/auto/open, arm/disarm slides)

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

**ECAM:**
- `ECAMFlightPhase`
- Command `AirbusFBW/CheckCabin`, which produces the CABIN READY memo

## Why the cockpit OBJ is patched

X-Plane only sends mouse clicks to the **cockpit object** (attachment `_obja/0`).

- **Why not a separate object?** Flagging another object as cockpit makes X-Plane ignore it ("two interior cockpit objects").
- **What gets patched:** the clickable screen (`ATTR_cockpit_device TOLISS_FAP` + `ATTR_manip_device`) and the invisible key click boxes are appended to the user's local cockpit OBJ. The DWSim ATR uses the same approach for its cabin FAP.
- **Re-running the installer:** it always starts again from the pristine copy (`*.fap-original`, path recorded in `*.fapinfo`), so the patch never stacks.
- **ToLiss updates:** when an update installs a fresh OBJ with no FAP block, that fresh OBJ becomes the new original.

The visible 3D hardware (`fap_hw.obj`) is a normal misc object. The installer adds it to every `.acf` that uses the same cockpit, by cloning the `kitchens.obj` attachment.

## 3D asset pipeline

Every asset is generated from code, so it can be reviewed and changed in a diff.

| Script | Output |
|---|---|
| `tools/build_fap_hw.py` | `obj/fap_hw.obj`, `obj/fap_screen.obj`, Blender preview meshes (Python 3, no packages) |
| `tools/gen_hw_tex.ps1` | `obj/fap_hw.png` + `obj/fap_hw_LIT.png` (texture atlas, System.Drawing) |
| `tools/gen_hw_nml.py` | `obj/fap_hw_NML.png` (normal map) |
| `tools/gen_screen_off.ps1` | `html/img/screen_off_default.png` |
| `tools/preview_fap.py` | Blender 4.x headless preview renders (`blender -b --factory-startup -P tools/preview_fap.py -- <out>`) |

Geometry is expressed in the ToLiss `kitchens.obj` frame and wrapped in the same `1-sim/fus` fuselage-length animation, so it follows the body length. The installer shifts the screen into the cockpit-object frame using the attachment offsets read from the `.acf`.

## Sound format

- **Format:** 16-bit PCM WAV, mono or stereo, any sample rate.
- **Folders:** each folder under `sounds/announcements` becomes a tree node on the Audio page.
- **Multi-language announcements:** use `<NN Name>/<Language>.wav` to group languages under one announcement.
- **Shipped audio:** only CC0 or public-domain sounds go into `sounds/`. Never commit audio you cannot redistribute. Personal sound packs belong outside the repo; use `-ExtraSounds` to install them.
