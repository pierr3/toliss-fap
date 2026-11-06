// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 pierr3 and ToLiss FAP contributors
// ToLiss FAP - Flight Attendant Panel for the ToLiss A320/A321 family.
// Creates a CEF browser avionics device (X-Plane 12.4.4 / SDK 440) whose page
// (html/index.html) talks to this plugin through xplane.getState() / xplane.action().

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <map>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "XPLMDataAccess.h"
#include "XPLMDisplay.h"
#include "XPLMMenus.h"
#include "XPLMPlugin.h"
#include "XPLMProcessing.h"
#include "XPLMUtilities.h"
#include "audio.h"
#include "json_mini.h"

namespace fs = std::filesystem;
using fap_audio::Chime;

#define FAP_VERSION "0.1.0"
#define DEVICE_ID "TOLISS_FAP"

static const int kScreenW = 1100;
static const int kScreenH = 840;

// ---------------------------------------------------------------------------
// logging
static void logf(const char* fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf - 2, fmt, ap);
    va_end(ap);
    std::string s = std::string("ToLissFAP: ") + buf + "\n";
    XPLMDebugString(s.c_str());
}

// ---------------------------------------------------------------------------
// Dataref wrapper (lazy, type-aware)
struct DR {
    const char* name;
    XPLMDataRef ref = nullptr;
    XPLMDataTypeID type = 0;
    explicit DR(const char* n) : name(n) {}
    bool ok() {
        if (!ref) {
            ref = XPLMFindDataRef(name);
            if (ref) type = XPLMGetDataRefTypes(ref);
        }
        return ref != nullptr;
    }
    float f(float def = 0) {
        if (!ok()) return def;
        if (type & xplmType_Float) return XPLMGetDataf(ref);
        if (type & xplmType_Double) return (float)XPLMGetDatad(ref);
        if (type & xplmType_Int) return (float)XPLMGetDatai(ref);
        if (type & xplmType_FloatArray) { float v = def; XPLMGetDatavf(ref, &v, 0, 1); return v; }
        if (type & xplmType_IntArray) { int v = (int)def; XPLMGetDatavi(ref, &v, 0, 1); return (float)v; }
        return def;
    }
    int i(int def = 0) { return (int)std::lround(f((float)def)); }
    int size() {
        if (!ok()) return 0;
        if (type & xplmType_FloatArray) return XPLMGetDatavf(ref, nullptr, 0, 0);
        if (type & xplmType_IntArray) return XPLMGetDatavi(ref, nullptr, 0, 0);
        return 1;
    }
    float at(int idx, float def = 0) {
        if (!ok()) return def;
        if (type & xplmType_FloatArray) { float v = def; if (XPLMGetDatavf(ref, &v, idx, 1) < 1) return def; return v; }
        if (type & xplmType_IntArray) { int v = (int)def; if (XPLMGetDatavi(ref, &v, idx, 1) < 1) return def; return (float)v; }
        return idx == 0 ? f(def) : def;
    }
    void set(float v) {
        if (!ok()) return;
        if (type & xplmType_Float) XPLMSetDataf(ref, v);
        else if (type & xplmType_Double) XPLMSetDatad(ref, v);
        else if (type & xplmType_Int) XPLMSetDatai(ref, (int)std::lround(v));
        else set_at(0, v);
    }
    void set_at(int idx, float v) {
        if (!ok()) return;
        if (type & xplmType_IntArray) { int x = (int)std::lround(v); XPLMSetDatavi(ref, &x, idx, 1); }
        else if (type & xplmType_FloatArray) XPLMSetDatavf(ref, &v, idx, 1);
        else if (idx == 0) set(v);
    }
    void reset() { ref = nullptr; type = 0; }
};

// ToLiss
static DR dPaxDoor("AirbusFBW/PaxDoorArray");
static DR dPaxDoorMode("AirbusFBW/PaxDoorModeArray");
static DR dSlideArmed("AirbusFBW/SlideArmedArray");
static DR dSlideDeploy("AirbusFBW/PaxDoorSlidesDeployRatio");
static DR dCargoDoor("AirbusFBW/CargoDoorArray");
static DR dCargoDoorMode("AirbusFBW/CargoDoorModeArray");
static DR dBulkDoor("AirbusFBW/BulkDoor");
static DR dEmerExit("AirbusFBW/EmerExitArray");
static DR dEmerSlides("AirbusFBW/EmerSlidesDeployRatio");
static DR dCkptDoorLock("AirbusFBW/CockpitDoorLockState");
static DR dCkptDoorAngle("AirbusFBW/CockpitDoorAngle");
static DR dCabLightPerc("AirbusFBW/cabinLightLevel_perc");
static DR dCabLight("AirbusFBW/CabinLightLevel");
static DR dFSB("AirbusFBW/SeatBeltSignsOn");
static DR dNS("AirbusFBW/NoSmokingSignsOn");
static DR dTempCk("AirbusFBW/CockpitTemperature_degC");
static DR dTempZ1("AirbusFBW/CabinZone1Temperature_degC");
static DR dTempZ2("AirbusFBW/CabinZone2Temperature_degC");
static DR dSelCk("AirbusFBW/CockpitTemp");
static DR dSelFwd("AirbusFBW/FwdCabinTemp");
static DR dSelAft("AirbusFBW/AftCabinTemp");
static DR dEvacLight("AirbusFBW/EmerEvacLight");
static DR dEvacBtn("AirbusFBW/EmerEvacButton");
static DR dEvacSel("AirbusFBW/EmerEvacCaptPursSelSwitch");
static DR dEmerCallOHP("AirbusFBW/EmerCallOHPButton");
static DR dNoPax("AirbusFBW/NoPax");
static DR dPaxOxy("AirbusFBW/PaxOxyMask");
static DR dPhase("AirbusFBW/ECAMFlightPhase");
static DR dCabAlt("AirbusFBW/CabinAlt");
static DR dDoorSwitch("AirbusFBW/CockpitDoorSwitch");  // pedestal COCKPIT DOOR: 0 UNLOCK, 1 NORM, 2 LOCK
static DR dFus("1-sim/fus");
// X-Plane
static DR dACBus("AirbusFBW/ACBusVoltages");   // [0] AC1, [1] AC2 (ext power / APU gen / engine gens)
static DR dDCBus("AirbusFBW/DCBusVoltages");   // any DC bus (batteries on, or fed through the TRs)
static DR dBusVolts("sim/cockpit2/electrical/bus_volts");  // fallback when the ToLiss arrays are missing
static DR dZulu("sim/time/zulu_time_sec");
static DR dOnGround("sim/flightmodel/failures/onground_any");
static DR dRunTime("sim/time/total_running_time_sec");
static DR dPaused("sim/time/paused");
static DR dIcao("sim/aircraft/view/acf_ICAO");
static DR dHeadZ("sim/graphics/view/pilots_head_z");
static DR dOutside("sim/graphics/misc/outside_light_level_r");
static DR dViewExt("sim/graphics/view/view_is_external");
static DR dCgZ("sim/aircraft/weight/acf_cgZ_original");
static DR dCkptDoorAnim("ckpt/door");

static DR* kAllDR[] = {&dPaxDoor, &dPaxDoorMode, &dSlideArmed, &dSlideDeploy, &dCargoDoor, &dCargoDoorMode,
                       &dBulkDoor, &dEmerExit, &dEmerSlides, &dCkptDoorLock, &dCkptDoorAngle, &dCabLightPerc,
                       &dCabLight, &dFSB, &dNS, &dTempCk, &dTempZ1, &dTempZ2, &dSelCk, &dSelFwd, &dSelAft,
                       &dEvacLight, &dEvacBtn, &dEvacSel, &dEmerCallOHP, &dNoPax, &dPaxOxy, &dPhase,
                       &dCabAlt, &dFus, &dACBus, &dDCBus, &dDoorSwitch};

static void run_command(const char* name) {
    XPLMCommandRef c = XPLMFindCommand(name);
    if (c) XPLMCommandOnce(c);
    else logf("command not found: %s", name);
}

// ---------------------------------------------------------------------------
// Simulated cabin state
struct CallEvt {
    int id;
    std::string src;   // e.g. "CAPT", "PAX 23C", "LAV A"
    std::string text;  // e.g. "CABIN CALL"
    std::string time;  // HH:MM UTC
    int prio;          // 0 normal, 1 priority, 2 emergency
    bool active;
};

struct Lav {
    const char* name;
    bool occupied = false;
    double next_change = 0;
    bool smoke = false;
};

struct Track {
    std::string name;
    std::string path;
};

