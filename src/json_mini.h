// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 pierr3 and ToLiss FAP contributors
// Minimal JSON helpers: a writer for building state, and a flat-object reader
// for the small {"a":"action","k":v} messages the FAP page sends us.
#pragma once
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>

namespace jm {

inline std::string esc(const std::string& s) {
    std::string o;
    o.reserve(s.size() + 2);
    for (unsigned char c : s) {
        switch (c) {
        case '"': o += "\\\""; break;
        case '\\': o += "\\\\"; break;
        case '\n': o += "\\n"; break;
        case '\r': o += "\\r"; break;
        case '\t': o += "\\t"; break;
        default:
            if (c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); o += b; }
            else o += (char)c;
        }
    }
    return o;
}

inline std::string str(const std::string& s) { return "\"" + esc(s) + "\""; }

inline std::string num(double v, int prec = 3) {
    if (!(v == v)) return "0";  // NaN guard
    char b[64];
    snprintf(b, sizeof b, "%.*f", prec, v);
    // trim trailing zeros
    std::string s(b);
    if (s.find('.') != std::string::npos) {
        while (!s.empty() && s.back() == '0') s.pop_back();
        if (!s.empty() && s.back() == '.') s.pop_back();
    }
    if (s == "-0") s = "0";
    return s;
}

// Parses a flat JSON object: {"k":"str","n":12.5,"b":true,"z":null}.
// Nested values are skipped. Values are returned as raw strings (strings unescaped).
inline std::map<std::string, std::string> parse_flat(const char* p) {
    std::map<std::string, std::string> out;
    if (!p) return out;
    auto ws = [&]() { while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t') ++p; };
    auto rstr = [&](std::string& s) -> bool {
        if (*p != '"') return false;
        ++p;
        while (*p && *p != '"') {
            if (*p == '\\' && p[1]) {
                ++p;
                switch (*p) {
                case 'n': s += '\n'; break;
                case 't': s += '\t'; break;
                case 'r': s += '\r'; break;
                case 'u': { // keep ASCII range only
                    char h[5] = {0};
                    for (int i = 0; i < 4 && p[1]; ++i) h[i] = *++p;
                    long cp = strtol(h, nullptr, 16);
                    s += (cp < 128) ? (char)cp : '?';
                    break;
                }
                default: s += *p;
                }
                ++p;
            } else s += *p++;
        }
        if (*p == '"') ++p;
        return true;
    };
    ws();
    if (*p != '{') return out;
    ++p;
    for (;;) {
        ws();
        if (*p == '}' || !*p) break;
        std::string k, v;
        if (!rstr(k)) break;
        ws();
        if (*p != ':') break;
        ++p;
        ws();
        if (*p == '"') rstr(v);
        else if (*p == '{' || *p == '[') {  // skip nested
            int depth = 0;
            bool instr = false;
            do {
                if (instr) { if (*p == '\\' && p[1]) ++p; else if (*p == '"') instr = false; }
                else if (*p == '"') instr = true;
                else if (*p == '{' || *p == '[') ++depth;
                else if (*p == '}' || *p == ']') --depth;
                ++p;
            } while (*p && depth > 0);
        } else {
            while (*p && *p != ',' && *p != '}') v += *p++;
            while (!v.empty() && (v.back() == ' ' || v.back() == '\n')) v.pop_back();
        }
        out[k] = v;
        ws();
        if (*p == ',') { ++p; continue; }
        if (*p == '}') break;
        break;
    }
    return out;
}

inline double getd(const std::map<std::string, std::string>& m, const char* k, double def = 0) {
    auto it = m.find(k);
    if (it == m.end() || it->second.empty() || it->second == "null") return def;
    if (it->second == "true") return 1;
    if (it->second == "false") return 0;
    return atof(it->second.c_str());
}

inline std::string gets(const std::map<std::string, std::string>& m, const char* k) {
    auto it = m.find(k);
    return it == m.end() ? std::string() : it->second;
}

}  // namespace jm
