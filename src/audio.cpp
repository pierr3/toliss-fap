// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 pierr3 and ToLiss FAP contributors
#include "audio.h"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>

#include "XPLMSound.h"
#include "XPLMUtilities.h"

namespace fap_audio {

namespace {

constexpr int kRate = 44100;
constexpr double kPi = 3.14159265358979323846;

std::vector<char> g_single, g_hilo, g_hilo3, g_tri, g_lo;
std::shared_ptr<Clip> g_real[5];  // recorded chimes (sounds/chimes/*.wav), preferred over synthesis

struct Slot {
    FMOD_CHANNEL* ch = nullptr;
    std::shared_ptr<Clip> clip;  // keeps PCM alive while FMOD reads it
    unsigned gen = 0;
    bool stopping = false;
    bool finished_flag = false;
    float vol = 1.f;  // channel volume before the cabin gain
};
Slot g_slots[kKinds];
std::vector<std::pair<std::shared_ptr<Clip>, double>> g_retired;
double g_now = 0;
float g_master = 1.f;  // cabin gain: where the listener is relative to the cabin speakers

// refcon encodes kind (low 8 bits) and generation (rest)
void on_complete(void* refcon, FMOD_RESULT) {
    uintptr_t r = (uintptr_t)refcon;
    int kind = (int)(r & 0xff);
    unsigned gen = (unsigned)(r >> 8);
    if (kind < 0 || kind >= kKinds) return;
    Slot& s = g_slots[kind];
    if (s.gen != gen) return;  // stale
    if (!s.stopping) s.finished_flag = true;
    s.ch = nullptr;
    s.clip.reset();
    s.stopping = false;
}

// Airbus cabin chime tone, modelled on analysed recordings of the real A320 chimes:
// a pure sine (no measurable overtones), ~5 ms attack, exponential decay of ~22 dB/s.
void add_tone(std::vector<float>& buf, double start_s, double freq, double dur_s, double amp) {
    size_t a = (size_t)(start_s * kRate);
    size_t n = (size_t)(dur_s * kRate);
    if (buf.size() < a + n) buf.resize(a + n, 0.f);
    const double k = 22.0 / 20.0 * std::log(10.0);  // 22 dB/s
    for (size_t i = 0; i < n; ++i) {
        double t = (double)i / kRate;
        double attack = std::min(1.0, t / 0.005);
        double release = std::min(1.0, (dur_s - t) / 0.05);  // avoid a click at the tail
        double env = attack * release * std::exp(-t * k);
        buf[a + i] += (float)(std::sin(2 * kPi * freq * t) * env * amp);
    }
}

std::vector<char> to_pcm16(const std::vector<float>& f) {
    std::vector<char> out(f.size() * 2);
    int16_t* o = (int16_t*)out.data();
    for (size_t i = 0; i < f.size(); ++i) {
        float v = std::max(-1.f, std::min(1.f, f[i]));
        o[i] = (int16_t)(v * 32000);
    }
    return out;
}

void build_chimes() {
    // Measured from CC0 A320 recordings: single/"hi" = B4 494 Hz, "lo" = G4 392 Hz,
    // tri-tone = G4 392 -> D5 587 -> B4 494 at ~0.95 s spacing.
    // Fallback only (real recordings are used when present). Real A320: hi = D5 587 Hz,
    // lo = B4 494 Hz, hi-lo = D5 -> B4, tri-tone = G4 392 -> D5 -> B4.
    const double hi = 587.3, lo = 493.9, g4 = 392.0, d5 = 587.3;
    std::vector<float> b;
    add_tone(b, 0.0, hi, 2.6, 0.6);
    g_single = to_pcm16(b);

    b.clear();
    add_tone(b, 0.0, hi, 2.4, 0.55);
    add_tone(b, 0.70, lo, 2.6, 0.55);
    g_hilo = to_pcm16(b);

    b.clear();
    for (int k = 0; k < 3; ++k) {
        add_tone(b, k * 1.5, hi, 2.0, 0.5);
        add_tone(b, k * 1.5 + 0.70, lo, 2.2, 0.5);
    }
    g_hilo3 = to_pcm16(b);

    b.clear();
    add_tone(b, 0.0, g4, 2.4, 0.55);
    add_tone(b, 0.95, d5, 2.4, 0.55);
    add_tone(b, 1.90, lo, 2.6, 0.55);
    g_tri = to_pcm16(b);

    b.clear();
    add_tone(b, 0.0, lo, 2.6, 0.6);
    g_lo = to_pcm16(b);
}

uint32_t rd32(const unsigned char* p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }
uint16_t rd16(const unsigned char* p) { return (uint16_t)(p[0] | (p[1] << 8)); }

}  // namespace

std::shared_ptr<Clip> load_wav(const std::string& path, std::string* err) {
    std::ifstream f(path, std::ios::binary);
    if (!f) { if (err) *err = "cannot open"; return nullptr; }
    std::vector<unsigned char> d((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    if (d.size() < 44 || memcmp(d.data(), "RIFF", 4) || memcmp(d.data() + 8, "WAVE", 4)) {
        if (err) *err = "not a WAV file";
        return nullptr;
    }
    int fmt = 0, ch = 0, rate = 0, bits = 0;
    const unsigned char* data = nullptr;
    size_t data_len = 0;
    size_t p = 12;
    while (p + 8 <= d.size()) {
        uint32_t len = rd32(&d[p + 4]);
        const unsigned char* body = &d[p + 8];
        size_t avail = d.size() - (p + 8);
        if (!memcmp(&d[p], "fmt ", 4) && len >= 16 && avail >= 16) {
            fmt = rd16(body);
            ch = rd16(body + 2);
            rate = (int)rd32(body + 4);
            bits = rd16(body + 14);
            if (fmt == 0xFFFE && len >= 40) fmt = rd16(body + 24);  // WAVE_FORMAT_EXTENSIBLE subformat
        } else if (!memcmp(&d[p], "data", 4)) {
            data = body;
            data_len = std::min<size_t>(len, avail);
        }
        p += 8 + len + (len & 1);
    }
    if (!data || ch < 1 || ch > 2 || rate <= 0) { if (err) *err = "unsupported WAV layout"; return nullptr; }
    auto c = std::make_shared<Clip>();
    c->rate = rate;
    c->channels = ch;
    if (fmt == 1 && bits == 16) {
        c->pcm.assign((const char*)data, (const char*)data + (data_len & ~(size_t)1));
    } else if (fmt == 1 && bits == 8) {
        c->pcm.resize(data_len * 2);
        int16_t* o = (int16_t*)c->pcm.data();
        for (size_t i = 0; i < data_len; ++i) o[i] = (int16_t)((data[i] - 128) << 8);
    } else if (fmt == 1 && bits == 24) {
        size_t n = data_len / 3;
        c->pcm.resize(n * 2);
        int16_t* o = (int16_t*)c->pcm.data();
        for (size_t i = 0; i < n; ++i) o[i] = (int16_t)(data[i * 3 + 1] | (data[i * 3 + 2] << 8));
    } else if (fmt == 3 && bits == 32) {
        size_t n = data_len / 4;
        c->pcm.resize(n * 2);
        int16_t* o = (int16_t*)c->pcm.data();
        for (size_t i = 0; i < n; ++i) {
            float v;
            memcpy(&v, data + i * 4, 4);
            v = std::max(-1.f, std::min(1.f, v));
            o[i] = (int16_t)(v * 32767);
        }
    } else {
        if (err) *err = "unsupported WAV encoding (use PCM 16-bit)";
        return nullptr;
    }
    return c;
}

void init() { build_chimes(); }

void shutdown() {
    for (int k = 0; k < kKinds; ++k) stop((Kind)k);
}

void load_chimes(const std::string& dir) {
    static const char* names[5] = {"hi.wav", "hilo.wav", "emer.wav", "tri.wav", "lo.wav"};
    for (int i = 0; i < 5; ++i) g_real[i] = load_wav(dir + "/" + names[i], nullptr);
}

void play_chime(Chime c) {
    if (auto& clip = g_real[(int)c]) {
        FMOD_CHANNEL* ch = XPLMPlayPCMOnBus(clip->pcm.data(), (int)clip->pcm.size(), FMOD_SOUND_FORMAT_PCM16,
                                            clip->rate, clip->channels, 0, xplm_AudioInterior, nullptr, nullptr);
        if (ch) XPLMSetAudioVolume(ch, g_master);
        return;
    }
    std::vector<char>& b = c == Chime::Single ? g_single : c == Chime::HiLo ? g_hilo : c == Chime::Tri ? g_tri
                           : c == Chime::Lo ? g_lo : g_hilo3;
    if (b.empty()) return;
    // Fire-and-forget; buffers are static so they outlive the channel.
    FMOD_CHANNEL* ch = XPLMPlayPCMOnBus(b.data(), (int)b.size(), FMOD_SOUND_FORMAT_PCM16, kRate, 1, 0,
                                        xplm_AudioInterior, nullptr, nullptr);
    if (ch) XPLMSetAudioVolume(ch, g_master);
}

bool play(Kind k, std::shared_ptr<Clip> clip, float volume, bool loop) {
    if (!clip || clip->pcm.empty()) return false;
    stop(k);
    Slot& s = g_slots[k];
    s.gen++;
    s.clip = clip;
    s.finished_flag = false;
    s.stopping = false;
    void* ref = (void*)(((uintptr_t)s.gen << 8) | (uintptr_t)k);
    s.ch = XPLMPlayPCMOnBus(clip->pcm.data(), (int)clip->pcm.size(), FMOD_SOUND_FORMAT_PCM16, clip->rate,
                            clip->channels, loop ? 1 : 0, xplm_AudioInterior, on_complete, ref);
    if (!s.ch) { s.clip.reset(); return false; }
    s.vol = volume;
    XPLMSetAudioVolume(s.ch, volume * g_master);
    return true;
}

void stop(Kind k) {
    Slot& s = g_slots[k];
    if (s.ch) {
        s.stopping = true;
        FMOD_CHANNEL* ch = s.ch;
        s.ch = nullptr;
        XPLMStopAudio(ch);  // may call on_complete synchronously
    }
    // Retire the PCM for a few seconds: FMOD may still own the sound briefly.
    if (s.clip) g_retired.push_back({s.clip, g_now + 5.0});
    s.clip.reset();
    s.gen++;  // ignore any late completion for the old channel
    s.stopping = false;
}

void tick(double now) {
    g_now = now;
    for (size_t i = 0; i < g_retired.size();) {
        if (g_retired[i].second < now) {
            g_retired[i] = g_retired.back();
            g_retired.pop_back();
        } else ++i;
    }
}

bool is_playing(Kind k) { return g_slots[k].ch != nullptr; }

void set_volume(Kind k, float v) {
    g_slots[k].vol = v;
    if (g_slots[k].ch) XPLMSetAudioVolume(g_slots[k].ch, v * g_master);
}

void set_master(float m) {
    if (std::fabs(m - g_master) < 0.005f) return;
    g_master = m;
    for (auto& s : g_slots)
        if (s.ch) XPLMSetAudioVolume(s.ch, s.vol * g_master);
}

float master() { return g_master; }

bool consume_finished(Kind k) {
    bool f = g_slots[k].finished_flag;
    g_slots[k].finished_flag = false;
    return f;
}

}  // namespace fap_audio