static struct Sim {
    // persisted
    float water = 100.f;  // %
    float waste = 8.f;    // %
    int water_presel = 100;
    float brightness = 0.9f;
    float music_vol = 0.5f;
    float ann_vol = 0.9f;
    // runtime
    bool water_fill = false;
    bool waste_drain = false;
    Lav lav[3] = {{"A"}, {"D"}, {"E"}};
    double smoke_test_until = 0;
    bool smoke_alert = false;
    bool cabin_ready = false;
    std::vector<CallEvt> calls;
    int call_seq = 0;
    double ckpt_call_until = 0;  // FAP -> cockpit call indicator
    int prev_emer_call = 0;
    double next_pax_call = 0;
    int debug_quad = 0;
    bool powered = false;        // FAP screen + cabin audio: AC power (ext power, APU gen or engine gens)
    bool dc_powered = false;     // key backlight / CIDS: any DC bus (batteries on)
    double boot_start = -1;      // sim time the screen started booting, -1 = not booting
    // audio
    std::vector<Track> music, ann;
    int music_idx = -1;
    bool music_playing = false;
    bool music_loop_all = true;
    int ann_idx = -1;
    std::vector<int> memo;       // announcement memo list (indices into ann)
    std::vector<int> ann_queue;  // unused (kept for state compatibility)
    bool memo_all = false;       // "Play All" in progress: memo entries are consumed as they start
    std::string audio_msg;
} S;

static std::mt19937 g_rng(12345);
static float g_cabin_gain = 1.f;  // cabin PA level at the listener position (see cabin_gain_target)
static bool g_lav_maint = false;   // LAV MAINT key
static double g_lock_until = 0;    // SCREEN 30 sec LOCK key (sim time)
static double urand() { return std::uniform_real_distribution<double>(0, 1)(g_rng); }

static double now_s() { return dRunTime.f(0); }

static constexpr double kBootSecs = 32.0;     // FAP power-up sequence length (the page draws the stages)
static constexpr double kHoldUpSecs = 2.0;    // AC breaks shorter than this (power transfers) don't reboot
static double g_load_t = -1;                  // aircraft load time: power found right after load = no boot
static double g_ac_lost_at = -1;

static std::string zulu_hhmm() {
    int t = (int)dZulu.f(0);
    char b[16];
    snprintf(b, sizeof b, "%02d:%02d", (t / 3600) % 24, (t / 60) % 60);
    return b;
}

// chime = false when the call comes from the cockpit: ToLiss already plays its own chime then.
static void add_call(const std::string& src, const std::string& text, int prio, Chime chime, bool chime_on = true) {
    CallEvt e{++S.call_seq, src, text, zulu_hhmm(), prio, true};
    S.calls.insert(S.calls.begin(), e);
    if (S.calls.size() > 20) S.calls.resize(20);
    if (chime_on && S.powered) fap_audio::play_chime(chime);
}

// ---------------------------------------------------------------------------
// paths / persistence
static std::string g_plugin_dir;  // .../plugins/ToLissFAP
static std::string g_prefs_path;

static std::string file_url(const std::string& native_path) {
    std::string p = native_path;
    std::replace(p.begin(), p.end(), '\\', '/');
    std::string out = "file:///";
    static const char* hex = "0123456789ABCDEF";
    for (unsigned char c : p) {
        bool safe = isalnum(c) || strchr("/:-_.~()!*'", c);
        if (safe) out += (char)c;
        else { out += '%'; out += hex[c >> 4]; out += hex[c & 15]; }
    }
    return out;
}

// Free-form UI state owned by the page (entry lights, BGM channel, temp unit...).
static std::map<std::string, double> g_ui;

static bool valid_ui_key(const std::string& k) {
    if (k.empty() || k.size() > 32) return false;
    for (char c : k)
        if (!isalnum((unsigned char)c) && c != '_') return false;
    return true;
}

static void load_prefs() {
    std::ifstream f(g_prefs_path);
    std::string k;
    float v;
    while (f >> k >> v) {
        if (k.rfind("ui.", 0) == 0) {
            if (valid_ui_key(k.substr(3)) && g_ui.size() < 64) g_ui[k.substr(3)] = v;
        } else if (k == "water") S.water = std::clamp(v, 0.f, 100.f);
        else if (k == "waste") S.waste = std::clamp(v, 0.f, 100.f);
        else if (k == "water_presel") S.water_presel = std::clamp((int)v, 25, 100);
        else if (k == "brightness") S.brightness = std::clamp(v, 0.05f, 1.f);
        else if (k == "music_vol") S.music_vol = std::clamp(v, 0.f, 1.f);
        else if (k == "ann_vol") S.ann_vol = std::clamp(v, 0.f, 1.f);
        // debug_quad is deliberately not restored: it must never come back on by itself
    }
}

static void save_prefs() {
    std::ofstream f(g_prefs_path);
    f << "water " << S.water << "\nwaste " << S.waste << "\nwater_presel " << S.water_presel << "\nbrightness "
      << S.brightness << "\nmusic_vol " << S.music_vol << "\nann_vol " << S.ann_vol << "\ndebug_quad "
      << S.debug_quad << "\n";
    for (auto& kv : g_ui) f << "ui." << kv.first << " " << kv.second << "\n";
}

// Scans for .wav files, recursing into sub-folders (up to 3 levels). A file in a
// sub-folder gets the name "Folder/Sub/File" so the page can show it as a tree.
static std::vector<Track> scan_wavs(const std::string& dir) {
    std::vector<Track> v;
    std::error_code ec;
    if (!fs::is_directory(dir, ec)) return v;
    auto it = fs::recursive_directory_iterator(dir, fs::directory_options::skip_permission_denied, ec);
    for (; !ec && it != fs::recursive_directory_iterator(); it.increment(ec)) {
        if (it.depth() > 2) { it.disable_recursion_pending(); continue; }
        if (!it->is_regular_file()) continue;
        std::string ext = it->path().extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
        if (ext != ".wav" && ext != ".mp3") continue;
        fs::path rel = fs::relative(it->path(), dir, ec);
        rel.replace_extension();
        v.push_back({rel.generic_string(), it->path().string()});
    }
    std::sort(v.begin(), v.end(), [](const Track& a, const Track& b) {
        return std::lexicographical_compare(a.name.begin(), a.name.end(), b.name.begin(), b.name.end(),
                                            [](char x, char y) { return ::tolower((unsigned char)x) < ::tolower((unsigned char)y); });
    });
    return v;
}

// ---- per-livery content: <livery>/FAP/{screen_off.png|jpg, sounds/music, sounds/announcements}
static std::string g_xp_root;      // X-Plane folder (native path, trailing separator)
static std::string g_livery_dir;   // absolute path of the current livery folder ("" = default paint)
static std::string g_livery_name;
static std::string g_off_img_url;  // file URL of the screen-off image (livery or default)

static int g_music_liv = 0;       // number of livery music tracks at the start of S.music

// "(CFM) EC-MBD - Vueling - [A320-214]" -> "EC-MBD - Vueling": drops (..) / [..] tags and 4K/8K
static std::string short_livery_name(const std::string& n) {
    std::string o;
    int depth = 0;
    for (char c : n) {
        if (c == '(' || c == '[') { ++depth; continue; }
        if (c == ')' || c == ']') { if (depth) --depth; continue; }
        if (!depth) o += c;
    }
    std::istringstream ss(o);
    std::string w, out;
    while (ss >> w)
        if (w != "4K" && w != "8K") out += (out.empty() ? "" : " ") + w;
    while (!out.empty() && (out.back() == '-' || out.back() == ' ')) out.pop_back();
    while (!out.empty() && (out.front() == '-' || out.front() == ' ')) out.erase(out.begin());
    return out.empty() ? n : out;
}

static std::string livery_fap_dir() { return g_livery_dir.empty() ? std::string() : g_livery_dir + "/FAP"; }

static void rescan_audio() {
    S.music.clear();
    S.ann.clear();
    g_music_liv = 0;
    // livery content first, so it shows at the top of the lists
    if (!g_livery_dir.empty()) {
        for (auto& t : scan_wavs(livery_fap_dir() + "/sounds/music")) S.music.push_back(t);
        // the livery's own announcements are shown at the top level (it is "this airline's" FAP)
        for (auto& t : scan_wavs(livery_fap_dir() + "/sounds/announcements")) S.ann.push_back(t);
    }
    g_music_liv = (int)S.music.size();
    bool livAnn = !S.ann.empty();
    for (auto& t : scan_wavs(g_plugin_dir + "/sounds/music")) S.music.push_back(t);
    // general announcements: grouped under "General" only when the livery brings its own
    for (auto& t : scan_wavs(g_plugin_dir + "/sounds/announcements"))
        S.ann.push_back({livAnn ? "General/" + t.name : t.name, t.path});
}

