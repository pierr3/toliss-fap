// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 pierr3 and ToLiss FAP contributors
// Cabin audio for the FAP: synthesized chimes, plus WAV playback for boarding
// music and prerecorded announcements, all through XPLMPlayPCMOnBus.
#pragma once
#include <memory>
#include <string>
#include <vector>

namespace fap_audio {

struct Clip {
    std::vector<char> pcm;  // interleaved PCM16
    int rate = 44100;
    int channels = 1;
};

// Loads a PCM16 WAV (mono/stereo, any sample rate). 8-bit/float WAVs are converted.
std::shared_ptr<Clip> load_wav(const std::string& path, std::string* err);

// Order matches the recorded files loaded by load_chimes(): hi, hilo, emer, tri, lo.
enum class Chime { Single = 0, HiLo = 1, HiLoX3 = 2, Tri = 3, Lo = 4 };
void load_chimes(const std::string& dir);

void init();
void shutdown();

void play_chime(Chime c);

// Flight-deck door keypad sounds (synthesized): key click beep at the keypad, and the
// access-request buzzer heard in the cockpit. Played at full level (not the cabin PA gain).
enum class Beep { Key = 0, DoorBuzzer = 1 };
void play_beep(Beep b);

// Channel kinds; each kind plays one sound at a time (new one replaces old).
enum Kind { kMusic = 0, kAnnounce = 1, kKinds = 2 };
bool play(Kind k, std::shared_ptr<Clip> clip, float volume, bool loop);
void stop(Kind k);
bool is_playing(Kind k);
void set_volume(Kind k, float v);

// Cabin gain (0..1) applied on top of every channel volume, including chimes.
void set_master(float m);
float master();

// Call regularly (seconds, monotonic) to release retired buffers.
void tick(double now);

// True once after a clip of that kind finished on its own (not via stop()).
bool consume_finished(Kind k);

}  // namespace fap_audio
