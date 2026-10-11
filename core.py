import math
import numpy as np
import pygame
import json
import os
import ctypes
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader

# ===================== CONFIG =====================
WIDTH, HEIGHT = 960, 720
FPS = 60
SEED = 1337
MAX_TRAIL = 20
MAX_SHAPES = 32
MAX_CHECKPOINTS = 8
SAVE_FILE = "threshold_save.json"

# ===================== MATH =====================
def sd_circle(p, c, r): return float(np.linalg.norm(p - c)) - r
def sd_segment(p, a, b, r):
    pa = p - a; ba = b - a
    h = float(np.clip(np.dot(pa, ba) / max(float(np.dot(ba, ba)), 1e-6), 0.0, 1.0))
    return float(np.linalg.norm(pa - ba * h)) - r
def sd_box(p, c, b, rot=0.0):
    d = p - c
    ca, sa = math.cos(rot), math.sin(rot)
    d = np.array([d[0]*ca + d[1]*sa, -d[0]*sa + d[1]*ca])
    q = np.abs(d) - b
    return float(np.linalg.norm(np.maximum(q, 0.0)) + min(max(q[0], q[1]), 0.0))
def lerp(a, b, t): return a + (b - a) * t

# ===================== SHADERS =====================
VERTEX_SHADER = """
#version 330 core
layout (location = 0) in vec2 aPos;
layout (location = 1) in vec2 aUv;
out vec2 vUv;
void main() {
    vUv = aUv;
    gl_Position = vec4(aPos, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = r"""
#version 330 core
out vec4 FragColor;
in vec2 vUv;

uniform vec2 uResolution;
uniform float uTime;
uniform vec2 uCamOffset;
uniform float uZoom;
uniform float uReduceMotion;
uniform float uMenuMode;

uniform vec2 uPlayerPos;
uniform vec2 uPlayerScale;
uniform float uPlayerRadius;
uniform float uPlayerAngle;
uniform float uPlayerDashCD;
uniform float uPlayerThrust;
uniform float uPlayerInvuln;
uniform vec3 uPlayerColor;

uniform vec4 uBoxes[32];
uniform float uBoxRots[32];
uniform vec3 uBoxColors[32];
uniform int  uBoxCount;

uniform vec4 uCircles[32];
uniform vec3 uCircleColors[32];
uniform int  uCircleCount;

uniform vec4 uLasers[8];
uniform float uLaserPhases[8];
uniform int  uLaserCount;

uniform vec3 uOrbs[16];
uniform int  uOrbCollected[16];
uniform int  uOrbCount;

uniform vec3 uCheckpoints[8];
uniform int  uCheckpointActive[8];
uniform int  uCheckpointCount;

uniform vec2 uGoalPos;
uniform float uGoalActive;

uniform vec3 uBgColor;
uniform vec3 uAccentColor;

uniform vec3 uTrail[20];
uniform int  uTrailCount;
uniform float uDamageFlash;
uniform float uLevelClearFlash;
uniform float uRespawnFlash;

float hash(vec2 p) {
    p = fract(p * vec2(443.897, 441.423));
    p += dot(p, p.yx + 19.19);
    return fract((p.x + p.y) * p.x);
}
float noise(vec2 p) {
    vec2 i = floor(p); vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1,0)), f.x),
               mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), f.x), f.y);
}
float fbm(vec2 p) {
    float v = 0.0; float a = 0.5;
    for (int i = 0; i < 5; i++) { v += a * noise(p); p *= 2.0; a *= 0.5; }
    return v;
}

float sdCircle(vec2 p, vec2 c, float r) { return length(p - c) - r; }
float sdBox(vec2 p, vec2 c, vec2 b, float rot) {
    vec2 d = p - c;
    float ca = cos(rot), sa = sin(rot);
    d = vec2(d.x*ca + d.y*sa, -d.x*sa + d.y*ca);
    vec2 q = abs(d) - b;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
}
float sdSegment(vec2 p, vec2 a, vec2 b, float r) {
    vec2 pa = p - a, ba = b - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 0.0001), 0.0, 1.0);
    return length(pa - ba * h) - r;
}
float sdEllipse(vec2 p, vec2 c, vec2 ab) {
    vec2 d = p - c;
    ab = max(ab, vec2(0.001));
    float k1 = length(d / ab);
    float k2 = length(d / (ab * ab));
    return k1 * (k1 - 1.0) / max(k2, 0.001);
}