// Rescan everything on disk: livery content (screen-off image, sounds), general music and
// announcements, and the chime recordings.
static void livery_refresh(bool force);
static void rescan_all() {
    livery_refresh(true);   // also rescans the audio lists
    fap_audio::load_chimes(g_plugin_dir + "/sounds/chimes");
    if (S.music_idx >= (int)S.music.size()) S.music_idx = -1;
    S.memo.clear();   // memo entries are indices into the old list
    logf("rescan: %d music, %d announcements (wav/mp3), chimes reloaded", (int)S.music.size(), (int)S.ann.size());
}

// Reads the current livery and (re)loads its FAP content when it changed.
static void livery_refresh(bool force) {
    char buf[1024] = {0};
    XPLMDataRef r = XPLMFindDataRef("sim/aircraft/view/acf_livery_path");
    if (r) XPLMGetDatab(r, buf, 0, sizeof buf - 1);
    std::string rel(buf), dir;
    if (!rel.empty()) {
        fs::path p(rel);
        dir = (p.is_absolute() ? p : fs::path(g_xp_root) / p).lexically_normal().string();
        while (!dir.empty() && (dir.back() == '/' || dir.back() == '\\')) dir.pop_back();
    }
    if (!force && dir == g_livery_dir && !g_off_img_url.empty()) return;
    g_livery_dir = dir;
    g_livery_name = dir.empty() ? std::string() : short_livery_name(fs::path(dir).filename().string());

    std::string img;
    std::error_code ec;
    for (const char* name : {"screen_off.png", "screen_off.jpg", "screen_off.jpeg"}) {
        std::string c = livery_fap_dir() + "/" + name;
        if (!dir.empty() && fs::exists(c, ec)) { img = c; break; }
    }
    g_off_img_url = file_url(img.empty() ? g_plugin_dir + "/html/img/screen_off_default.png" : img);

    rescan_audio();
    if (S.music_idx >= (int)S.music.size()) S.music_idx = -1;
    S.memo.clear();
    logf("livery: %s (screen-off image: %s, %d music, %d announcements)", g_livery_name.empty() ? "default" : g_livery_name.c_str(),
         img.empty() ? "default" : "livery", (int)S.music.size(), (int)S.ann.size());
}

static bool play_track(fap_audio::Kind k, const std::vector<Track>& list, int idx, float vol) {
    if (idx < 0 || idx >= (int)list.size()) return false;
    std::string err;
    auto clip = fap_audio::load_wav(list[idx].path, &err);
    if (!clip) {
        S.audio_msg = list[idx].name + ": " + err;
        logf("audio: %s", S.audio_msg.c_str());
        return false;
    }
    S.audio_msg.clear();
    return fap_audio::play(k, clip, vol, false);
}

static bool start_announcement(int k) {
    if (!play_track(fap_audio::kAnnounce, S.ann, k, S.ann_vol)) return false;
    S.ann_idx = k;
    fap_audio::set_volume(fap_audio::kMusic, S.music_vol * 0.25f);  // duck boarding music
    return true;
}

// Pops the first memo entry and plays it; skips entries that fail to load.
static bool play_next_memo() {
    while (!S.memo.empty()) {
        int k = S.memo.front();
        S.memo.erase(S.memo.begin());
        if (start_announcement(k)) return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// Avionics device
static XPLMAvionicsID g_dev = nullptr;
static bool g_tried_data_url = false;

// The screen is drawn as a light source: at night X-Plane's exposure blows it out, so the
// user brightness is capped by the outside light (100 % at night ~ 28 %).
// The 2D popup / pop-out window shows the same page but is not subject to the cockpit
// exposure, so while it is open the night dimming is skipped (the user setting still applies).
static float eff_brightness() {
    if (g_dev && XPLMIsAvionicsPopupVisible(g_dev)) return std::max(S.brightness, 0.35f);
    float amb = std::clamp(dOutside.f(1.f), 0.f, 1.f);
    return S.brightness * (0.28f + 0.72f * amb);
}
static float fap_brightness(float, float, float, void*) { return S.powered ? eff_brightness() : 0.f; }

static std::string state_json();
static std::string do_action(const char* json);

static const char* js_get_state(XPLMAvionicsID, const char*, void*) {
    std::string s = state_json();
    return XPLMReturnString(s.c_str());
}

static const char* js_action(XPLMAvionicsID, const char* inJSON, void*) {
    std::string s = do_action(inJSON);
    return XPLMReturnString(s.c_str());
}

static const char* js_log(XPLMAvionicsID, const char* inJSON, void*) {
    logf("page: %s", inJSON ? inJSON : "(null)");
    return XPLMReturnString("null");
}

static std::string base64(const std::string& in) {
    static const char* t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string o;
    o.reserve((in.size() + 2) / 3 * 4);
    size_t i = 0;
    for (; i + 2 < in.size(); i += 3) {
        unsigned n = ((unsigned char)in[i] << 16) | ((unsigned char)in[i + 1] << 8) | (unsigned char)in[i + 2];
        o += t[n >> 18]; o += t[(n >> 12) & 63]; o += t[(n >> 6) & 63]; o += t[n & 63];
    }
    if (i < in.size()) {
        unsigned n = (unsigned char)in[i] << 16;
        if (i + 1 < in.size()) n |= (unsigned char)in[i + 1] << 8;
        o += t[n >> 18]; o += t[(n >> 12) & 63];
        o += (i + 1 < in.size()) ? t[(n >> 6) & 63] : '=';
        o += '=';
    }
    return o;
}

static void load_page_data_url() {
    std::ifstream f(g_plugin_dir + "/html/index.html", std::ios::binary);
    std::string html((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    if (html.empty()) { logf("index.html missing or empty"); return; }
    logf("falling back to data: URL (%u bytes)", (unsigned)html.size());
    std::string url = "data:text/html;charset=utf-8;base64," + base64(html);
    XPLMAvionicsSetURL(g_dev, url.c_str());
}

static void on_load_finished(XPLMAvionicsID dev, const char* url, void*) {
    logf("page loaded: %.120s", url ? url : "");
    // Diagnostic: report what the page sees of the xplane.* bridge.
    XPLMAvionicsInjectScript(dev,
        "try{var k=window.xplane?Object.keys(window.xplane):null;"
        "if(window.xplane&&window.xplane.log)window.xplane.log({diag:\"bridge\",type:typeof window.xplane,keys:k});}catch(e){}");
}

static void on_load_error(XPLMAvionicsID, const char* url, const char* err, void*) {
    logf("page load error: %.200s (%s)", url ? url : "", err ? err : "?");
    if (!g_tried_data_url && url && !strncmp(url, "file:", 5)) {
        g_tried_data_url = true;
        load_page_data_url();
    }
}

static void load_page() {
    g_tried_data_url = false;
    std::string url = file_url(g_plugin_dir + "/html/index.html");
    logf("loading %s", url.c_str());
    XPLMAvionicsSetURL(g_dev, url.c_str());
}

// Touches on the screen (3D cockpit via ATTR_manip_device, or the popup).
// Coordinates are texels, origin bottom-left. We forward a synthetic click into
// the page; the page de-duplicates in case X-Plane also delivers it natively.
static int g_touch_log = 0;
static bool screen_locked() { return now_s() < g_lock_until; }
static int fap_touch(int x, int y, XPLMMouseStatus st, void*) {
    if (screen_locked()) return 1;  // SCREEN 30 sec LOCK (cleaning)
    if (g_touch_log < 40) {
        ++g_touch_log;
        logf("touch %s x=%d y=%d", st == xplm_MouseDown ? "down" : st == xplm_MouseDrag ? "drag" : "up", x, y);
    }
    if (st == xplm_MouseDown && g_dev && x >= 0 && y >= 0 && x < kScreenW && y < kScreenH) {
        char js[160];
        snprintf(js, sizeof js, "window.fapTouch&&window.fapTouch(%d,%d)", x, kScreenH - 1 - y);
        XPLMAvionicsInjectScript(g_dev, js);
    }
    return 1;
}

static void create_device() {
    if (g_dev) return;
    XPLMCreateAvionics_t p;
    memset(&p, 0, sizeof p);
    p.structSize = sizeof p;
    p.screenWidth = kScreenW;
    p.screenHeight = kScreenH;
    p.bezelWidth = kScreenW;
    p.bezelHeight = kScreenH;
    p.screenOffsetX = 0;
    p.screenOffsetY = 0;
    p.drawOnDemand = 0;
    p.brightnessCallback = fap_brightness;
    p.screenTouchCallback = fap_touch;
    p.deviceID = DEVICE_ID;
    p.deviceName = "ToLiss FAP (Flight Attendant Panel)";
    p.contentType = xplm_WindowContentTypeBrowser;
    p.windowWithChrome = 1;
    p.browserLoadFinishedFunc = on_load_finished;
    p.browserLoadErrorFunc = on_load_error;
    g_dev = XPLMCreateAvionicsEx(&p);
    if (!g_dev) { logf("XPLMCreateAvionicsEx FAILED"); return; }
    XPLMAvionicsAddBrowserFunction(g_dev, "getState", js_get_state, nullptr);
    XPLMAvionicsAddBrowserFunction(g_dev, "action", js_action, nullptr);
    XPLMAvionicsAddBrowserFunction(g_dev, "log", js_log, nullptr);
    load_page();
    logf("device %s created (%dx%d)", DEVICE_ID, kScreenW, kScreenH);
}

static void destroy_device() {
    if (g_dev) XPLMDestroyAvionics(g_dev);
    g_dev = nullptr;
}

// ---------------------------------------------------------------------------
// State -> JSON
static std::string state_json() {
    std::ostringstream o;
    auto n = [](double v, int p = 2) { return jm::num(v, p); };
    o << "{\"v\":\"" FAP_VERSION "\"";
    o << ",\"pwr\":" << (S.powered ? 1 : 0);
    o << ",\"boot\":" << (S.powered && S.boot_start >= 0 ? n(now_s() - S.boot_start, 2) : std::string("-1"))
      << ",\"bootDur\":" << n(kBootSecs, 0);
    o << ",\"utc\":" << jm::str(zulu_hhmm());
    o << ",\"phase\":" << dPhase.i(0);
    o << ",\"gnd\":" << dOnGround.i(1);
    o << ",\"toliss\":" << (dPaxDoorMode.ok() ? 1 : 0);
    char icao[8] = {0};
    if (dIcao.ok()) XPLMGetDatab(dIcao.ref, icao, 0, 7);
    o << ",\"icao\":" << jm::str(icao);

    // doors
    int nd = std::max(0, std::min(8, dPaxDoorMode.size()));
    o << ",\"doors\":[";
    for (int k = 0; k < nd; ++k) {
        if (k) o << ",";
        o << "{\"pos\":" << n(dPaxDoor.at(k)) << ",\"mode\":" << dPaxDoorMode.at(k) << ",\"armed\":"
          << (int)dSlideArmed.at(k) << ",\"slide\":" << n(dSlideDeploy.at(k)) << "}";
    }
    o << "]";
    int nc = std::max(0, std::min(4, dCargoDoorMode.size()));
    o << ",\"cargo\":[";
    for (int k = 0; k < nc; ++k) {
        if (k) o << ",";
        float pos = (k == 2 && dBulkDoor.ok()) ? std::max(dBulkDoor.f(), dCargoDoor.at(k)) : dCargoDoor.at(k);
        o << "{\"pos\":" << n(pos) << ",\"mode\":" << dCargoDoorMode.at(k) << "}";
    }
    o << "]";
    o << ",\"emer\":[";
    for (int k = 0; k < 4; ++k) {
        if (k) o << ",";
        o << n(std::max(dEmerExit.at(k), dEmerSlides.at(k)));
    }
    o << "]";
    o << ",\"ckptLock\":" << dCkptDoorLock.i() << ",\"ckptDoor\":" << n(dCkptDoorAngle.f());

    // lights & signs
    o << ",\"light\":{\"perc\":" << n(dCabLightPerc.f(), 0) << ",\"act\":" << n(dCabLight.f()) << "}";
    o << ",\"fsb\":" << dFSB.i() << ",\"ns\":" << dNS.i();

    // temps
    o << ",\"temp\":{\"ck\":" << n(dTempCk.f(), 1) << ",\"z1\":" << n(dTempZ1.f(), 1) << ",\"z2\":"
      << n(dTempZ2.f(), 1) << ",\"sCk\":" << dSelCk.i() << ",\"sF\":" << dSelFwd.i() << ",\"sA\":" << dSelAft.i()
      << "}";

    // water / waste
    o << ",\"water\":" << n(S.water, 1) << ",\"waste\":" << n(S.waste, 1) << ",\"wpre\":" << S.water_presel
      << ",\"wfill\":" << (S.water_fill ? 1 : 0) << ",\"wdrain\":" << (S.waste_drain ? 1 : 0);

    // lavs / smoke
    o << ",\"lav\":[";
    for (int k = 0; k < 3; ++k) {
        if (k) o << ",";
        o << "{\"n\":" << jm::str(S.lav[k].name) << ",\"occ\":" << (S.lav[k].occupied ? 1 : 0)
          << ",\"smoke\":" << (S.lav[k].smoke ? 1 : 0) << "}";
    }
    o << "],\"smokeTest\":" << (now_s() < S.smoke_test_until ? 1 : 0);

    // calls
    o << ",\"calls\":[";
    for (size_t k = 0; k < S.calls.size(); ++k) {
        auto& c = S.calls[k];
        if (k) o << ",";
        o << "{\"id\":" << c.id << ",\"src\":" << jm::str(c.src) << ",\"txt\":" << jm::str(c.text)
          << ",\"tm\":" << jm::str(c.time) << ",\"prio\":" << c.prio << ",\"act\":" << (c.active ? 1 : 0) << "}";
    }
    o << "],\"ckptCall\":" << (now_s() < S.ckpt_call_until ? 1 : 0);

    // misc
    o << ",\"cabinReady\":" << (S.cabin_ready ? 1 : 0);
    o << ",\"lock\":" << (int)std::ceil(std::max(0.0, g_lock_until - now_s())) << ",\"lavMaint\":" << (g_lav_maint ? 1 : 0);
    o << ",\"evac\":{\"light\":" << dEvacLight.i() << ",\"btn\":" << dEvacBtn.i() << ",\"sel\":" << dEvacSel.i()
      << "}";
    o << ",\"pax\":" << dNoPax.i() << ",\"oxy\":" << dPaxOxy.i() << ",\"cabAlt\":" << n(dCabAlt.f(), 0);
    o << ",\"gain\":" << n(g_cabin_gain, 2);
    o << ",\"effBright\":" << n(eff_brightness(), 3);
    o << ",\"bright\":" << n(S.brightness) << ",\"debugQuad\":" << S.debug_quad;

    // audio
    o << ",\"music\":{\"files\":[";
    for (size_t k = 0; k < S.music.size(); ++k) o << (k ? "," : "") << jm::str(S.music[k].name);
    o << "],\"liv\":" << g_music_liv << ",\"idx\":" << S.music_idx << ",\"playing\":" << (fap_audio::is_playing(fap_audio::kMusic) ? 1 : 0)
      << ",\"vol\":" << n(S.music_vol) << "}";
    o << ",\"ann\":{\"files\":[";
    for (size_t k = 0; k < S.ann.size(); ++k) o << (k ? "," : "") << jm::str(S.ann[k].name);
    o << "],\"idx\":" << S.ann_idx << ",\"playing\":" << (fap_audio::is_playing(fap_audio::kAnnounce) ? 1 : 0)
      << ",\"vol\":" << n(S.ann_vol) << ",\"memo\":[";
    for (size_t k = 0; k < S.memo.size(); ++k) o << (k ? "," : "") << S.memo[k];
    o << "],\"queue\":" << (S.memo_all ? S.memo.size() : 0) << ",\"all\":" << (S.memo_all ? 1 : 0) << "}";
    o << ",\"audioMsg\":" << jm::str(S.audio_msg);
    o << ",\"livery\":" << jm::str(g_livery_name) << ",\"offImg\":" << jm::str(g_off_img_url);
    o << ",\"ui\":{";
    bool first = true;
    for (auto& kv : g_ui) {
        o << (first ? "" : ",") << jm::str(kv.first) << ":" << n(kv.second, 3);
        first = false;
    }
    o << "}}";
    return o.str();
}

// ---------------------------------------------------------------------------
// Actions from the page
static std::string ok() { return "{\"ok\":true}"; }
static std::string fail(const char* why) { return std::string("{\"ok\":false,\"err\":") + jm::str(why) + "}"; }

static std::string do_action(const char* json) {
    auto m = jm::parse_flat(json);
    std::string a = jm::gets(m, "a");
    auto d = [&](const char* k, double def = 0) { return jm::getd(m, k, def); };
    bool gnd = dOnGround.i(1) != 0;

    if (a == "door_mode") {
        int k = (int)d("i", -1), mode = (int)d("mode", 1);
        if (k < 0 || k >= dPaxDoorMode.size() || mode < 0 || mode > 2) return fail("bad door");
        dPaxDoorMode.set_at(k, (float)mode);
    } else if (a == "cargo_mode") {
        int k = (int)d("i", -1), mode = (int)d("mode", 1);
        if (k < 0 || k >= dCargoDoorMode.size() || mode < 0 || mode > 2) return fail("bad cargo door");
        dCargoDoorMode.set_at(k, (float)mode);
    } else if (a == "all_doors") {
        int mode = (int)d("mode", 1);
        run_command(mode == 0 ? "toliss_airbus/door_commands/all_to_mode_close"
                    : mode == 2 ? "toliss_airbus/door_commands/all_to_mode_open"
                                : "toliss_airbus/door_commands/all_to_mode_auto");
    } else if (a == "arm_slides") {
        run_command("toliss_airbus/door_commands/arm_slides");
    } else if (a == "disarm_slides") {
        run_command("toliss_airbus/door_commands/disarm_slides");
    } else if (a == "light") {
        dCabLightPerc.set((float)std::clamp(d("level", 100), 0.0, 100.0));
    } else if (a == "temp") {
        DR& sel = jm::gets(m, "zone") == "aft" ? dSelAft : dSelFwd;
        int v = std::clamp(sel.i(22) + (int)d("delta", 0), 18, 30);
        sel.set((float)v);
    } else if (a == "temp_reset") {
        int ck = dSelCk.i(22);
        dSelFwd.set((float)ck);
        dSelAft.set((float)ck);
    } else if (a == "ui_set") {
        std::string k = jm::gets(m, "k");
        if (!valid_ui_key(k)) return fail("bad key");
        if (!g_ui.count(k) && g_ui.size() >= 64) return fail("ui store full");
        g_ui[k] = d("v", 0);
        save_prefs();
    } else if (a == "music_sel") {
        int k = (int)d("i", 0);
        if (k < 0 || k >= (int)S.music.size()) return fail("bad channel");
        S.music_idx = k;
    } else if (a == "water_presel") {
        S.water_presel = std::clamp((int)d("pct", 100), 25, 100);
    } else if (a == "water_fill") {
        if (!gnd) return fail("INHIBITED IN FLIGHT");
        S.water_fill = !S.water_fill;
    } else if (a == "waste_drain") {
        if (!gnd) return fail("INHIBITED IN FLIGHT");
        S.waste_drain = !S.waste_drain;
    } else if (a == "smoke_test") {
        S.smoke_test_until = now_s() + 6.0;
        if (S.powered) fap_audio::play_chime(Chime::HiLoX3);
    } else if (a == "smoke_reset") {
        for (auto& l : S.lav) l.smoke = false;
        S.smoke_alert = false;
    } else if (a == "call_reset") {
        int id = (int)d("id", -1);
        for (auto& c : S.calls)
            if (id < 0 || c.id == id) c.active = false;
    } else if (a == "call_clear") {
        S.calls.erase(std::remove_if(S.calls.begin(), S.calls.end(), [](const CallEvt& c) { return !c.active; }),
                      S.calls.end());
    } else if (a == "call_capt") {
        S.ckpt_call_until = now_s() + 30.0;
        if (S.powered) fap_audio::play_chime(Chime::HiLo);
    } else if (a == "call_capt_emer") {
        S.ckpt_call_until = now_s() + 60.0;
        if (S.powered) fap_audio::play_chime(Chime::HiLoX3);
    } else if (a == "call_attnd") {
        if (S.powered) fap_audio::play_chime(Chime::HiLo);
    } else if (a == "chime") {
        std::string t = jm::gets(m, "t");
        if (S.powered)
            fap_audio::play_chime(t == "hilo" ? Chime::HiLo : t == "emer" ? Chime::HiLoX3 : t == "tri" ? Chime::Tri : t == "lo" ? Chime::Lo : Chime::Single);
    } else if (a == "cabin_ready") {
        bool was = S.cabin_ready;
        S.cabin_ready = d("on", !S.cabin_ready) != 0;
        if (S.cabin_ready && !was) {
            // Same as pressing a purser/attendant call pb in the cockpit: ToLiss then
            // shows CABIN READY in the ECAM memo (and plays its own chime).
            run_command("AirbusFBW/CheckCabin");
        }
    } else if (a == "evac_cmd") {
        if (dEvacSel.i() != 1) return fail("EVAC CMD ONLY WITH CAPT & PURS SELECTED");
        dEvacBtn.set(1);
    } else if (a == "evac_reset") {
        dEvacBtn.set(0);
    } else if (a == "horn_off") {
        run_command("AirbusFBW/EvacHornShutOff");
    } else if (a == "music_play") {
        int k = (int)d("i", S.music_idx < 0 ? 0 : S.music_idx);
        if (!play_track(fap_audio::kMusic, S.music, k, S.music_vol)) return fail("cannot play");
        S.music_idx = k;
        S.music_playing = true;
    } else if (a == "music_stop") {
        S.music_playing = false;
        fap_audio::stop(fap_audio::kMusic);
    } else if (a == "music_next") {
        if (S.music.empty()) return fail("no music files");
        S.music_idx = (S.music_idx + 1) % (int)S.music.size();
        S.music_playing = play_track(fap_audio::kMusic, S.music, S.music_idx, S.music_vol);
    } else if (a == "music_vol") {
        S.music_vol = (float)std::clamp(d("v", 0.5), 0.0, 1.0);
        fap_audio::set_volume(fap_audio::kMusic, S.music_vol);
    } else if (a == "ann_play") {  // direct play
        S.ann_queue.clear();
        S.memo_all = false;
        if (!start_announcement((int)d("i", 0))) return fail("cannot play");
    } else if (a == "ann_stop") {
        S.ann_queue.clear();
        S.memo_all = false;
        fap_audio::stop(fap_audio::kAnnounce);
        fap_audio::set_volume(fap_audio::kMusic, S.music_vol);
    } else if (a == "memo_add") {
        int k = (int)d("i", -1);
        if (k < 0 || k >= (int)S.ann.size()) return fail("bad announcement");
        if (S.memo.size() >= 30) return fail("MEMO FULL");
        S.memo.push_back(k);
    } else if (a == "memo_del") {
        int p = (int)d("p", -1);
        if (p < 0 || p >= (int)S.memo.size()) return fail("SELECT MEMO ENTRY");
        S.memo.erase(S.memo.begin() + p);
    } else if (a == "memo_move") {
        int p = (int)d("p", -1), q = p + (int)d("d", 0);
        if (p < 0 || q < 0 || p >= (int)S.memo.size() || q >= (int)S.memo.size()) return fail("bad move");
        std::swap(S.memo[p], S.memo[q]);
    } else if (a == "memo_clear") {
        S.memo.clear();
    } else if (a == "memo_next") {  // play first memo entry and consume it
        if (S.memo.empty()) return fail("MEMO EMPTY");
        int k = S.memo.front();
        S.memo.erase(S.memo.begin());
        S.ann_queue.clear();
        S.memo_all = false;
        if (!start_announcement(k)) return fail("cannot play");
    } else if (a == "memo_all") {  // play the memo in order, consuming entries as they start
        if (S.memo.empty()) return fail("MEMO EMPTY");
        S.ann_queue.clear();
        S.memo_all = true;
        if (!play_next_memo()) { S.memo_all = false; return fail("cannot play"); }
    } else if (a == "ann_vol") {
        S.ann_vol = (float)std::clamp(d("v", 0.9), 0.0, 1.0);
        fap_audio::set_volume(fap_audio::kAnnounce, S.ann_vol);
    } else if (a == "rescan") {
        rescan_all();
        S.memo.clear();
        S.ann_queue.clear();
        S.memo_all = false;
    } else if (a == "bright") {
        S.brightness = (float)std::clamp(d("v", 0.9), 0.05, 1.0);
    } else if (a == "debug_quad") {
        S.debug_quad = d("on", !S.debug_quad) != 0;
    } else {
        return fail("unknown action");
    }
    return ok();
}

// ---------------------------------------------------------------------------
// Simulation tick
static double g_last_t = -1;

// How loud the cabin PA is where the listener is. The speakers are in the cabin, so:
// cabin 100%, cockpit with door open ~45%, door closed ~15%, outside views ~5%.
static float cabin_gain_target() {
    if (dViewExt.i() != 0) return 0.05f;
    const double FT = 0.3048;
    // FAP screen plane in the CG frame (kitchens frame + anim + attach - default CG),
    // following the fuselage-length animation used by ToLiss (1-sim/fus).
    double f = dFus.f(0), fusZ = f <= 1 ? 1.6 * f : 1.6 + (-4.26 - 1.6) * (f - 1);
    double fapZ = -0.3713 + (-1.43062 + fusZ) + 20.75 * FT - dCgZ.f(54) * FT;
    double doorZ = fapZ - 0.40;                                  // flight deck door just forward of the FAP
    double t = std::clamp((dHeadZ.f(0) - (doorZ - 0.3)) / 0.6, 0.0, 1.0);  // 0 cockpit .. 1 cabin
    // ckpt/door is the door animation in degrees (0 closed, ~80 open); CockpitDoorAngle may be a ratio
    double ang = dCkptDoorAngle.f(0);
    double open = std::max(std::clamp(dCkptDoorAnim.f(0) / 60.0, 0.0, 1.0), std::clamp(ang > 1.0 ? ang / 60.0 : ang, 0.0, 1.0));
    double cockpit = 0.15 + 0.30 * open;
    return (float)(cockpit + (1.0 - cockpit) * t);
}

// Power model:
//  - key backlight follows the DC buses (batteries on is enough);
//  - the screen needs AC (AC1 or AC2: external power, APU generator or engine generators),
//    and boots for kBootSecs every time AC comes back after a real loss.
static void update_power(double t) {
    bool ac, dc;
    if (dACBus.size() >= 2) {
        ac = std::max(dACBus.at(0), dACBus.at(1)) > 90.f;
        dc = false;
        for (int k = 0, n = dDCBus.size(); k < n; ++k) dc |= dDCBus.at(k) > 20.f;
        dc |= ac;
    } else {  // not a ToLiss (or datarefs not there yet): X-Plane's buses for both
        ac = dc = std::max(dBusVolts.at(0), dBusVolts.at(1)) > 20.f;
    }
    if (dc != S.dc_powered) logf("DC power %s", dc ? "ON (keys backlit)" : "OFF");
    S.dc_powered = dc;

    if (ac) {
        g_ac_lost_at = -1;
        if (!S.powered) {
            S.powered = true;
            bool at_load = g_load_t >= 0 && t - g_load_t < 10.0;  // e.g. loaded with engines running
            S.boot_start = at_load ? -1 : t;
            std::string v;
            for (int k = 0, n = dACBus.size(); k < n; ++k) v += (k ? " " : "") + jm::num(dACBus.at(k), 0);
            logf("AC power ON (AC buses: %s)%s", v.c_str(), at_load ? ", already on at load: no boot" : ", booting");
        }
    } else if (S.powered) {
        if (g_ac_lost_at < 0) g_ac_lost_at = t;
        if (t - g_ac_lost_at > kHoldUpSecs) {
            S.powered = false;
            S.boot_start = -1;
            logf("AC power OFF: FAP screen off");
        }
    }
    if (S.boot_start >= 0 && t - S.boot_start >= kBootSecs) S.boot_start = -1;
}

static void door_tick(double t);

static float sim_tick(float, float, int, void*) {
    double t = now_s();
    fap_audio::tick(t);
    double dt = (g_last_t < 0) ? 0 : std::clamp(t - g_last_t, 0.0, 1.0);
    g_last_t = t;
    if (dPaused.i() != 0) dt = 0;

    update_power(t);
    door_tick(t);

    // livery changes (also caught by XPLM_MSG_LIVERY_LOADED; this is a cheap safety net)
    static double next_livery_check = 0;
    if (t > next_livery_check) { next_livery_check = t + 3.0; livery_refresh(false); }

    // cabin speaker attenuation (smoothed so walking through the door fades nicely)
    float target = cabin_gain_target();
    g_cabin_gain += (target - g_cabin_gain) * (float)std::min(1.0, (dt > 0 ? dt : 0.1) * 3.0);
    fap_audio::set_master(g_cabin_gain);

    bool gnd = dOnGround.i(1) != 0;
    int pax = dNoPax.i(0);
    bool fsb = dFSB.i() != 0;

    // water consumption (A320: ~200 L tank) and waste (~170 L tank)
    if (pax > 0 && dt > 0) {
        double hours = dt / 3600.0;
        S.water = (float)std::max(0.0, S.water - pax * 0.10 * hours / 200.0 * 100.0 * (gnd ? 0.3 : 1.0));
        S.waste = (float)std::min(100.0, S.waste + pax * 0.08 * hours / 170.0 * 100.0 * (gnd ? 0.3 : 1.0));
    }
    if (S.water_fill) {
        if (!gnd) S.water_fill = false;
        else {
            S.water = std::min((float)S.water_presel, S.water + (float)dt * 1.5f);
            if (S.water >= S.water_presel - 0.01f) S.water_fill = false;
        }
    }
    if (S.waste_drain) {
        if (!gnd) S.waste_drain = false;
        else {
            S.waste = std::max(0.f, S.waste - (float)dt * 2.0f);
            if (S.waste <= 0.01f) S.waste_drain = false;
        }
    }

    // lavatory occupancy (only with passengers aboard)
    for (auto& l : S.lav) {
        if (t < l.next_change) continue;
        if (pax <= 0) { l.occupied = false; l.next_change = t + 30; continue; }
        if (l.occupied) {
            l.occupied = false;
            l.next_change = t + (fsb ? 600 + urand() * 600 : 60 + urand() * 400);
        } else if (!fsb) {
            l.occupied = true;
            l.next_change = t + 90 + urand() * 240;
        } else {
            l.next_change = t + 60;
        }
    }

    // smoke test lights all detectors
    bool testing = t < S.smoke_test_until;
    for (auto& l : S.lav)
        if (testing) l.smoke = true;
    if (!testing && S.smoke_test_until > 0 && t - S.smoke_test_until < 0.5)
        for (auto& l : S.lav) l.smoke = false;

    // random passenger / lav calls in cruise with seat belts off
    if (S.next_pax_call == 0) S.next_pax_call = t + 600 + urand() * 900;
    if (t > S.next_pax_call) {
        S.next_pax_call = t + 600 + urand() * 1200;
        if (!gnd && !fsb && pax > 0 && S.powered) {
            if (urand() < 0.8) {
                char seat[16];
                snprintf(seat, sizeof seat, "PAX %d%c", 1 + (int)(urand() * 30), "ABCDEF"[(int)(urand() * 6)]);
                add_call(seat, "PAX CALL", 0, Chime::Single);
            } else {
                int k = (int)(urand() * 3);
                add_call(std::string("LAV ") + S.lav[k].name, "LAV CALL", 0, Chime::Single);
            }
        }
    }

    // emergency call from cockpit (overhead EMER CALL pb)
    int ec = dEmerCallOHP.i();
    if (ec && !S.prev_emer_call) add_call("CAPT", "EMER CALL", 2, Chime::HiLoX3, false);
    S.prev_emer_call = ec;

    // music playlist auto-advance
    if (fap_audio::consume_finished(fap_audio::kMusic) && S.music_playing && !S.music.empty()) {
        S.music_idx = (S.music_idx + 1) % (int)S.music.size();
        S.music_playing = play_track(fap_audio::kMusic, S.music, S.music_idx, S.music_vol);
    }
    if (fap_audio::consume_finished(fap_audio::kAnnounce)) {
        bool next = S.memo_all && play_next_memo();
        if (!next) {
            S.memo_all = false;
            fap_audio::set_volume(fap_audio::kMusic, S.music_vol);
        }
    }
    if (!S.powered) {
        if (fap_audio::is_playing(fap_audio::kMusic)) fap_audio::stop(fap_audio::kMusic);
        if (fap_audio::is_playing(fap_audio::kAnnounce)) fap_audio::stop(fap_audio::kAnnounce);
        S.music_playing = false;
    }
    return 0.1f;
}

// ---------------------------------------------------------------------------
// Cockpit -> cabin call buttons (pass-through handlers on ToLiss commands)
struct Hook {
    const char* cmd;
    const char* src;
    const char* text;
    XPLMCommandRef ref = nullptr;
};
static Hook g_hooks[] = {
    {"AirbusFBW/purser/fwd", "CAPT", "CALL FWD ATTND"},
    {"AirbusFBW/purser/aft", "CAPT", "CALL AFT ATTND"},
    {"AirbusFBW/purser/all", "CAPT", "CALL ALL ATTND"},
    {"AirbusFBW/purser/mech", "CAPT", "CALL MECH"},
};

static int hook_handler(XPLMCommandRef, XPLMCommandPhase phase, void* ref) {
    if (phase == xplm_CommandBegin) {
        Hook* h = (Hook*)ref;
        add_call(h->src, h->text, 1, Chime::HiLo, false);
    }
    return 1;  // let ToLiss handle it too
}

static void install_hooks() {
    for (auto& h : g_hooks) {
        if (h.ref) continue;
        h.ref = XPLMFindCommand(h.cmd);
        if (h.ref) XPLMRegisterCommandHandler(h.ref, hook_handler, 1, &h);
    }
}

static void remove_hooks() {
    for (auto& h : g_hooks) {
        if (h.ref) XPLMUnregisterCommandHandler(h.ref, hook_handler, 1, &h);
        h.ref = nullptr;
    }
}

// ---------------------------------------------------------------------------
// Own commands and datarefs
static XPLMCommandRef c_popup, c_popout, c_reload, c_debug, c_rescan;
static XPLMMenuID g_menu = nullptr;
static int g_menu_item = -1;
static XPLMDataRef r_debug, r_water, r_waste, r_ready, r_ckcall;

static int own_cmd(XPLMCommandRef c, XPLMCommandPhase phase, void*) {
    if (phase != xplm_CommandBegin || !g_dev) return 0;
    if (c == c_popup) XPLMSetAvionicsPopupVisible(g_dev, !XPLMIsAvionicsPopupVisible(g_dev));
    else if (c == c_popout) {
        if (!XPLMIsAvionicsPopupVisible(g_dev)) XPLMSetAvionicsPopupVisible(g_dev, 1);
        XPLMPopOutAvionics(g_dev);
    }
    else if (c == c_rescan) rescan_all();
    else if (c == c_reload) { rescan_all(); load_page(); }
    else if (c == c_debug) S.debug_quad = !S.debug_quad;
    return 0;
}

// ---------------------------------------------------------------------------
// Hardware keys under the screen (3D model: obj/fap_hw.obj, clicks via cockpit patch)
static XPLMCommandRef c_keys[7];
static const char* kKeyCmds[7][2] = {
    {"toliss_fap/key/emer", "FAP key: EMER (emergency call)"},
    {"toliss_fap/key/lights", "FAP key: LIGHTS MAIN ON/OFF"},
    {"toliss_fap/key/lav_maint", "FAP key: LAV MAINT"},
    {"toliss_fap/key/screen_lock", "FAP key: SCREEN 30 sec LOCK"},
    {"toliss_fap/key/evac_cmd", "FAP key: EVAC CMD"},
    {"toliss_fap/key/evac_reset", "FAP key: EVAC RESET"},
    {"toliss_fap/key/smoke_reset", "FAP key: SMOKE RESET"},
};
static float g_last_light = 100.f;
static XPLMDataRef r_keylight, r_hwoff, r_backlight, r_cover, r_doorreq;

// Transparent cover over the keys (3D only: while it is closed it takes the clicks).
// Animated from sim time in the getter, so it moves smoothly at any frame rate.
static XPLMCommandRef c_cover;
static bool g_cover_open = false;
static double g_cover_t0 = -10;               // time of the last toggle
static constexpr double kCoverSecs = 0.35;
static float get_cover(void*) {
    double p = std::clamp((now_s() - g_cover_t0) / kCoverSecs, 0.0, 1.0);
    p = p * p * (3 - 2 * p);                  // ease in/out
    return (float)(g_cover_open ? p : 1.0 - p);
}

// Flight-deck door keypad (own model; ToLiss has no keypad). Digits build a code, * clears it,
// # sends an access request: 5 s of "bip bip bip" in the cockpit, then, if the pedestal COCKPIT
// DOOR switch is in NORM, the door unlocks for 5 s (the plugin moves the switch to UNLOCK and back,
// since ToLiss's lock state is read-only). Selecting LOCK during the beeps denies the request.
// Switch values (probed in the sim): 0 UNLOCK, 1 NORM, 2 LOCK (only 2 sets CockpitDoorLockState).
static constexpr int kDoorUnlock = 0, kDoorNorm = 1, kDoorLock = 2;
static constexpr double kDoorBuzzSecs = 5.0, kDoorUnlockSecs = 5.0;
static const char* kKeypad[12] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "star", "hash"};
static XPLMCommandRef c_keypad[12];
static std::string g_code;
static double g_door_req_until = 0;          // buzzing until (0 = no request)
static double g_door_unlock_until = 0;       // we hold the switch in UNLOCK until (0 = not us)

static void door_tick(double t) {
    if (g_door_req_until > 0) {
        int sw = dDoorSwitch.i(kDoorNorm);
        if (sw == kDoorLock) {                         // pilot denied entry
            g_door_req_until = 0;
            fap_audio::stop_buzzer();
            logf("cockpit door access denied (switch LOCK)");
        } else if (t >= g_door_req_until) {
            g_door_req_until = 0;
            if (sw == kDoorNorm && dDoorSwitch.ok()) {
                dDoorSwitch.set((float)kDoorUnlock);
                g_door_unlock_until = t + kDoorUnlockSecs;
                logf("cockpit door unlocked after access request (switch NORM)");
            } else {
                logf("cockpit door access request: switch %d, no automatic unlock", sw);
            }
        }
    }
    if (g_door_unlock_until > 0 && t >= g_door_unlock_until) {
        g_door_unlock_until = 0;
        if (dDoorSwitch.i(-1) == kDoorUnlock) dDoorSwitch.set((float)kDoorNorm);   // only if nobody moved it
    }
}
static int keypad_cmd(XPLMCommandRef c, XPLMCommandPhase phase, void*) {
    if (phase != xplm_CommandBegin || !S.dc_powered) return 0;
    int k = 0;
    while (k < 12 && c_keypad[k] != c) ++k;
    if (k == 12) return 0;
    fap_audio::play_beep(fap_audio::Beep::Key);
    if (k < 10) { if (g_code.size() < 8) g_code += kKeypad[k]; }
    else if (k == 10) g_code.clear();
    else if (!g_code.empty() && g_door_req_until == 0) {
        g_code.clear();
        g_door_req_until = now_s() + kDoorBuzzSecs;
        fap_audio::play_beep(fap_audio::Beep::DoorBuzzer);
        logf("cockpit door access request from the keypad (door switch %d)", dDoorSwitch.i(-1));
    }
    return 0;
}
static int get_doorreq(void*) { return g_door_req_until > 0 ? 1 : 0; }

static bool emer_active() {
    if (now_s() < S.ckpt_call_until && S.ckpt_call_until - now_s() > 30.0) return true;  // FAP->cockpit EMER
    for (auto& c : S.calls)
        if (c.active && c.prio == 2) return true;
    return false;
}

static int key_cmd(XPLMCommandRef c, XPLMCommandPhase phase, void*) {
    if (phase != xplm_CommandBegin) return 0;
    if (c == c_cover) {
        double p = get_cover(nullptr);        // reverse smoothly if it is still moving
        g_cover_open = !g_cover_open;
        double from = g_cover_open ? p : 1.0 - p;
        g_cover_t0 = now_s() - from * kCoverSecs;
        return 0;
    }
    if (c == c_keys[0]) {  // EMER: start an emergency call, or reset an active one
        if (emer_active()) {
            for (auto& e : S.calls)
                if (e.prio == 2) e.active = false;
            S.ckpt_call_until = 0;
        } else do_action("{\"a\":\"call_capt_emer\"}");
    } else if (c == c_keys[1]) {  // LIGHTS MAIN ON/OFF
        float p = dCabLightPerc.f(0);
        if (p > 0.5f) { g_last_light = p; dCabLightPerc.set(0); }
        else dCabLightPerc.set(g_last_light > 1 ? g_last_light : 100.f);
    } else if (c == c_keys[2]) g_lav_maint = !g_lav_maint;
    else if (c == c_keys[3]) g_lock_until = now_s() + 30.0;
    else if (c == c_keys[4]) do_action("{\"a\":\"evac_cmd\"}");
    else if (c == c_keys[5]) { do_action("{\"a\":\"evac_reset\"}"); do_action("{\"a\":\"horn_off\"}"); }
    else if (c == c_keys[6]) do_action("{\"a\":\"smoke_reset\"}");
    return 0;
}

// Key legend lighting (index 0 = EMER, 1..6 = keys as in KEYS of build_fap_hw.py).
// Like the real panel, every key glows in its colour whenever there is DC power (backlight
// level); a key whose function is active is fully lit, alerts blink between the two.
static constexpr float kKeyBacklight = 0.42f;
static int get_keylight(void*, float* out, int offset, int max) {
    const int N = 8;
    if (!out) return N;
    float v[N] = {0};
    if (S.dc_powered) {
        double t = now_s();
        bool blink = std::fmod(t, 1.0) < 0.5;
        bool evac = dEvacLight.i() || dEvacBtn.i();
        bool smoke = false;
        for (auto& l : S.lav) smoke |= l.smoke;
        auto lvl = [](bool on) { return on ? 1.f : kKeyBacklight; };
        v[0] = lvl(emer_active() && blink);
        v[1] = lvl(dCabLightPerc.f(0) > 0.5f);
        v[2] = lvl(g_lav_maint);
        v[3] = lvl(t < g_lock_until);
        v[4] = lvl(evac && blink);
        v[5] = lvl(evac);
        v[6] = lvl(smoke && blink);
        v[7] = kKeyBacklight;
    }
    int n = 0;
    for (int i = offset; i < N && n < max; ++i) out[n++] = v[i];
    return n;
}
static float get_zero(void*) { return 0.f; }
// Legend backlight: on whenever the aircraft has DC power, like the real FAP keys.
static float get_backlight(void*) { return S.dc_powered ? 1.f : 0.f; }

static int get_debug(void*) { return S.debug_quad; }
static void set_debug(void*, int v) { S.debug_quad = v != 0; }
static float get_water(void*) { return S.water; }
static float get_waste(void*) { return S.waste; }
static int get_ready(void*) { return S.cabin_ready; }
static int get_ckcall(void*) { return now_s() < S.ckpt_call_until; }

static float deferred_init(float, float, int, void*) {
    for (DR* d : kAllDR) d->reset();
    g_load_t = now_s();
    install_hooks();
    livery_refresh(true);
    logf("ToLiss datarefs %s; aircraft fus=%d, doors=%d",
         dPaxDoorMode.ok() ? "found" : "NOT FOUND (is this a ToLiss?)", dFus.i(), dPaxDoorMode.size());
    return 0;  // once
}

// ---------------------------------------------------------------------------
PLUGIN_API int XPluginStart(char* outName, char* outSig, char* outDesc) {
    strcpy(outName, "ToLiss FAP");
    strcpy(outSig, "community.tolissfap");
    strcpy(outDesc, "Flight Attendant Panel (CIDS) for ToLiss A320/A321 - browser avionics");
    XPLMEnableFeature("XPLM_USE_NATIVE_PATHS", 1);

    char path[1024] = {0};
    XPLMGetPluginInfo(XPLMGetMyID(), nullptr, path, nullptr, nullptr);
    fs::path p(path);  // .../plugins/ToLissFAP/win_x64/ToLissFAP.xpl
    g_plugin_dir = p.parent_path().parent_path().string();
    char prefs[1024] = {0};
    XPLMGetPrefsPath(prefs);  // .../Output/preferences/Set X-Plane.prf
    g_prefs_path = (fs::path(prefs).parent_path() / "ToLissFAP.prf").string();
    logf("v" FAP_VERSION " start, dir=%s", g_plugin_dir.c_str());

    load_prefs();
    fap_audio::init();
    char sys[1024] = {0};
    XPLMGetSystemPath(sys);
    g_xp_root = sys;
    rescan_audio();
    fap_audio::load_chimes(g_plugin_dir + "/sounds/chimes");

    c_popup = XPLMCreateCommand("toliss_fap/toggle_popup", "FAP: show/hide 2D popup");
    c_popout = XPLMCreateCommand("toliss_fap/pop_out", "FAP: pop out into its own OS window");
    c_reload = XPLMCreateCommand("toliss_fap/reload", "FAP: reload page and rescan sound files");
    c_debug = XPLMCreateCommand("toliss_fap/toggle_debug_quad", "FAP: toggle debug screen in cockpit");
    c_rescan = XPLMCreateCommand("toliss_fap/rescan_sounds", "FAP: rescan sound files");
    for (auto c : {c_popup, c_popout, c_reload, c_debug, c_rescan}) XPLMRegisterCommandHandler(c, own_cmd, 1, nullptr);
    for (int i = 0; i < 7; ++i) {
        c_keys[i] = XPLMCreateCommand(kKeyCmds[i][0], kKeyCmds[i][1]);
        XPLMRegisterCommandHandler(c_keys[i], key_cmd, 1, nullptr);
    }
    c_cover = XPLMCreateCommand("toliss_fap/key/cover", "FAP: open/close the clear cover over the keys");
    XPLMRegisterCommandHandler(c_cover, key_cmd, 1, nullptr);
    for (int i = 0; i < 12; ++i) {
        std::string name = std::string("toliss_fap/keypad/") + kKeypad[i];
        std::string desc = std::string("Cockpit door keypad: ") + (i == 10 ? "*" : i == 11 ? "#" : kKeypad[i]);
        c_keypad[i] = XPLMCreateCommand(name.c_str(), desc.c_str());
        XPLMRegisterCommandHandler(c_keypad[i], keypad_cmd, 1, nullptr);
    }
    r_cover = XPLMRegisterDataAccessor("toliss_fap/key_cover", xplmType_Float, 0, nullptr, nullptr, get_cover,
                                       nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                       nullptr, nullptr, nullptr);
    r_doorreq = XPLMRegisterDataAccessor("toliss_fap/door_request", xplmType_Int, 0, get_doorreq, nullptr, nullptr,
                                         nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                         nullptr, nullptr, nullptr);
    r_keylight = XPLMRegisterDataAccessor("toliss_fap/key_light", xplmType_FloatArray, 0, nullptr, nullptr, nullptr,
                                          nullptr, nullptr, nullptr, nullptr, nullptr, get_keylight, nullptr, nullptr,
                                          nullptr, nullptr, nullptr);
    r_hwoff = XPLMRegisterDataAccessor("toliss_fap/hw_lit_off", xplmType_Float, 0, nullptr, nullptr, get_zero,
                                       nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                       nullptr, nullptr, nullptr);
    r_backlight = XPLMRegisterDataAccessor("toliss_fap/key_backlight", xplmType_Float, 0, nullptr, nullptr, get_backlight,
                                           nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                           nullptr, nullptr, nullptr);

    // Plugins > ToLiss FAP
    g_menu_item = XPLMAppendMenuItem(XPLMFindPluginsMenu(), "ToLiss FAP", nullptr, 0);
    g_menu = XPLMCreateMenu("ToLiss FAP", XPLMFindPluginsMenu(), g_menu_item, nullptr, nullptr);
    if (g_menu) {
        XPLMAppendMenuItemWithCommand(g_menu, "Show / hide FAP popup", c_popup);
        XPLMAppendMenuItemWithCommand(g_menu, "Pop out FAP (separate window)", c_popout);
        XPLMAppendMenuSeparator(g_menu);
        XPLMAppendMenuItemWithCommand(g_menu, "Rescan sound files", c_rescan);
        XPLMAppendMenuItemWithCommand(g_menu, "Reload FAP page", c_reload);
    }

    r_debug = XPLMRegisterDataAccessor("toliss_fap/debug_quad", xplmType_Int, 1, get_debug, set_debug, nullptr,
                                       nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                       nullptr, nullptr, nullptr);
    r_water = XPLMRegisterDataAccessor("toliss_fap/water_pct", xplmType_Float, 0, nullptr, nullptr, get_water,
                                       nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                       nullptr, nullptr, nullptr);
    r_waste = XPLMRegisterDataAccessor("toliss_fap/waste_pct", xplmType_Float, 0, nullptr, nullptr, get_waste,
                                       nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                       nullptr, nullptr, nullptr);
    r_ready = XPLMRegisterDataAccessor("toliss_fap/cabin_ready", xplmType_Int, 0, get_ready, nullptr, nullptr,
                                       nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                       nullptr, nullptr, nullptr);
    r_ckcall = XPLMRegisterDataAccessor("toliss_fap/cockpit_call", xplmType_Int, 0, get_ckcall, nullptr, nullptr,
                                        nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                                        nullptr, nullptr, nullptr);
    return 1;
}

PLUGIN_API void XPluginStop(void) {
    for (auto c : {c_popup, c_popout, c_reload, c_debug, c_rescan}) XPLMUnregisterCommandHandler(c, own_cmd, 1, nullptr);
    if (g_menu) XPLMDestroyMenu(g_menu);
    if (g_menu_item >= 0) XPLMRemoveMenuItem(XPLMFindPluginsMenu(), g_menu_item);
    g_menu = nullptr;
    g_menu_item = -1;
    for (auto r : {r_debug, r_water, r_waste, r_ready, r_ckcall, r_keylight, r_hwoff, r_backlight, r_cover, r_doorreq}) XPLMUnregisterDataAccessor(r);
    for (int i = 0; i < 7; ++i) XPLMUnregisterCommandHandler(c_keys[i], key_cmd, 1, nullptr);
    XPLMUnregisterCommandHandler(c_cover, key_cmd, 1, nullptr);
    for (int i = 0; i < 12; ++i) XPLMUnregisterCommandHandler(c_keypad[i], keypad_cmd, 1, nullptr);
}

PLUGIN_API int XPluginEnable(void) {
    create_device();
    XPLMRegisterFlightLoopCallback(sim_tick, 0.1f, nullptr);
    XPLMRegisterFlightLoopCallback(deferred_init, 2.0f, nullptr);
    return 1;
}

PLUGIN_API void XPluginDisable(void) {
    XPLMUnregisterFlightLoopCallback(sim_tick, nullptr);
    XPLMUnregisterFlightLoopCallback(deferred_init, nullptr);
    remove_hooks();
    fap_audio::shutdown();
    save_prefs();
    destroy_device();
}

PLUGIN_API void XPluginReceiveMessage(XPLMPluginID, int msg, void*) {
    if (msg == XPLM_MSG_PLANE_LOADED || msg == XPLM_MSG_AIRPORT_LOADED) {
        for (DR* d : kAllDR) d->reset();
        g_load_t = now_s();  // a new flight that starts powered (engines running) skips the boot
    }
    if (msg == XPLM_MSG_PLANE_LOADED || msg == XPLM_MSG_LIVERY_LOADED) livery_refresh(true);
}