vec3 ACESFilm(vec3 x) {
    const float a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

void main() {
    vec2 baseUv = vUv * uResolution;
    vec2 p = (baseUv - uResolution * 0.5) / uZoom + uResolution * 0.5 + uCamOffset;
    float t = uTime;

    if (uDamageFlash > 0.1) {
        float glitch = step(0.92, hash(vec2(floor(vUv.y * 30.0), floor(t * 20.0))));
        p.x += glitch * 40.0 * uDamageFlash;
    }

    float d = 1e9;
    float hazardD = 1e9;
    vec3 wallCol = vec3(0.0);

    float bD = sdBox(p, vec2(480.0, -30.0), vec2(530.0, 80.0), 0.0);
    bD = min(bD, sdBox(p, vec2(480.0, 750.0), vec2(530.0, 80.0), 0.0));
    bD = min(bD, sdBox(p, vec2(-30.0, 360.0), vec2(80.0, 410.0), 0.0));
    bD = min(bD, sdBox(p, vec2(990.0, 360.0), vec2(80.0, 410.0), 0.0));
    d = min(d, bD);
    wallCol += uAccentColor * step(bD, d);

    for(int i=0; i<32; i++) {
        if(i >= uBoxCount) break;
        float boxD = sdBox(p, uBoxes[i].xy, uBoxes[i].zw, uBoxRots[i]);
        if(boxD < d) { d = boxD; wallCol = uBoxColors[i]; }
    }
    for(int i=0; i<32; i++) {
        if(i >= uCircleCount) break;
        float circD = sdCircle(p, uCircles[i].xy, uCircles[i].z);
        if(circD < d) { d = circD; wallCol = uCircleColors[i]; }
    }
    for(int i=0; i<8; i++) {
        if(i >= uLaserCount) break;
        float ang = t * uLasers[i].z + uLaserPhases[i];
        vec2 dir = vec2(cos(ang), sin(ang)) * uLasers[i].w;
        hazardD = min(hazardD, sdSegment(p, uLasers[i].xy - dir, uLasers[i].xy + dir, 5.0));
    }

    float playerBodyD = sdEllipse(p, uPlayerPos, uPlayerScale * uPlayerRadius);
    vec2 beamDir = vec2(cos(uPlayerAngle), sin(uPlayerAngle));
    vec2 nosePos = uPlayerPos + beamDir * uPlayerRadius * 0.7;
    float noseD = sdCircle(p, nosePos, uPlayerRadius * 0.38);
    float playerD = min(playerBodyD, noseD);

    float orbD = 1e9;
    for(int i=0; i<16; i++) {
        if(i >= uOrbCount) break;
        if(uOrbCollected[i] == 0) {
            float r = uOrbs[i].z + sin(t * 4.0 + float(i) * 1.5) * 2.0;
            orbD = min(orbD, sdCircle(p, uOrbs[i].xy, r));
        }
    }

    float goalD = 1e9;
    if(uGoalActive > 0.5) {
        goalD = sdCircle(p, uGoalPos, 26.0 + sin(t * 5.0) * 4.0);
    }

    vec3 col = vec3(0.0);
    vec2 center = vec2(480.0, 360.0);
    float distToCenter = length(p - center) / length(center);
    vec3 bgCol = mix(uBgColor * 1.3, uBgColor * 0.05, distToCenter);

    if(uReduceMotion < 0.5) {
        vec2 nebUv = p / 180.0 + vec2(t * 0.02, t * 0.015);
        float neb = fbm(nebUv * 2.0);
        neb = pow(neb, 2.5);
        bgCol += uAccentColor * 1.5 * neb * (1.0 - distToCenter * 0.6);

        float aurora = sin(p.x * 0.008 + t * 0.3 + fbm(p*0.01) * 5.0) * 0.5 + 0.5;
        aurora *= smoothstep(0.3, 0.8, fbm(p * 0.015 - t * 0.05));
        bgCol += uAccentColor * 0.4 * aurora;

        vec2 starUv = p * 0.25 + vec2(t * 0.5, -t * 0.3);
        vec2 starCell = floor(starUv);
        float starHash = hash(starCell);
        if (starHash > 0.985) {
            vec2 starFrac = fract(starUv) - 0.5;
            float starDist = length(starFrac);
            float twinkle = 0.5 + 0.5 * sin(t * 4.0 + starHash * 50.0);
            float starVal = exp(-starDist * 30.0) * twinkle;
            vec3 starCol = mix(vec3(0.7, 0.8, 1.0), vec3(1.0, 0.85, 0.7), starHash);
            bgCol += starCol * starVal * 1.5;
        }

        vec2 grid = abs(fract(p / 40.0) - 0.5);
        float gridLine = smoothstep(0.48, 0.5, max(grid.x, grid.y));
        bgCol += uBgColor * 0.7 * gridLine * 0.35;

        vec2 grid2 = abs(fract(p / 200.0) - 0.5);
        float gridLine2 = smoothstep(0.495, 0.5, max(grid2.x, grid2.y));
        bgCol += uAccentColor * 1.5 * gridLine2 * 0.45;
    }
    col = bgCol;

    float wallGlow = exp(-max(d, 0.0) / 22.0) * 0.7;
    col += wallCol * wallGlow + uAccentColor * wallGlow * 0.3;

    float contour = abs(sin((d + t * 8.0) * 3.14159 / 25.0));
    col += wallCol * 1.5 * smoothstep(0.92, 1.0, contour) * 0.5 * step(0.0, d);

    if(d < 0.0) {
        float depth = clamp(-d / 50.0, 0.0, 1.0);
        vec3 inner = mix(wallCol * 1.4, wallCol * 0.15, depth);
        float scan = 0.85 + 0.15 * sin(p.y * 0.3 + t * 2.0);
        col = mix(col, inner * scan, 0.92);
    }
    col += wallCol * exp(-d*d / 5.0) * 1.8;

    col += vec3(1.0, 0.23, 0.23) * exp(-max(hazardD, 0.0) / 14.0) * 1.5;
    col += vec3(1.0, 0.85, 0.7) * exp(-max(hazardD, 0.0) / 4.0) * 0.9;
    if(hazardD < 0.0) col = vec3(1.0, 0.5, 0.5);

    for(int i=0; i<8; i++) {
        if(i >= uCheckpointCount) break;
        float cpD = sdCircle(p, uCheckpoints[i].xy, uCheckpoints[i].z);
        if(uCheckpointActive[i] > 0) {
            float pulse = 0.6 + 0.4 * sin(t * 3.0 + float(i) * 1.2);
            col += uAccentColor * exp(-max(cpD, 0.0) / 14.0) * pulse * 1.3;
            float angle = atan(p.y - uCheckpoints[i].y, p.x - uCheckpoints[i].x);
            float ring = abs(cpD) - 3.0;
            float ringMask = exp(-abs(ring) / 2.5) * 0.8 * pulse;
            float arc = 0.5 + 0.5 * sin(angle * 5.0 + t * 3.0);
            col += (uAccentColor + vec3(0.2)) * ringMask * (0.4 + 0.6 * arc);
            if(cpD < 0.0) {
                float spiral = 0.5 + 0.5 * sin(angle * 3.0 - t * 2.0 + length(p - uCheckpoints[i].xy) * 0.2);
                col = mix(col, uAccentColor * (0.7 + 0.3 * spiral), 0.35);
            }
        } else {
            col += vec3(0.35, 0.35, 0.45) * exp(-max(cpD, 0.0) / 12.0) * 0.5;
            col += vec3(0.4, 0.4, 0.5) * exp(-abs(cpD) / 2.5) * 0.3;
        }
    }

    col += uAccentColor * exp(-max(orbD, 0.0) / 18.0) * 1.7;
    col += vec3(0.85, 1.0, 0.92) * exp(-max(orbD, 0.0) / 5.0) * 0.7;
    if(orbD < 0.0) col = vec3(0.65, 1.0, 0.88);

    for(int i=0; i<20; i++) {
        if(i >= uTrailCount) break;
        float td = length(p - uTrail[i].xy);
        float trailGlow = exp(-td / 14.0) * (1.0 - uTrail[i].z) * 0.55;
        col += uPlayerColor * trailGlow;
    }

    if (uPlayerPos.x > -500.0) {
        if (uPlayerThrust > 0.5) {
            vec2 flameStart = uPlayerPos - beamDir * uPlayerRadius * 0.5;
            vec2 flameEnd = uPlayerPos - beamDir * (uPlayerRadius * 2.5 + sin(t * 40.0) * 4.0);
            float flameD = sdSegment(p, flameStart, flameEnd, uPlayerRadius * 0.5);
            float flicker = 0.8 + 0.2 * sin(t * 50.0);
            col += mix(vec3(1.0, 0.4, 0.1), vec3(1.0, 0.9, 0.5), exp(-flameD/3.0)) * exp(-max(flameD, 0.0) / 4.0) * 1.5 * flicker;
        }
        vec2 beamEnd = uPlayerPos + beamDir * 52.0;
        float beamD = sdSegment(p, uPlayerPos, beamEnd, 2.0);
        col += uPlayerColor * exp(-max(beamD, 0.0) / 3.5) * 0.5;

        if (uPlayerInvuln > 0.5) {
            float shieldD = sdCircle(p, uPlayerPos, uPlayerRadius + 8.0);
            col += uPlayerColor * exp(-abs(shieldD) / 1.5) * 0.8 * (0.5 + 0.5 * sin(t * 10.0));
        }
        if (uPlayerDashCD > 0.5) {
            float ringR = uPlayerRadius + 6.0;
            float ringD = abs(length(p - uPlayerPos) - ringR) - 0.8;
            col += vec3(0.4, 1.0, 0.8) * exp(-abs(ringD) / 1.5) * 0.8 * (0.6 + 0.4 * sin(t * 6.0));
        }
        float playerGlow = exp(-max(playerD, 0.0) / 14.0) * 1.9;
        col += uPlayerColor * playerGlow;
        col += vec3(1.0) * exp(-max(playerD, 0.0) / 4.0) * 0.7;
        if(playerD < 0.0) {
            vec3 playerInner = mix(uPlayerColor, vec3(1.0), length(p - uPlayerPos) / uPlayerRadius * 0.5);
            col = playerInner;
        }
    }

    if(uGoalActive > 0.5) {
        vec2 gp = p - uGoalPos;
        float goalAngle = atan(gp.y, gp.x);
        float swirl = sin(goalAngle * 5.0 + t * 4.0 - length(gp) * 0.15);
        col += uAccentColor * exp(-max(goalD, 0.0) / 22.0) * 1.7;
        col += vec3(1.0, 0.65, 0.78) * exp(-max(goalD, 0.0) / 6.0) * 0.9;
        if(goalD < 0.0) {
            col = mix(uAccentColor, vec3(1.0, 0.85, 0.92), 0.5 + 0.5 * swirl);
        }
        float haloD = length(gp);
        col += uAccentColor * exp(-haloD / 60.0) * 0.15 * (0.5 + 0.5 * sin(t * 3.0));
    }

    if(uReduceMotion < 0.5) {
        vec2 uv = vUv * 2.0 - 1.0;
        float r2 = dot(uv, uv);
        uv *= 1.0 + r2 * (0.015 + uDamageFlash * 0.04);
        uv = uv * 0.5 + 0.5;
        float scan = sin(uv.y * uResolution.y * 3.1415 * 2.0) * 0.035 + 0.965;
        col *= scan;
        float vig = smoothstep(1.05, 0.25, length(uv - 0.5) * 1.45);
        col *= vig;
        float grain = (hash(vUv * uResolution + t * 60.0) - 0.5) * 0.035;
        col += grain;
    }

    col = mix(col, vec3(1.0, 0.1, 0.1), uDamageFlash * 0.55);
    col = mix(col, vec3(0.4, 1.0, 0.6), uLevelClearFlash * 0.5);
    col = mix(col, uAccentColor, uRespawnFlash * 0.55);

    if (uMenuMode > 0.5) col *= 0.35;
    col = ACESFilm(col * 1.15);
    col = pow(col, vec3(1.0 / 2.2));
    FragColor = vec4(col, 1.0);
}
"""

class Shader:
    def __init__(self, vert_src, frag_src):
        self.program = compileProgram(compileShader(vert_src, GL_VERTEX_SHADER), compileShader(frag_src, GL_FRAGMENT_SHADER))
        self.uniforms = {}
    def use(self): glUseProgram(self.program)
    def get_loc(self, name):
        if name not in self.uniforms:
            self.uniforms[name] = glGetUniformLocation(self.program, name)
        return self.uniforms[name]
    def set_1f(self, name, v): glUniform1f(self.get_loc(name), float(v))
    def set_2f(self, name, v0, v1): glUniform2f(self.get_loc(name), float(v0), float(v1))
    def set_3f(self, name, v0, v1, v2): glUniform3f(self.get_loc(name), float(v0), float(v1), float(v2))
    def set_1i(self, name, v): glUniform1i(self.get_loc(name), int(v))
    def set_4fv(self, name, count, arr): glUniform4fv(self.get_loc(name), count, np.array(arr, dtype=np.float32))
    def set_3fv(self, name, count, arr): glUniform3fv(self.get_loc(name), count, np.array(arr, dtype=np.float32))
    def set_1fv(self, name, count, arr): glUniform1fv(self.get_loc(name), count, np.array(arr, dtype=np.float32))
    def set_1iv(self, name, count, arr): glUniform1iv(self.get_loc(name), count, np.array(arr, dtype=np.int32))

class Mesh:
    def __init__(self, vertices):
        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)
        self.vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        stride = vertices.itemsize * 4
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(8))
    def draw(self):
        glBindVertexArray(self.vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

class AudioEngine:
    def __init__(self):
        self.available = False
        self.muted = False
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            self.available = True
            self.sr = 44100
            self._generate_sounds()
        except Exception:
            self.available = False

    def _make_sound(self, samples):
        stereo = np.column_stack([samples, samples])
        stereo = np.clip(stereo, -1.0, 1.0)
        return pygame.sndarray.make_sound((stereo * 32767).astype(np.int16))

    def _generate_sounds(self):
        sr = self.sr
        t = np.linspace(0, 0.15, int(sr * 0.15))
        env = np.exp(-t * 12)
        wave = env * np.sin(2 * np.pi * (150 + 600 * (t / 0.15)) * t) * 0.25
        wave += env * (np.random.random(len(t)) - 0.5) * 0.15
        self.sounds = {'dash': self._make_sound(wave)}

        t = np.linspace(0, 0.25, int(sr * 0.25))
        env = np.exp(-t * 7)
        wave = env * np.sin(2 * np.pi * (523 + 440 * (t / 0.25)) * t) * 0.25
        wave += env * np.sin(2 * np.pi * (523 + 440 * (t / 0.25)) * 1.5 * t) * 0.12
        self.sounds['orb'] = self._make_sound(wave)

        t = np.linspace(0, 0.1, int(sr * 0.1))
        env = np.exp(-t * 15)
        wave = env * np.sin(2 * np.pi * 800 * t) * 0.2
        self.sounds['select'] = self._make_sound(wave)

        t = np.linspace(0, 0.4, int(sr * 0.4))
        env = np.exp(-t * 4)
        wave = env * np.sin(2 * np.pi * 523 * t) * 0.15
        wave += env * np.sin(2 * np.pi * 659 * t) * 0.12
        wave += env * np.sin(2 * np.pi * 784 * t) * 0.1
        self.sounds['checkpoint'] = self._make_sound(wave)

        t = np.linspace(0, 0.12, int(sr * 0.12))
        env = np.exp(-t * 18)
        wave = env * np.sin(2 * np.pi * 300 * t) * 0.3
        wave += env * (np.random.random(len(t)) - 0.5) * 0.1
        self.sounds['bounce'] = self._make_sound(wave)

        t = np.linspace(0, 0.4, int(sr * 0.4))
        env = np.exp(-t * 5)
        wave = env * np.sin(2 * np.pi * (70 + 30 * np.sin(t * 15)) * t) * 0.4
        wave += env * (np.random.random(len(t)) - 0.5) * 0.25
        self.sounds['hit'] = self._make_sound(wave)

        t = np.linspace(0, 1.2, int(sr * 1.2))
        wave = np.zeros_like(t)
        notes = [523, 659, 784, 1047, 1319]
        for i, f in enumerate(notes):
            mask = (t >= i * 0.15) & (t < (i + 1) * 0.3)
            local_t = t[mask] - i * 0.15
            wave[mask] += np.sin(2 * np.pi * f * t[mask]) * np.exp(-local_t * 5) * 0.25
        self.sounds['win'] = self._make_sound(wave)

    def play(self, name, volume=1.0):
        if not self.available or self.muted: return
        if name in self.sounds:
            self.sounds[name].set_volume(volume)
            self.sounds[name].play()

    def toggle_mute(self):
        self.muted = not self.muted
        return self.muted

class TextRenderer:
    def __init__(self):
        self.font_sm = pygame.font.SysFont("Arial", 16, bold=True)
        self.font = pygame.font.SysFont("Arial", 20, bold=True)
        self.font_md = pygame.font.SysFont("Arial", 32, bold=True)
        self.font_big = pygame.font.SysFont("Arial", 54, bold=True)
        self.font_huge = pygame.font.SysFont("Arial", 80, bold=True)
        self.cache = {}
    def get_texture(self, text, font, color):
        key = (text, font, color)
        if key not in self.cache:
            surf = font.render(text, True, color).convert_alpha()
            data = pygame.image.tostring(surf, 'RGBA', True)
            tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, surf.get_width(), surf.get_height(), 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
            self.cache[key] = (tex, surf.get_width(), surf.get_height())
        return self.cache[key]
    def render(self, text, x, y, font=None, color=(255, 255, 255)):
        if font is None: font = self.font
        tex, w, h = self.get_texture(text, font, color)
        glUseProgram(0)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex)
        x0 = (x / WIDTH) * 2.0 - 1.0
        y0 = 1.0 - (y / HEIGHT) * 2.0
        x1 = ((x + w) / WIDTH) * 2.0 - 1.0
        y1 = 1.0 - ((y + h) / HEIGHT) * 2.0
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x0, y0)
        glTexCoord2f(1, 0); glVertex2f(x1, y0)
        glTexCoord2f(1, 1); glVertex2f(x1, y1)
        glTexCoord2f(0, 1); glVertex2f(x0, y1)
        glEnd()
        glDisable(GL_TEXTURE_2D)
    def render_centered(self, text, cx, cy, font=None, color=(255, 255, 255)):
        if font is None: font = self.font
        tex, w, h = self.get_texture(text, font, color)
        self.render(text, cx - w // 2, cy - h // 2, font, color)
    def render_quad(self, x, y, w, h, color):
        r, g, b, a = color
        glUseProgram(0)
        glDisable(GL_TEXTURE_2D)
        glColor4f(r/255.0, g/255.0, b/255.0, a/255.0)
        x0 = (x / WIDTH) * 2.0 - 1.0
        y0 = 1.0 - (y / HEIGHT) * 2.0
        x1 = ((x + w) / WIDTH) * 2.0 - 1.0
        y1 = 1.0 - ((y + h) / HEIGHT) * 2.0
        glBegin(GL_QUADS)
        glVertex2f(x0, y0); glVertex2f(x1, y0)
        glVertex2f(x1, y1); glVertex2f(x0, y1)
        glEnd()
        glColor4f(1, 1, 1, 1)

class InputManager:
    def __init__(self):
        self.keys = set()
        self.keys_pressed = set()
        self.keys_released = set()
    def update(self):
        self.keys_pressed.clear()
        self.keys_released.clear()
    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            self.keys.add(e.key)
            self.keys_pressed.add(e.key)
        elif e.type == pygame.KEYUP:
            self.keys.discard(e.key)
            self.keys_released.add(e.key)
    def is_down(self, k): return k in self.keys
    def is_pressed(self, k): return k in self.keys_pressed
    def is_released(self, k): return k in self.keys_released

class SaveSystem:
    @staticmethod
    def load():
        if os.path.exists(SAVE_FILE):
            try:
                with open(SAVE_FILE, 'r') as f:
                    return json.load(f)
            except: pass
        return {"best_times": {}, "unlocked": ["0"]}
    @staticmethod
    def save(data):
        with open(SAVE_FILE, 'w') as f:
            json.dump(data, f, indent=4)
