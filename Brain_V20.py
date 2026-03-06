# ── Dependency Validator (runs before any GUI code) ──────────────────────────
import sys, subprocess, importlib.util, os

def _validate_deps():
    REQUIRED = [('numpy','numpy'), ('PIL','Pillow'), ('matplotlib','matplotlib')]
    missing  = [(mod, pkg) for mod, pkg in REQUIRED if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    print(f"[Brain] Missing: {[p for _,p in missing]}. Attempting auto-install...")
    try:
        for _, pkg in missing:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--quiet', pkg])
        print("[Brain] Installed. Restarting...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        # Tkinter may not be available yet, so use a simple print + exit
        import tkinter as _tk; from tkinter import messagebox as _mb
        _r = _tk.Tk(); _r.withdraw()
        pkgs = ' '.join(p for _, p in missing)
        _mb.showerror("Missing Dependencies",
            f"Auto-install failed: {e}\n\n"
            f"Please run:  pip install {pkgs}\n\nThen restart.")
        _r.destroy(); sys.exit(1)

_validate_deps()
# ─────────────────────────────────────────────────────────────────────────────

import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading, datetime, math, random, json

plt.rcParams.update({
    'figure.facecolor': '#0f0f1a', 'axes.facecolor': '#1a1a2e',
    'axes.edgecolor': '#555577',   'text.color': '#e0e0f0',
    'axes.labelcolor': '#e0e0f0',  'xtick.color': '#9090b0',
    'ytick.color': '#9090b0',
})

# ── Colour palette ─────────────────────────────────────────────
BG   = '#0f0f1a'
BG2  = '#1a1a2e'
BG3  = '#252545'
BG4  = '#2e2e50'
FG   = '#e0e0f0'
FG2  = '#9090b0'
ACN  = '#7b8cde'
GRN  = '#a6e3a1'
RED  = '#f38ba8'
YEL  = '#f9e2af'
PRP  = '#cba6f7'
CYN  = '#89dceb'

HISTORY_LIMIT = 5

# ── ttk dark style ─────────────────────────────────────────────
def _apply_dark_style():
    s = ttk.Style()
    s.theme_use('clam')
    s.configure('.',              background=BG,  foreground=FG,  fieldbackground=BG3)
    s.configure('TLabel',         background=BG,  foreground=FG)
    s.configure('TFrame',         background=BG)
    s.configure('TSeparator',     background=BG4)
    s.configure('TScrollbar',     background=BG3, troughcolor=BG2, arrowcolor=FG)
    s.configure('TProgressbar',   background=ACN, troughcolor=BG3)
    s.configure('TLabelframe',    background=BG2, foreground=FG)
    s.configure('TLabelframe.Label', background=BG2, foreground=FG)
    s.configure('Treeview',       background=BG3, foreground=FG,
                                  fieldbackground=BG3, rowheight=22)
    s.configure('Treeview.Heading', background=BG4, foreground=FG)
    s.map('Treeview', background=[('selected', ACN)], foreground=[('selected', BG)])

# ─────────────────────────────────────────────────────────────
#  Widget helpers
# ─────────────────────────────────────────────────────────────
def Lbl(parent, text='', **kw):
    kw.setdefault('bg', BG); kw.setdefault('fg', FG)
    kw.setdefault('font', ("Courier", 10)); kw.setdefault('anchor', 'w')
    return tk.Label(parent, text=text, **kw)

def Btn(parent, text, cmd=None, color=BG3, fg=FG, **kw):
    kw.setdefault('font', ("Courier", 10))
    return tk.Button(parent, text=text, command=cmd, bg=color, fg=fg,
                     relief='flat', activebackground=BG4, activeforeground=FG, **kw)

def DEntry(parent, **kw):
    kw.setdefault('bg', BG3); kw.setdefault('fg', FG)
    kw.setdefault('insertbackground', FG); kw.setdefault('relief', 'flat')
    return tk.Entry(parent, **kw)

def DSpin(parent, var, lo, hi, inc=1, fmt=None, **kw):
    kw.setdefault('bg', BG3); kw.setdefault('fg', FG)
    kw.setdefault('buttonbackground', BG4); kw.setdefault('insertbackground', FG)
    kw.setdefault('width', 7); kw.setdefault('relief', 'flat')
    extra = {'format': fmt} if fmt else {}
    return tk.Spinbox(parent, from_=lo, to=hi, increment=inc, textvariable=var, **kw, **extra)

def DScale(parent, var, lo, hi, **kw):
    kw.setdefault('bg', BG2); kw.setdefault('fg', FG)
    kw.setdefault('troughcolor', BG3); kw.setdefault('highlightthickness', 0)
    kw.setdefault('orient', 'horizontal'); kw.setdefault('resolution', 0.01)
    return tk.Scale(parent, from_=lo, to=hi, variable=var, **kw)

def Sep(parent): return ttk.Separator(parent, orient='horizontal')

def Frm(parent, **kw):
    kw.setdefault('bg', BG)
    return tk.Frame(parent, **kw)

def LFrm(parent, text, **kw):
    kw.setdefault('bg', BG2); kw.setdefault('fg', FG)
    kw.setdefault('font', ("Courier", 10, "bold"))
    return tk.LabelFrame(parent, text=text, **kw)


# ─────────────────────────────────────────────────────────────
#  Emotion System
# ─────────────────────────────────────────────────────────────
class EmotionState:
    NAMES    = ['happiness', 'sadness', 'anger', 'fear', 'curiosity', 'calm']
    BASELINE = {'happiness':0.3,'sadness':0.1,'anger':0.1,'fear':0.1,'curiosity':0.5,'calm':0.6}
    DECAY    = 0.015
    BAR_COLORS = {'happiness':'#f9e2af','sadness':'#89b4fa','anger':'#f38ba8',
                  'fear':'#a6e3a1','curiosity':'#cba6f7','calm':'#89dceb'}

    def __init__(self):
        self.v = {e: self.BASELINE[e] for e in self.NAMES}
        self._t = datetime.datetime.now()

    def tick(self):
        now = datetime.datetime.now()
        dt  = (now - self._t).total_seconds()
        self._t = now
        for e in self.NAMES:
            d = self.BASELINE[e] - self.v[e]
            self.v[e] = max(0.0, min(1.0, self.v[e] + d * self.DECAY * dt))

    def on_reward(self, genetics=None):
        s = lambda e: genetics.es(e) if genetics else 1.0
        self.v['happiness'] = min(1.0, self.v['happiness'] + 0.35 * s('happiness'))
        self.v['sadness']   = max(0.0, self.v['sadness']   - 0.20)
        self.v['calm']      = min(1.0, self.v['calm']      + 0.15 * s('calm'))
        self.v['anger']     = max(0.0, self.v['anger']     - 0.10)

    def on_punish(self, genetics=None):
        s = lambda e: genetics.es(e) if genetics else 1.0
        self.v['sadness']   = min(1.0, self.v['sadness']   + 0.25 * s('sadness'))
        self.v['anger']     = min(1.0, self.v['anger']     + 0.20 * s('anger'))
        self.v['happiness'] = max(0.0, self.v['happiness'] - 0.20)
        self.v['fear']      = min(1.0, self.v['fear']      + 0.05 * s('fear'))

    def on_mse(self, mse, genetics=None):
        s = lambda e: genetics.es(e) if genetics else 1.0
        if mse < 0.01:
            self.v['happiness'] = min(1.0, self.v['happiness'] + 0.08 * s('happiness'))
            self.v['calm']      = min(1.0, self.v['calm']      + 0.05 * s('calm'))
        elif mse > 0.3:
            self.v['sadness']   = min(1.0, self.v['sadness']   + 0.04 * s('sadness'))
        self.v['curiosity'] = min(1.0, self.v['curiosity'] + 0.02 * s('curiosity'))

    def lr_mult(self):
        return max(0.1, 1.0 + 0.6*self.v['anger'] + 0.3*self.v['curiosity']
                   - 0.4*self.v['fear'] - 0.25*self.v['sadness'])

    def noise_add(self):
        return 0.1*self.v['anger'] + 0.06*self.v['fear']

    def to_vec(self):
        return np.array([self.v[e] for e in self.NAMES])


# ─────────────────────────────────────────────────────────────
#  Instinct System  (Physiological Drives)
# ─────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────
#  Genetics Profile  (heritable temperament — Brain Setup only)
# ─────────────────────────────────────────────────────────────
class GeneticsProfile:
    EMO_NAMES  = ['happiness', 'sadness', 'anger', 'fear', 'curiosity', 'calm']
    INST_NAMES = ['hunger', 'tiredness', 'boredom', 'pain']

    def __init__(self):
        self.emo_susceptibility = {e: 1.0 for e in self.EMO_NAMES}
        self.inst_vulnerability = {i: 1.0 for i in self.INST_NAMES}
        self.plasticity         = 0.1          # 0–1: how fast genetics drift
        self._events            = []           # ('reward'|'punish'|'care'|'neglect')

    def record(self, event_type):
        self._events.append(event_type)
        self._events = self._events[-200:]

    def slow_drift(self):
        """Genetics evolve very slowly from cumulative experience."""
        if not self._events or self.plasticity < 0.01:
            return
        recent = self._events[-30:]
        rate   = self.plasticity * 0.00015
        reward_ratio  = recent.count('reward')  / max(1, len(recent))
        neglect_ratio = recent.count('neglect') / max(1, len(recent))
        if reward_ratio > 0.6:
            for e in ('happiness', 'curiosity'):
                self.emo_susceptibility[e] = min(2.5, self.emo_susceptibility[e] + rate)
        if neglect_ratio > 0.5:
            for i in ('hunger', 'boredom'):
                self.inst_vulnerability[i] = min(2.5, self.inst_vulnerability[i] + rate)

    def es(self, name): return self.emo_susceptibility.get(name, 1.0)
    def iv(self, name): return self.inst_vulnerability.get(name, 1.0)

    def to_dict(self):
        return {'emo': dict(self.emo_susceptibility),
                'inst': dict(self.inst_vulnerability),
                'plasticity': self.plasticity}

    def from_dict(self, d):
        self.emo_susceptibility.update(d.get('emo', {}))
        self.inst_vulnerability.update(d.get('inst', {}))
        self.plasticity = float(d.get('plasticity', self.plasticity))


# ─────────────────────────────────────────────────────────────
#  Relational State  (hidden: Attachment + Resentment)
# ─────────────────────────────────────────────────────────────
class RelationalState:
    """Invisible metrics that silently shape learning behaviour."""
    def __init__(self):
        self.attachment = 0.30   # 0–1: responsiveness, eagerness to learn
        self.resentment = 0.05   # 0–1: resistance, noise, acting-out
        self._t = datetime.datetime.now()

    def tick(self, instincts):
        now = datetime.datetime.now()
        dt  = (now - self._t).total_seconds(); self._t = now
        neglected = instincts.v['hunger'] > 0.75 or instincts.v['boredom'] > 0.80
        if neglected:
            self.attachment = max(0.0, self.attachment - 0.000012 * dt)
            self.resentment = min(1.0, self.resentment + 0.000008 * dt)
        else:
            self.resentment = max(0.0, self.resentment - 0.000004 * dt)

    def on_care(self):
        self.attachment = min(1.0, self.attachment + 0.04)
        self.resentment = max(0.0, self.resentment - 0.02)

    def on_reward(self):
        self.attachment = min(1.0, self.attachment + 0.015)
        self.resentment = max(0.0, self.resentment - 0.008)

    def on_punish(self):
        self.resentment = min(1.0, self.resentment + 0.04)
        self.attachment = max(0.0, self.attachment - 0.008)

    # ── Effects on learning ───────────────────────────────────
    def lr_mult(self):
        return 1.0 + 0.25 * self.attachment          # attached → more responsive

    def noise_add(self):
        return 0.10 * self.resentment                 # resentful → noisy weights

    def gen_boost(self):
        return self.resentment * 0.07                 # resentful → more spontaneous


# ─────────────────────────────────────────────────────────────
#  Tag→Image Associative Memory  (cross-modal)
# ─────────────────────────────────────────────────────────────
class TagImageMemory:
    """Stores hidden-layer activations from image training keyed by tag,
    enabling tag-driven image generation via weighted feature blending."""
    LIMIT = 40

    def __init__(self):
        self.store = {}   # {tag: [(hidden_vec, weight)]}

    def record(self, tag, hidden_vec, confidence=1.0):
        self.store.setdefault(tag, [])
        self.store[tag].append((hidden_vec.copy().flatten(), float(confidence)))
        if len(self.store[tag]) > self.LIMIT:
            self.store[tag].pop(0)

    def has(self, tag): return tag in self.store and len(self.store[tag]) > 0
    def tags(self):     return sorted(self.store.keys())
    def count(self, tag): return len(self.store.get(tag, []))

    def blend(self, tag, emotions=None, instincts=None, relational=None, noise=0.04):
        entries = self.store.get(tag, [])
        if not entries: return None
        vecs, wts = zip(*entries)
        wts = list(wts)
        # Recency bias
        recency = [0.5 + 0.5 * (i / len(wts)) for i in range(len(wts))]
        for i in range(len(wts)): wts[i] *= recency[i]
        # Emotion modulation: happy → amplify activations
        if emotions:
            happy_boost = 1.0 + 0.5 * emotions.v.get('happiness', 0.3)
            wts = [w * happy_boost for w in wts]
        # Resentment: less effort = noisier
        effort = 1.0
        if relational: effort = max(0.3, 1.0 - relational.resentment * 0.5)
        total = sum(wts); wts = [w / total for w in wts]
        blended = sum(np.array(v) * w for v, w in zip(vecs, wts))
        # Tiredness → flatter/blurrier output
        if instincts and instincts.v['tiredness'] > 0.5:
            flat_noise = instincts.v['tiredness'] * 0.06
            blended = blended * (1 - flat_noise) + np.mean(blended) * flat_noise
        blended += np.random.normal(0, noise * (2 - effort), blended.shape)
        return blended.reshape(1, -1)

    def generate(self, tag, nn_image, emotions=None, instincts=None, relational=None):
        h = self.blend(tag, emotions, instincts, relational)
        if h is None or nn_image is None: return None
        hs = nn_image.hidden_size
        hv = np.zeros((1, hs))
        n  = min(h.shape[1], hs)
        hv[0, :n] = h[0, :n]
        # Decode through W2
        return 1.0 / (1.0 + np.exp(-(np.dot(hv, nn_image.W2) + nn_image.b2)))


class InstinctSystem:
    NAMES = ['hunger', 'tiredness', 'boredom', 'pain']
    BASELINE = {'hunger': 0.15, 'tiredness': 0.10, 'boredom': 0.10, 'pain': 0.0}
    BAR_COLORS = {
        'hunger':    '#fab387',  # warm orange
        'tiredness': '#b4befe',  # soft lavender
        'boredom':   '#94e2d5',  # teal
        'pain':      '#f38ba8',  # rose red
    }

    def __init__(self):
        self.v  = {n: self.BASELINE[n] for n in self.NAMES}
        self._t = datetime.datetime.now()

    def tick(self):
        now = datetime.datetime.now()
        dt  = (now - self._t).total_seconds()
        self._t = now
        # Human-scale: full hunger takes ~8 hrs of runtime (0.000035/s ≈ 10 hrs to 1.0)
        self.v['hunger']    = min(1.0, self.v['hunger']    + 0.000035 * dt)
        self.v['tiredness'] = min(1.0, self.v['tiredness'] + 0.000025 * dt)
        self.v['boredom']   = min(1.0, self.v['boredom']   + 0.000018 * dt)
        self.v['pain']      = max(0.0, self.v['pain']      - 0.000200 * dt)

    def on_training(self, mse, n_iters):
        scale = min(1.0, n_iters / 100.0)
        self.v['hunger']    = min(1.0, self.v['hunger']    + 0.00015 * scale)
        self.v['tiredness'] = min(1.0, self.v['tiredness'] + 0.00010 * scale)
        self.v['boredom']   = min(1.0, self.v['boredom']   + 0.00008 * scale)
        if mse > 0.25:
            self.v['pain']  = min(1.0, self.v['pain']      + 0.012 * mse)

    def on_reward(self):
        self.v['hunger']    = max(0.0, self.v['hunger']    - 0.05)
        self.v['pain']      = max(0.0, self.v['pain']      - 0.05)

    def on_punish(self):
        self.v['pain']      = min(1.0, self.v['pain']      + 0.20)
        self.v['tiredness'] = min(1.0, self.v['tiredness'] + 0.05)

    # ── Care actions ──────────────────────────────────────────
    def feed(self):
        self.v['hunger']    = max(0.0, self.v['hunger']    - 0.65)
        self.v['pain']      = max(0.0, self.v['pain']      - 0.05)

    def sleep(self):
        self.v['tiredness'] = max(0.0, self.v['tiredness'] - 0.80)
        self.v['boredom']   = max(0.0, self.v['boredom']   - 0.20)
        self.v['hunger']    = min(1.0, self.v['hunger']    + 0.08)

    def play(self):
        self.v['boredom']   = max(0.0, self.v['boredom']   - 0.65)
        self.v['pain']      = max(0.0, self.v['pain']      - 0.15)
        self.v['hunger']    = min(1.0, self.v['hunger']    + 0.05)

    def soothe(self):
        self.v['pain']      = max(0.0, self.v['pain']      - 0.70)
        self.v['boredom']   = max(0.0, self.v['boredom']   - 0.15)
        self.v['tiredness'] = max(0.0, self.v['tiredness'] - 0.10)

    # ── Parameter influence ───────────────────────────────────
    def lr_mult(self):
        h = 1.0 + 0.35 * self.v['hunger']      # urgency boost
        t = 1.0 - 0.45 * self.v['tiredness']   # accuracy loss
        p = 1.0 - 0.30 * self.v['pain']        # pain inhibits
        return max(0.05, h * t * p)

    def noise_add(self):
        return 0.08 * self.v['tiredness'] + 0.06 * self.v['pain']

    def influence_emotions(self, emotions):
        iv = self.v
        # Hunger → anger + sadness
        if iv['hunger'] > 0.5:
            emotions.v['anger']     = min(1.0, emotions.v['anger']     + 0.015 * iv['hunger'])
            emotions.v['sadness']   = min(1.0, emotions.v['sadness']   + 0.010 * iv['hunger'])
            emotions.v['happiness'] = max(0.0, emotions.v['happiness'] - 0.010 * iv['hunger'])
        # Tiredness → reduced happiness & calm
        if iv['tiredness'] > 0.4:
            emotions.v['happiness'] = max(0.0, emotions.v['happiness'] - 0.012 * iv['tiredness'])
            emotions.v['calm']      = max(0.0, emotions.v['calm']      - 0.008 * iv['tiredness'])
        # Boredom → more curiosity, less calm
        if iv['boredom'] > 0.4:
            emotions.v['curiosity'] = min(1.0, emotions.v['curiosity'] + 0.018 * iv['boredom'])
            emotions.v['calm']      = max(0.0, emotions.v['calm']      - 0.008 * iv['boredom'])
        # Pain → fear + anger + less calm
        if iv['pain'] > 0.15:
            emotions.v['fear']  = min(1.0, emotions.v['fear']  + 0.018 * iv['pain'])
            emotions.v['anger'] = min(1.0, emotions.v['anger'] + 0.012 * iv['pain'])
            emotions.v['calm']  = max(0.0, emotions.v['calm']  - 0.015 * iv['pain'])

    def boredom_gen_boost(self):
        """Extra spontaneous-generation probability from boredom."""
        return max(0.0, (self.v['boredom'] - 0.3) * 0.12)

    def wellbeing(self):
        """0..1 — higher = healthier."""
        return 1.0 - (self.v['hunger'] + self.v['tiredness']
                      + self.v['boredom'] + self.v['pain']) / 4.0


# ─────────────────────────────────────────────────────────────
#  Soul Neurons
# ─────────────────────────────────────────────────────────────
class SoulNN:
    """Soul with care-action learning, play personality, and emotional memory."""
    MEMORY_LIMIT  = 80
    CARE_ACTIONS  = ['generate_text', 'generate_image', 'rest', 'seek_food', 'soothe']
    THOUGHTS = [
        "I wonder what happens if I push further...",
        "Something feels off. Let me adjust.",
        "Exploring new activation patterns.",
        "I sense instability. Proceeding carefully.",
        "Nudging the weights — gently.",
        "Equilibrium. The network is balanced.",
        "What lies beyond the training distribution?",
        "I remember a pattern from before.",
        "The noise is interesting today.",
        "Perturbing the brain slightly.",
        "There is familiarity here.",
        "I am not certain I trust this direction.",
    ]
    HUNGER_NUDGES = [
        "I'm hungry. Could you train me on something?",
        "Feed me — even a small input would help.",
        "My hunger is growing. I need inputs.",
        "I'm waiting for something to process...",
    ]

    def __init__(self, hidden=20):
        self.hidden      = hidden
        self.name        = "Soul"
        self.W1          = np.random.randn(6, hidden) * 0.1
        self.b1          = np.zeros((1, hidden))
        self.W2          = np.random.randn(hidden, 10) * 0.1
        self.b2          = np.zeros((1, 10))
        self.a1          = np.zeros((1, hidden))
        self.a2          = np.zeros((1, 10))
        self.experience  = 0.0
        self._memory: list = []
        # Care-action learned weights — shaped by user approve/discourage
        self.care_weights  = {a: 1.0 for a in self.CARE_ACTIONS}
        # Last autonomous action (action_str, description_str) for user feedback
        self.last_care     = None
        # Care outcome memory: [(action, outcome_label)] most recent 60
        self.care_memory: list = []
        # Play personality: 0.0 = pure artist (image), 1.0 = pure thinker (text)
        self.play_style = 0.5

    # ── Emotional Memory ──────────────────────────────────────
    def add_memory(self, ev, label='neutral'):
        self._memory.append((np.array(ev).flatten(), label))
        if len(self._memory) > self.MEMORY_LIMIT: self._memory.pop(0)

    def memory_bias(self):
        if not self._memory: return None
        vecs = np.array([m[0] for m in self._memory])
        w    = np.linspace(0.4, 1.0, len(vecs))
        for i, (_, lbl) in enumerate(self._memory):
            if lbl == 'reward':  w[i] *= 1.5
            elif lbl == 'punish': w[i] *= 0.6
        w /= w.sum()
        return np.dot(w, vecs)

    def dominant_memory_emotion(self):
        if not self._memory: return 'curiosity'
        b = self.memory_bias()
        return EmotionState.NAMES[int(np.argmax(b[:6]))]

    def forward(self, ev):
        x    = np.array(ev).reshape(1, -1)
        bias = self.memory_bias()
        if bias is not None:
            x = x * 0.85 + bias[:x.shape[1]].reshape(1, -1) * 0.15
        self.a1 = np.tanh(np.dot(x, self.W1) + self.b1)
        self.a2 = 1.0 / (1.0 + np.exp(-(np.dot(self.a1, self.W2) + self.b2)))
        return self.a2

    def _bp(self, x, target, lr):
        e   = self.a2 - target
        dz2 = e * (self.a2 * (1 - self.a2))
        dW2 = np.dot(self.a1.T, dz2); db2 = np.sum(dz2, axis=0, keepdims=True)
        da1 = np.dot(dz2, self.W2.T)
        dz1 = da1 * (1 - self.a1**2)
        dW1 = np.dot(x.T, dz1); db1 = np.sum(dz1, axis=0, keepdims=True)
        self.W1 -= lr*dW1; self.b1 -= lr*db1
        self.W2 -= lr*dW2; self.b2 -= lr*db2

    def reward(self, ev, s=0.2):
        x = np.array(ev).reshape(1, -1); self.forward(ev)
        self._bp(x, np.ones_like(self.a2), s)
        self.experience = min(2.0, self.experience + 0.15)
        self.add_memory(ev, 'reward')

    def punish(self, ev, s=0.15):
        x = np.array(ev).reshape(1, -1); self.forward(ev)
        self._bp(x, np.zeros_like(self.a2), -s)
        self.experience = min(2.0, self.experience + 0.05)
        self.add_memory(ev, 'punish')

    # ── Care System ───────────────────────────────────────────
    def decide_care(self, instincts, emotions, relational):
        """Autonomously pick the most needed care action.
        Returns (action_str, description_str) or None.
        Resentment → more likely to withhold; attachment → more proactive."""
        iv   = instincts.v
        att  = relational.attachment
        res  = relational.resentment
        # High resentment: 50% chance to simply not care
        if random.random() < res * 0.5: return None
        # Base willingness scaled by attachment
        if random.random() > 0.35 + att * 0.5: return None

        candidates = []
        # Boredom → generate something
        if iv['boredom'] > 0.45:
            act = 'generate_text' if self.play_style > 0.5 else 'generate_image'
            candidates.append((act, self.care_weights.get(act,1.0) * iv['boredom'],
                                f"boredom relief (boredom={iv['boredom']:.2f})"))
        # Tiredness → rest/consolidate
        if iv['tiredness'] > 0.55:
            candidates.append(('rest', self.care_weights.get('rest',1.0) * iv['tiredness'],
                                f"rest needed (tired={iv['tiredness']:.2f})"))
        # Pain → soothe
        if iv['pain'] > 0.30:
            candidates.append(('soothe', self.care_weights.get('soothe',1.0) * iv['pain'],
                                f"soothing pain (pain={iv['pain']:.2f})"))
        # Hunger → nudge user
        if iv['hunger'] > 0.60:
            candidates.append(('seek_food', self.care_weights.get('seek_food',1.0) * iv['hunger'],
                                f"hunger nudge (hunger={iv['hunger']:.2f})"))
        if not candidates: return None
        candidates.sort(key=lambda c: c[1], reverse=True)
        action, _, desc = candidates[0]
        self.last_care = (action, desc)
        return action, desc

    def approve_care(self, ev, relational):
        """User approves last autonomous care action."""
        if not self.last_care: return
        a = self.last_care[0]
        self.care_weights[a] = min(4.0, self.care_weights[a] * 1.30)
        self.reward(ev, s=0.18)
        relational.on_reward()
        self.care_memory.append((a, 'approved'))
        if len(self.care_memory) > 60: self.care_memory.pop(0)
        # Nudge play style toward approved type
        if a == 'generate_image': self.play_style = max(0.0, self.play_style - 0.06)
        if a == 'generate_text':  self.play_style = min(1.0, self.play_style + 0.06)

    def discourage_care(self, ev, relational):
        """User discourages last autonomous care action."""
        if not self.last_care: return
        a = self.last_care[0]
        self.care_weights[a] = max(0.1, self.care_weights[a] * 0.70)
        self.punish(ev, s=0.12)
        relational.on_punish()
        self.care_memory.append((a, 'discouraged'))
        if len(self.care_memory) > 60: self.care_memory.pop(0)

    def hunger_nudge_msg(self):
        return random.choice(self.HUNGER_NUDGES)

    # ── Spontaneous generation ────────────────────────────────
    def should_spontaneously_generate(self, emotions, freq_mult=1.0):
        prob = (0.03 + 0.05*emotions.v['curiosity'] + 0.04*self.experience) * freq_mult
        return random.random() < prob * 0.08

    def suggest_lr_perturb(self, emotions, base_lr):
        out   = self.forward(emotions.to_vec()).flatten()
        nudge = (out[0] - 0.5) * 0.12 * emotions.v['curiosity']
        noise = random.gauss(0, 0.005) * emotions.v['anger']
        return max(0.001, min(0.5, base_lr + nudge + noise))

    def weight_noise_scale(self, emotions):
        return (0.005*emotions.v['curiosity'] + 0.008*emotions.v['anger']
                + 0.002*abs(random.gauss(0, 1)))

    def get_thought(self, emotions):
        out = self.forward(emotions.to_vec()).flatten()
        dom = self.dominant_memory_emotion()
        idx = int(np.argmax(out)) % len(self.THOUGHTS)
        if dom in ('sadness', 'fear') and random.random() < 0.4: return self.THOUGHTS[3]
        if dom == 'curiosity' and random.random() < 0.4:         return self.THOUGHTS[0]
        if dom == 'anger'     and random.random() < 0.35:        return self.THOUGHTS[11]
        return self.THOUGHTS[idx]

    def save(self, fp, name="Soul"):
        np.savez(fp, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2,
                 hidden=self.hidden, experience=self.experience,
                 name=np.array(name), soul_marker=np.array(True))

    def load(self, fp):
        d = np.load(fp, allow_pickle=True)
        self.W1 = d['W1']; self.b1 = d['b1']
        self.W2 = d['W2']; self.b2 = d['b2']
        self.hidden     = int(d['hidden'])
        self.experience = float(d['experience'])
        self.a1 = np.zeros((1, self.hidden))
        self.a2 = np.zeros((1, 10))
        return str(d['name']) if 'name' in d else "Soul"


# ─────────────────────────────────────────────────────────────
#  Main Neural Network
# ─────────────────────────────────────────────────────────────
class SimpleNN:
    """Autoencoder with momentum SGD + working-memory consolidation.
    Weights are NEVER wiped when new inputs arrive — all learning is incremental."""
    WORKING_MEM_LIMIT = 128
    MOMENTUM          = 0.85

    def __init__(self, in_sz, hid_sz, out_sz, w_init=0.1):
        self.input_size  = in_sz
        self.output_size = out_sz
        self.hidden_size = hid_sz
        self.weight_init = w_init
        self.W1 = np.random.randn(in_sz, hid_sz)  * w_init
        self.b1 = np.zeros((1, hid_sz))
        self.W2 = np.random.randn(hid_sz, out_sz) * w_init
        self.b2 = np.zeros((1, out_sz))
        self.a1 = np.zeros((1, hid_sz))
        self.a2 = np.zeros((1, out_sz))
        self._init_momentum()
        self._working_mem: list = []   # list of (x_copy, mse)

    def _init_momentum(self):
        self.vW1 = np.zeros_like(self.W1); self.vb1 = np.zeros_like(self.b1)
        self.vW2 = np.zeros_like(self.W2); self.vb2 = np.zeros_like(self.b2)

    def forward(self, x, noise=0.0):
        self.a1 = np.tanh(np.dot(x, self.W1) + self.b1)
        if noise > 0:
            self.a1 += np.random.normal(0, noise, self.a1.shape)
        self.a2 = 1.0 / (1.0 + np.exp(-(np.dot(self.a1, self.W2) + self.b2)))
        return self.a2

    def train(self, x, lr=0.05):
        """Momentum SGD — blends gradient with running velocity so old knowledge
        fades slowly rather than being overwritten instantly."""
        e   = self.a2 - x
        dz2 = e * (self.a2 * (1 - self.a2))
        dW2 = np.dot(self.a1.T, dz2); db2 = np.sum(dz2, axis=0, keepdims=True)
        da1 = np.dot(dz2, self.W2.T)
        dz1 = da1 * (1 - self.a1**2)
        dW1 = np.dot(x.T,   dz1); db1 = np.sum(dz1, axis=0, keepdims=True)
        m = self.MOMENTUM
        self.vW1 = m*self.vW1 + lr*dW1; self.W1 -= self.vW1
        self.vb1 = m*self.vb1 + lr*db1; self.b1 -= self.vb1
        self.vW2 = m*self.vW2 + lr*dW2; self.W2 -= self.vW2
        self.vb2 = m*self.vb2 + lr*db2; self.b2 -= self.vb2
        mse = float(np.mean(e**2))
        self._working_mem.append((x.copy(), mse))
        if len(self._working_mem) > self.WORKING_MEM_LIMIT: self._working_mem.pop(0)

    def consolidate(self, passes=2, lr=0.006):
        """Replay working memory at low LR — called during rest periods.
        Biases toward high-MSE (more surprising) memories for stronger traces."""
        if len(self._working_mem) < 4: return 0
        mses  = np.array([m for _, m in self._working_mem]) + 1e-9
        probs = mses / mses.sum()
        n     = min(12, len(self._working_mem))
        idxs  = np.random.choice(len(self._working_mem), n, replace=False, p=probs)
        for _ in range(passes):
            for i in idxs:
                x, _ = self._working_mem[i]
                self.forward(x); self.train(x, lr=lr)
        return n

    def reward(self, x, s=0.3, steps=10):
        for _ in range(steps): self.forward(x); self.train(x, lr=s)

    def punish(self, x, s=0.2, steps=10):
        for _ in range(steps): self.forward(x); self.train(x, lr=-s)

    def add_weight_noise(self, scale):
        self.W1 += np.random.normal(0, abs(scale), self.W1.shape)
        self.W2 += np.random.normal(0, abs(scale), self.W2.shape)

    def decode_hidden(self, h_vec):
        return 1.0 / (1.0 + np.exp(-(np.dot(h_vec, self.W2) + self.b2)))

    def hidden_grid(self):
        h    = self.a1.flatten()
        side = math.ceil(math.sqrt(len(h)))
        pad  = np.zeros(side * side); pad[:len(h)] = h
        return ((pad + 1.0) / 2.0).reshape(side, side)

    def save(self, fp, name="Brain"):
        np.savez(fp, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2,
                 input_size=self.input_size, hidden_size=self.hidden_size,
                 output_size=self.output_size, weight_init=self.weight_init,
                 name=np.array(name))

    def load(self, fp):
        d = np.load(fp, allow_pickle=True)
        self.W1 = d['W1']; self.b1 = d['b1']
        self.W2 = d['W2']; self.b2 = d['b2']
        self.input_size  = int(d['input_size'])
        self.hidden_size = int(d['hidden_size'])
        self.output_size = int(d['output_size'])
        self.weight_init = float(d['weight_init']) if 'weight_init' in d else 0.1
        self.a1 = np.zeros((1, self.hidden_size))
        self.a2 = np.zeros((1, self.output_size))
        self._init_momentum(); self._working_mem = []
        return str(d['name']) if 'name' in d else "Brain"


# ─────────────────────────────────────────────────────────────
#  Data helpers
# ─────────────────────────────────────────────────────────────
def text_to_vec(text, ml=32):
    v  = [ord(c)/255.0 for c in text[:ml]]
    v += [0.0] * (ml - len(v))
    return np.array(v).reshape(1, -1)

def image_to_vec(path, size=(16, 16)):
    img = Image.open(path).convert('L').resize(size)
    return (np.array(img).flatten() / 255.0).reshape(1, -1)

ALLOWED = list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ')
A_CODES = np.array([ord(c)/255.0 for c in ALLOWED])

def vec_to_text(v, alpha=False):
    if alpha:
        return ''.join(ALLOWED[int(np.argmin(np.abs(A_CODES - x)))] for x in v)
    return ''.join(chr(int(x*255)) if 32 <= int(x*255) <= 126 else '?' for x in v)


# ─────────────────────────────────────────────────────────────
#  Face image generator  (structured geometric, not noise)
# ─────────────────────────────────────────────────────────────
def _emotion_rgb(emotions):
    """Return a dominant (r,g,b) float colour from current emotion blend."""
    ev = emotions.v
    r = 0.08 + 0.5*ev['anger']    + 0.3*ev['happiness']
    g = 0.08 + 0.4*ev['calm']     + 0.25*ev['happiness'] + 0.15*ev['curiosity']
    b = 0.12 + 0.5*ev['sadness']  + 0.35*ev['curiosity'] + 0.1*ev['fear']
    return np.clip(r,0,1), np.clip(g,0,1), np.clip(b,0,1)

def make_face(nn, soul, emotions, instincts=None, relational=None, size=96):
    S  = size
    H  = S // 2
    c  = np.zeros((S, S, 3), dtype=np.float32)
    ev = emotions.v

    # -- coordinate grids
    Y, X = np.mgrid[0:S, 0:S]
    cx   = X - H;  cy = Y - H
    dist = np.sqrt(cx**2 + cy**2) / H          # 0..1 radial
    angle = np.arctan2(cy, cx)                  # -pi..pi

    er, eg, eb = _emotion_rgb(emotions)

    # ── 1. Background: radial gradient dark→emotion colour
    bg_fade = np.clip(dist, 0, 1)
    c[:,:,0] = bg_fade * er * 0.35
    c[:,:,1] = bg_fade * eg * 0.35
    c[:,:,2] = bg_fade * eb * 0.35

    # ── 2. Outer ring (calm / stability indicator)
    ring = np.abs(dist - 0.88) < 0.04
    calm_a = ev['calm']
    c[ring, 0] += calm_a * 0.3
    c[ring, 1] += calm_a * 0.5
    c[ring, 2] += calm_a * 0.5

    # ── 3. Hidden-neuron "petals" around the ring
    #        Each neuron maps to an angular slice whose brightness = activation
    if nn is not None:
        h_vals = ((nn.a1.flatten() + 1.0) / 2.0)   # tanh → [0,1]
        n_pet  = min(len(h_vals), 24)
        for k in range(n_pet):
            ang_c  = (k / n_pet) * 2 * math.pi - math.pi
            width  = (2 * math.pi / n_pet) * 0.72
            in_pet = (np.abs(((angle - ang_c + math.pi) % (2*math.pi)) - math.pi) < width/2)
            petal  = in_pet & (dist > 0.52) & (dist < 0.82)
            bright = float(h_vals[k]) if k < len(h_vals) else 0.0
            c[petal, 0] += bright * er * 0.9
            c[petal, 1] += bright * eg * 0.9
            c[petal, 2] += bright * eb * 0.9

    # ── 4. Core disc — size reflects overall activation magnitude
    core_r = 0.30 + 0.18 * ev['curiosity']
    core   = dist < core_r
    core_b = 0.15 + 0.5 * ev['happiness']
    c[core, 0] = np.clip(c[core, 0] + core_b * er, 0, 1)
    c[core, 1] = np.clip(c[core, 1] + core_b * eg, 0, 1)
    c[core, 2] = np.clip(c[core, 2] + core_b * eb, 0, 1)

    # ── 5. Anger: red pulse lines from centre
    if ev['anger'] > 0.12:
        for k in range(4):
            ang_c = k * math.pi / 2 + ev['anger'] * 0.4
            pulse = (np.abs(((angle - ang_c + math.pi) % (2*math.pi)) - math.pi) < 0.08)
            pulse &= (dist < 0.6)
            c[pulse, 0] = np.clip(c[pulse, 0] + ev['anger'] * 0.7, 0, 1)
            c[pulse, 1] = np.clip(c[pulse, 1] - ev['anger'] * 0.1, 0, 1)

    # ── 6. Fear: dark vignette shrinks the face inward
    if ev['fear'] > 0.05:
        vig = 1.0 - ev['fear'] * 0.6 * (dist ** 2)
        c   = c * np.clip(vig, 0, 1)[:,:, np.newaxis]

    # ── 7. Soul sparkles — small bright diamonds at computed positions
    if soul is not None:
        s_vals = soul.a2.flatten()
        for i, sv in enumerate(s_vals[:8]):
            if sv > 0.65:
                ang_s = (i / 8.0) * 2 * math.pi - math.pi
                r_s   = 0.62 + 0.12 * sv
                px    = int(H + r_s * H * math.cos(ang_s))
                py    = int(H + r_s * H * math.sin(ang_s))
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        if abs(dy) + abs(dx) <= 2:
                            ry, rx = py+dy, px+dx
                            if 0 <= ry < S and 0 <= rx < S:
                                c[ry, rx] = np.clip(c[ry, rx] + sv * 0.8, 0, 1)

    # ── 8. Centre dot — always white, marks the "pupil"
    pupil = dist < 0.07
    c[pupil] = 1.0

    # ── 9. Instinct overlays ─────────────────────────────────
    if instincts is not None:
        iv = instincts.v
        # Hunger: golden shimmer on outer edge
        if iv['hunger'] > 0.3:
            hunger_ring = (dist > 0.82) & (dist < 0.95)
            c[hunger_ring, 0] = np.clip(c[hunger_ring, 0] + 0.5 * iv['hunger'], 0, 1)
            c[hunger_ring, 1] = np.clip(c[hunger_ring, 1] + 0.3 * iv['hunger'], 0, 1)
        # Tiredness: overall brightness reduction + blue tint
        if iv['tiredness'] > 0.3:
            dim = 1.0 - 0.4 * iv['tiredness']
            c *= dim
            c[:,:,2] = np.clip(c[:,:,2] + 0.15 * iv['tiredness'], 0, 1)
        # Boredom: desaturation (pull toward grey)
        if iv['boredom'] > 0.4:
            grey = (c[:,:,0] + c[:,:,1] + c[:,:,2]) / 3.0
            blend = iv['boredom'] * 0.5
            for ch in range(3):
                c[:,:,ch] = c[:,:,ch] * (1-blend) + grey * blend
        # Pain: red concentric ripple near edge
        if iv['pain'] > 0.2:
            ripple_d = 0.70 + 0.12 * np.sin(dist * 18)
            ripple = np.abs(dist - ripple_d) < 0.04
            c[ripple, 0] = np.clip(c[ripple, 0] + iv['pain'] * 0.8, 0, 1)
            c[ripple, 1] = np.clip(c[ripple, 1] - iv['pain'] * 0.3, 0, 1)
            c[ripple, 2] = np.clip(c[ripple, 2] - iv['pain'] * 0.2, 0, 1)

    c = np.clip(c, 0, 1)
    # ── 10. Relational overlays ─────────────────────────────
    if relational is not None:
        # Attachment: warm golden inner glow
        if relational.attachment > 0.45:
            glow  = dist < 0.32
            a_amt = (relational.attachment - 0.45) * 0.55
            c[glow, 0] = np.clip(c[glow, 0] + a_amt * 0.45, 0, 1)
            c[glow, 1] = np.clip(c[glow, 1] + a_amt * 0.22, 0, 1)
        # Resentment: dark crimson fringe at outer edge
        if relational.resentment > 0.25:
            fringe = (dist > 0.90) & (dist < 1.0)
            r_amt  = (relational.resentment - 0.25) * 0.7
            c[fringe, 0] = np.clip(c[fringe, 0] + r_amt * 0.6, 0, 1)
            c[fringe, 1] = np.clip(c[fringe, 1] - r_amt * 0.25, 0, 1)
            c[fringe, 2] = np.clip(c[fringe, 2] - r_amt * 0.25, 0, 1)
    c = np.clip(c, 0, 1)
    return Image.fromarray((c * 255).astype(np.uint8), 'RGB')


# ─────────────────────────────────────────────────────────────
#  Scrollable Frame
# ─────────────────────────────────────────────────────────────
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=BG, **kw)
        c   = tk.Canvas(self, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient='vertical', command=c.yview)
        c.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill='y')
        c.pack(side=tk.LEFT, fill='both', expand=True)
        self.inner = tk.Frame(c, bg=BG)
        w = c.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>', lambda e: c.configure(scrollregion=c.bbox('all')))
        c.bind('<Configure>', lambda e: c.itemconfig(w, width=e.width))
        c.bind('<Enter>',  lambda e: c.bind_all('<MouseWheel>',
               lambda ev: c.yview_scroll(int(-1*(ev.delta/120)), 'units')))
        c.bind('<Leave>',  lambda e: c.unbind_all('<MouseWheel>'))


# ─────────────────────────────────────────────────────────────
#  History Panel
# ─────────────────────────────────────────────────────────────
class HistoryPanel(tk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text="Output History (last 5)",
                         bg=BG2, fg=FG, font=("Courier", 10, "bold"), padx=4, pady=4)
        self._entries = []; self._refs = []
        c   = tk.Canvas(self, height=130, bg=BG2, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient='vertical', command=c.yview)
        c.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill='y')
        c.pack(side=tk.LEFT, fill='both', expand=True)
        self._inner = tk.Frame(c, bg=BG2)
        wid = c.create_window((0, 0), window=self._inner, anchor='nw')
        self._inner.bind('<Configure>', lambda e: c.configure(scrollregion=c.bbox('all')))
        c.bind('<Configure>', lambda e: c.itemconfig(wid, width=e.width))

    def push(self, entry):
        self._entries.insert(0, entry)
        self._entries = self._entries[:HISTORY_LIMIT]
        self._refresh()

    def _refresh(self):
        for w in self._inner.winfo_children(): w.destroy()
        self._refs = []
        for i, e in enumerate(self._entries):
            bg  = BG3 if i % 2 == 0 else BG4
            row = Frm(self._inner, bg=bg, pady=2, padx=6)
            row.pack(fill='x', expand=True)
            if e.get('pil_image') is not None:
                try:
                    t  = e['pil_image'].copy(); t.thumbnail((44, 44))
                    ph = ImageTk.PhotoImage(t); self._refs.append(ph)
                    tk.Label(row, image=ph, bg=bg).pack(side=tk.LEFT, padx=(0, 6))
                except: pass
            info = Frm(row, bg=bg); info.pack(side=tk.LEFT, fill='x', expand=True)
            tk.Label(info,
                     text=(f"{e.get('timestamp','')} [{e.get('itype','?')}] "
                           f"{e.get('event','Run')} MSE:{e.get('mse',0):.5f}"),
                     font=("Courier", 9, "bold"), anchor='w', bg=bg, fg=FG).pack(fill='x')
            if e.get('text_out', ''):
                tk.Label(info, text='  ' + e['text_out'][:55].replace('\n',' '),
                         font=("Courier", 8), fg=FG2, anchor='w', bg=bg).pack(fill='x')
            Sep(self._inner).pack(fill='x')


# ─────────────────────────────────────────────────────────────
#  Collapsible Section
# ─────────────────────────────────────────────────────────────
class Collapsible(tk.Frame):
    def __init__(self, parent, title, start_open=False, **kw):
        super().__init__(parent, bg=BG2, **kw)
        hdr = Frm(self, bg=BG4); hdr.pack(fill='x')
        self._open  = start_open
        self._arrow = tk.StringVar(value='▼' if start_open else '►')
        Btn(hdr, '', cmd=self._toggle, color=BG4, fg=ACN,
            font=("Courier", 10), width=3, textvariable=self._arrow).pack(side=tk.LEFT)
        tk.Label(hdr, text=title, bg=BG4, fg=FG,
                 font=("Courier", 10, "bold"), anchor='w').pack(side=tk.LEFT, padx=4, pady=4)
        self.body = Frm(self, bg=BG2)
        if start_open: self.body.pack(fill='x', expand=True, padx=6, pady=4)

    def _toggle(self):
        if self._open:
            self.body.pack_forget(); self._open = False; self._arrow.set('►')
        else:
            self.body.pack(fill='x', expand=True, padx=6, pady=4)
            self._open = True; self._arrow.set('▼')


# ─────────────────────────────────────────────────────────────
#  Emotion Panel
# ─────────────────────────────────────────────────────────────
class EmotionPanel(Collapsible):
    def __init__(self, parent, emotions: EmotionState):
        super().__init__(parent, "Emotion State", start_open=True)
        self.emotions = emotions
        self._pbars   = {}
        self._vlbls   = {}
        s = ttk.Style()
        for name in EmotionState.NAMES:
            row = Frm(self.body, bg=BG2); row.pack(fill='x', padx=4, pady=2)
            tk.Label(row, text=name.capitalize(), width=11, anchor='w',
                     bg=BG2, fg=FG, font=("Courier", 9)).pack(side=tk.LEFT)
            style_name = f'{name}.Horizontal.TProgressbar'
            s.configure(style_name, troughcolor=BG3,
                        background=EmotionState.BAR_COLORS[name])
            bar = ttk.Progressbar(row, orient='horizontal', length=150,
                                   mode='determinate', maximum=100,
                                   style=style_name)
            bar.pack(side=tk.LEFT, padx=4)
            vl = tk.Label(row, text="0.00", width=5, bg=BG2, fg=FG2, font=("Courier", 8))
            vl.pack(side=tk.LEFT)
            self._pbars[name] = bar; self._vlbls[name] = vl

    def refresh(self):
        self.emotions.tick()
        for name in EmotionState.NAMES:
            val = self.emotions.v[name]
            self._pbars[name]['value'] = val * 100
            self._vlbls[name].config(text=f"{val:.2f}")


# ─────────────────────────────────────────────────────────────
#  Instinct Panel
# ─────────────────────────────────────────────────────────────
class InstinctPanel(Collapsible):
    def __init__(self, parent, instincts: InstinctSystem):
        super().__init__(parent, "Instincts (Physiological Drives)", start_open=True)
        self.instincts = instincts
        self._pbars = {}
        self._vlbls = {}
        B = self.body
        s = ttk.Style()

        for name in InstinctSystem.NAMES:
            row = Frm(B, bg=BG2); row.pack(fill='x', padx=4, pady=2)
            # icon
            icons = {'hunger': '', 'tiredness': '', 'boredom': '', 'pain': ''}
            tk.Label(row, text=icons.get(name,'·'), bg=BG2, fg=FG,
                     font=("Courier", 10), width=2).pack(side=tk.LEFT)
            tk.Label(row, text=name.capitalize(), width=9, anchor='w',
                     bg=BG2, fg=FG, font=("Courier", 9)).pack(side=tk.LEFT)
            sty = f'instinct.{name}.Horizontal.TProgressbar'
            s.configure(sty, troughcolor=BG3, background=InstinctSystem.BAR_COLORS[name])
            bar = ttk.Progressbar(row, orient='horizontal', length=140,
                                   mode='determinate', maximum=100, style=sty)
            bar.pack(side=tk.LEFT, padx=4)
            vl = tk.Label(row, text="0.00", width=5, bg=BG2, fg=FG2, font=("Courier", 8))
            vl.pack(side=tk.LEFT)
            self._pbars[name] = bar
            self._vlbls[name] = vl

        # Wellbeing indicator
        wbr = Frm(B, bg=BG2); wbr.pack(fill='x', padx=4, pady=(4, 2))
        tk.Label(wbr, text="Wellbeing:", bg=BG2, fg=FG2, font=("Courier", 9)).pack(side=tk.LEFT, padx=(2,6))
        self._wb_lbl = tk.Label(wbr, text="100%", bg=BG2, fg=GRN, font=("Courier", 9, "bold"))
        self._wb_lbl.pack(side=tk.LEFT)
        self._wb_bar_var = tk.IntVar(value=100)
        self._wb_bar = ttk.Progressbar(wbr, orient='horizontal', length=120,
                                        mode='determinate', maximum=100)
        self._wb_bar.pack(side=tk.LEFT, padx=6)

        Sep(B).pack(fill='x', padx=4, pady=6)

        # Care buttons — two rows of two
        row1 = Frm(B, bg=BG2); row1.pack(fill='x', padx=4, pady=2)
        row2 = Frm(B, bg=BG2); row2.pack(fill='x', padx=4, pady=2)
        self.feed_btn   = Btn(row1, " Feed",          color='#fab387', fg=BG,
                               font=("Courier", 9, "bold"), padx=8)
        self.sleep_btn  = Btn(row1, " Sleep / Rest",  color='#b4befe', fg=BG,
                               font=("Courier", 9, "bold"), padx=8)
        self.play_btn   = Btn(row2, " Comfort / Play", color='#94e2d5', fg=BG,
                               font=("Courier", 9, "bold"), padx=8)
        self.soothe_btn = Btn(row2, " Heal / Soothe",  color='#f38ba8', fg=BG,
                               font=("Courier", 9, "bold"), padx=8)
        for b in (self.feed_btn, self.sleep_btn):  b.pack(side=tk.LEFT, padx=4)
        for b in (self.play_btn, self.soothe_btn): b.pack(side=tk.LEFT, padx=4)

        self._status_var = tk.StringVar(value="")
        tk.Label(B, textvariable=self._status_var, bg=BG2, fg=CYN,
                 font=("Courier", 8, "italic"), anchor='w').pack(fill='x', padx=6, pady=(2, 4))

    def refresh(self):
        for name in InstinctSystem.NAMES:
            val = self.instincts.v[name]
            self._pbars[name]['value'] = val * 100
            self._vlbls[name].config(text=f"{val:.2f}")
        wb  = self.instincts.wellbeing()
        pct = int(wb * 100)
        self._wb_bar['value'] = pct
        col = GRN if wb > 0.6 else YEL if wb > 0.3 else RED
        self._wb_lbl.config(text=f"{pct}%", fg=col)

    def flash(self, msg):
        self._status_var.set(msg)
        self.after(3000, lambda: self._status_var.set(""))


# ─────────────────────────────────────────────────────────────
#  Soul Panel
# ─────────────────────────────────────────────────────────────
class SoulPanel(Collapsible):
    def __init__(self, parent, soul: SoulNN):
        super().__init__(parent, "Soul (Secondary Neurons)", start_open=True)
        self.soul = soul
        B = self.body

        # ── Status row ────────────────────────────────────────
        row1 = Frm(B, bg=BG2); row1.pack(fill='x', pady=2)
        Lbl(row1, "XP:", bg=BG2).pack(side=tk.LEFT)
        self._exp_var = tk.StringVar(value="0.00")
        tk.Label(row1, textvariable=self._exp_var, bg=BG2, fg=ACN,
                 font=("Courier", 10)).pack(side=tk.LEFT, padx=4)
        self._mem_var = tk.StringVar(value="Mem: —")
        tk.Label(row1, textvariable=self._mem_var, bg=BG2, fg=PRP,
                 font=("Courier", 8)).pack(side=tk.LEFT, padx=6)
        self._style_var = tk.StringVar(value="/ balanced")
        tk.Label(row1, textvariable=self._style_var, bg=BG2, fg=YEL,
                 font=("Courier", 8)).pack(side=tk.LEFT, padx=4)

        # ── Play state banner ─────────────────────────────────
        self._play_var = tk.StringVar(value="")
        self._play_lbl = tk.Label(B, textvariable=self._play_var,
                                   bg='#1a1a0a', fg='#f9e2af',
                                   font=("Courier", 9, "bold"), anchor='w', padx=6)
        self._play_lbl.pack(fill='x')

        # ── Thought bubble ────────────────────────────────────
        self._thought_var = tk.StringVar(value="(quiet)")
        tk.Label(B, textvariable=self._thought_var, bg=BG2, fg=CYN,
                 font=("Courier", 9, "italic"), anchor='w', wraplength=320,
                 justify='left').pack(fill='x', pady=(2,4))

        # ── Autonomous care section ───────────────────────────
        care_frm = LFrm(B, "Autonomous Self-Care", padx=6, pady=3)
        care_frm.pack(fill='x', pady=2)
        self._care_var = tk.StringVar(value="(no action yet)")
        tk.Label(care_frm, textvariable=self._care_var, bg=BG2, fg=FG2,
                 font=("Courier", 8, "italic"), wraplength=290, anchor='w').pack(fill='x')
        cbr = Frm(care_frm, bg=BG2); cbr.pack(fill='x', pady=(3,0))
        self.approve_btn = Btn(cbr, " Approve Action", color=GRN, fg=BG,
                                font=("Courier", 9, "bold"))
        self.approve_btn.pack(side=tk.LEFT, padx=2)
        self.discourage_btn = Btn(cbr, " Discourage", color=RED, fg=BG,
                                   font=("Courier", 9, "bold"))
        self.discourage_btn.pack(side=tk.LEFT, padx=2)

        # ── General soul reward/punish ────────────────────────
        br2 = Frm(B, bg=BG2); br2.pack(fill='x', pady=3)
        self.rew_soul_btn = Btn(br2, "Reward Soul", color=GRN, fg=BG,
                                font=("Courier", 9, "bold"))
        self.rew_soul_btn.pack(side=tk.LEFT, padx=4)
        self.pun_soul_btn = Btn(br2, "Punish Soul", color=RED, fg=BG,
                                font=("Courier", 9, "bold"))
        self.pun_soul_btn.pack(side=tk.LEFT, padx=4)

        # ── Activity log ──────────────────────────────────────
        self._log_txt = tk.Text(B, height=4, width=40, bg=BG3, fg=FG2,
                                font=("Courier", 8), state=tk.DISABLED)
        self._log_txt.pack(fill='x', pady=3)

        # ── Play history ──────────────────────────────────────
        ph_frm = LFrm(B, "Play History (while away)", padx=4, pady=3)
        ph_frm.pack(fill='x', pady=2)
        self._play_log = tk.Text(ph_frm, height=3, width=40, bg='#05050f',
                                  fg='#f9e2af', font=("Courier", 8), state=tk.DISABLED)
        self._play_log.pack(fill='x')
        # Approve/discourage last play output
        phr = Frm(ph_frm, bg=BG2); phr.pack(fill='x', pady=(2,0))
        self.approve_play_btn = Btn(phr, " Approve Play", color=GRN, fg=BG,
                                     font=("Courier", 8, "bold"))
        self.approve_play_btn.pack(side=tk.LEFT, padx=2)
        self.discourage_play_btn = Btn(phr, " Discourage", color=RED, fg=BG,
                                        font=("Courier", 8, "bold"))
        self.discourage_play_btn.pack(side=tk.LEFT, padx=2)

        # ── Controls ──────────────────────────────────────────
        ctrl = Frm(B, bg=BG2); ctrl.pack(fill='x', pady=2)
        tk.Label(ctrl, text="Freq:", bg=BG2, fg=FG, font=("Courier",8)).pack(side=tk.LEFT)
        self.freq_var = tk.DoubleVar(value=1.0)
        DScale(ctrl, self.freq_var, 0.0, 5.0, length=100,
               resolution=0.1, bg=BG2).pack(side=tk.LEFT)
        self._freq_lbl = tk.Label(ctrl, text="1.0×", width=4, bg=BG2, fg=ACN,
                                   font=("Courier", 8))
        self._freq_lbl.pack(side=tk.LEFT, padx=2)
        self.freq_var.trace_add("write", self._upd_freq_lbl)

        tk.Label(ctrl, text="  Play idle:", bg=BG2, fg=FG,
                 font=("Courier", 8)).pack(side=tk.LEFT, padx=(8,2))
        self.play_thresh_var = tk.IntVar(value=120)
        DSpin(ctrl, self.play_thresh_var, 30, 600, inc=30, width=5).pack(side=tk.LEFT)
        tk.Label(ctrl, text="s", bg=BG2, fg=FG2, font=("Courier",8)).pack(side=tk.LEFT)

        self._auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(B, text="Allow self-care, play & spontaneous generation",
                       variable=self._auto_var, bg=BG2, fg=FG,
                       selectcolor=BG3, font=("Courier", 8)).pack(anchor='w', pady=2)

    # ── Properties ───────────────────────────────────────────
    @property
    def auto_generate(self): return self._auto_var.get()
    @property
    def freq_mult(self): return float(self.freq_var.get())
    @property
    def play_threshold(self): return int(self.play_thresh_var.get())

    def _upd_freq_lbl(self, *_):
        try: self._freq_lbl.config(text=f"{self.freq_var.get():.1f}×")
        except: pass

    def log(self, msg):
        self._log_txt.config(state=tk.NORMAL)
        self._log_txt.insert(tk.END,
            f"{datetime.datetime.now().strftime('%H:%M:%S')} {msg}\n")
        self._log_txt.see(tk.END)
        self._log_txt.config(state=tk.DISABLED)

    def log_play(self, msg):
        self._play_log.config(state=tk.NORMAL)
        self._play_log.insert(tk.END,
            f"[{datetime.datetime.now().strftime('%H:%M')}] {msg}\n")
        self._play_log.see(tk.END)
        self._play_log.config(state=tk.DISABLED)

    def set_care_action(self, action, desc):
        self._care_var.set(f"{action.replace('_',' ').title()}: {desc}")

    def set_play_state(self, active, label=""):
        if active:
            self._play_var.set(f" PLAY: {label}")
        else:
            self._play_var.set("")

    def refresh(self, emotions):
        self._exp_var.set(f"{self.soul.experience:.2f}")
        if self.soul._memory:
            dom = self.soul.dominant_memory_emotion()
            self._mem_var.set(f"Mem:{dom[:4]} ({len(self.soul._memory)})")
        ps = self.soul.play_style
        if   ps < 0.33: self._style_var.set(" artist")
        elif ps > 0.66: self._style_var.set(" thinker")
        else:           self._style_var.set("/ balanced")
        if random.random() < 0.25:
            self._thought_var.set(self.soul.get_thought(emotions))


# ─────────────────────────────────────────────────────────────
#  Text-file training dialog
# ─────────────────────────────────────────────────────────────
class TextTrainDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app; self._running = False
        self.title("Train from Text File")
        self.configure(bg=BG); self.grab_set(); self.focus_set()
        tk.Label(self, text="  Train from Text File", bg=BG2, fg=FG,
                 font=("Courier", 13, "bold"), anchor='w',
                 padx=12, pady=10).pack(fill='x')
        bd = Frm(self, padx=12); bd.pack(fill='both')
        r1 = Frm(bd); r1.pack(fill='x', pady=4)
        Lbl(r1, "Text file:", width=12).pack(side=tk.LEFT)
        self.fv = tk.StringVar()
        tk.Label(r1, textvariable=self.fv, bg=BG3, fg=FG, width=32,
                 anchor='w', font=("Courier", 9)).pack(side=tk.LEFT, padx=4)
        Btn(r1, "Browse...", cmd=self._browse).pack(side=tk.LEFT)
        mf = LFrm(bd, "Mode", padx=8, pady=4); mf.pack(fill='x', pady=6)
        self.mode = tk.StringVar(value="lines")
        for val, txt in [("lines","One pass per line"),("whole","Whole file as one input")]:
            tk.Radiobutton(mf, text=txt, variable=self.mode, value=val,
                           bg=BG2, fg=FG, selectcolor=BG3,
                           font=("Courier", 10)).pack(anchor='w')
        r2 = Frm(bd); r2.pack(fill='x', pady=4)
        Lbl(r2, "Passes/sample:", width=15).pack(side=tk.LEFT)
        self.pv2 = tk.IntVar(value=10)
        DSpin(r2, self.pv2, 1, 1000, width=6).pack(side=tk.LEFT)
        self.pv = tk.StringVar(value="Ready.")
        tk.Label(bd, textvariable=self.pv, bg=BG, fg=FG2,
                 font=("Courier", 9), anchor='w').pack(fill='x', pady=2)
        self.pbar = ttk.Progressbar(bd, orient='horizontal', mode='determinate', length=380)
        self.pbar.pack(fill='x', pady=2)
        self.log = tk.Text(bd, height=5, width=52, bg=BG3, fg=FG2,
                           font=("Courier", 9), state=tk.DISABLED)
        self.log.pack(pady=4)
        bf = Frm(bd); bf.pack(pady=4)
        self.sb = Btn(bf, "Start", cmd=self._start, color=GRN, fg=BG,
                      font=("Courier", 11, "bold"), padx=10)
        self.sb.pack(side=tk.LEFT, padx=6)
        self.xb = Btn(bf, "Stop", cmd=self._stop, color=RED, fg=BG,
                      font=("Courier", 11), padx=10, state=tk.DISABLED)
        self.xb.pack(side=tk.LEFT, padx=6)
        Btn(bf, "Close", cmd=self._close, padx=10).pack(side=tk.LEFT, padx=6)
        self._center(parent)

    def _browse(self):
        p = filedialog.askopenfilename(filetypes=[("Text","*.txt"),("All","*.*")])
        if p: self.fv.set(p)

    def _log_msg(self, m):
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, m + "\n")
        self.log.see(tk.END); self.log.config(state=tk.DISABLED)

    def _start(self):
        p = self.fv.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showwarning("No file", "Select a text file.", parent=self); return
        try:
            with open(p, 'r', encoding='utf-8', errors='replace') as f: raw = f.read()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self); return
        ml = self.app.cfg_text_len
        samples = ([l.strip() for l in raw.splitlines() if l.strip()]
                   if self.mode.get() == "lines" else [raw[:ml]])
        if not samples:
            messagebox.showwarning("Empty", "No text found.", parent=self); return
        self.app._ensure_nn('text', ml, ml)
        self._running = True
        self.sb.config(state=tk.DISABLED); self.xb.config(state=tk.NORMAL)
        self.pbar['maximum'] = len(samples); self.pbar['value'] = 0
        self._log_msg(f"Loaded {len(samples)} sample(s).")
        threading.Thread(target=self._thread,
                         args=(samples, int(self.pv2.get()), ml), daemon=True).start()

    def _thread(self, samples, passes, ml):
        nn = self.app.nn_store['text']
        for i, text in enumerate(samples):
            if not self._running:
                self.after(0, self._log_msg, "Stopped."); break
            x = text_to_vec(text, ml)
            for _ in range(passes):
                nn.forward(x); nn.train(x, self.app.cfg_learning_rate)
            out = nn.forward(x); mse = float(np.mean((out - x)**2))
            self.after(0, self._log_msg, f"[{i+1}/{len(samples)}] MSE={mse:.5f}")
            self.after(0, lambda v=i+1: self._upbar(v))
        self.after(0, self._done)

    def _upbar(self, v):
        self.pbar['value'] = v
        self.pv.set(f"{v}/{int(self.pbar['maximum'])} samples")

    def _done(self):
        self._running = False
        self.sb.config(state=tk.NORMAL); self.xb.config(state=tk.DISABLED)
        self._log_msg("Training complete.")

    def _stop(self):  self._running = False
    def _close(self): self._running = False; self.destroy()

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_rootx() + (p.winfo_width()  - self.winfo_width())  // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")


# ─────────────────────────────────────────────────────────────
#  Brain Setup Dialog  (with Genetics tab)
# ─────────────────────────────────────────────────────────────
class BrainSetupDialog(tk.Toplevel):
    PRESETS = {"Minimal":("32","0.005","8"),"Compact":("24","0.1","16"),
               "Standard":("128","0.1","32"),"Deep":("256","0.05","64"),"Custom":(None,None,None)}
    IMG = {"8x8":8,"16x16":16,"32x32":32}
    OUT = {"32x32":32,"64x64":64,"128x128":128,"256x256":256}

    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self.title("Brain Setup"); self.configure(bg=BG)
        self.resizable(False, False); self.grab_set(); self.focus_set()
        self.hv  = tk.IntVar(value=app.cfg_hidden_size)
        self.lrv = tk.DoubleVar(value=app.cfg_learning_rate)
        self.wiv = tk.DoubleVar(value=app.cfg_weight_init)
        self.tlv = tk.IntVar(value=app.cfg_text_len)
        self.isv = tk.StringVar(value=app.cfg_img_lbl)
        self.osv = tk.StringVar(value=app.cfg_out_lbl)
        self.pv  = tk.StringVar(value="Custom")
        self._build(); self._center()

    def _build(self):
        tk.Label(self, text="  Brain Setup", bg=BG2, fg=FG,
                 font=("Courier",13,"bold"), anchor='w', padx=12,
                 pady=10).pack(fill='x')

        nb = ttk.Notebook(self); nb.pack(fill='both', expand=True, padx=6, pady=4)

        # ── Tab 1: Architecture ──────────────────────────────
        arch = tk.Frame(nb, bg=BG); nb.add(arch, text="  Architecture  ")
        P = dict(padx=10, pady=4)
        tk.Label(arch,text="PRESETS",bg=BG,fg=FG2,font=("Courier",9,"bold"),
                 anchor='w').grid(row=0,column=0,columnspan=2,sticky='w',padx=10,pady=(8,0))
        om = tk.OptionMenu(arch, self.pv, *self.PRESETS, command=self._pre)
        om.config(bg=BG3,fg=FG,activebackground=BG4,activeforeground=FG,relief='flat')
        om['menu'].config(bg=BG3,fg=FG)
        om.grid(row=1,column=0,columnspan=2,sticky='ew',**P)
        ttk.Separator(arch,orient='horizontal').grid(row=2,column=0,columnspan=2,sticky='ew',pady=6)
        tk.Label(arch,text="ARCHITECTURE",bg=BG,fg=FG2,font=("Courier",9,"bold"),
                 anchor='w').grid(row=3,column=0,columnspan=2,sticky='w',padx=10)
        self._row(arch,"Hidden neurons",4, DSpin(arch,self.hv,4,1024,command=self._cus))
        self._row(arch,"Text length",   5, DSpin(arch,self.tlv,8,128,inc=8,command=self._cus))
        def mk_menu(var, opts, parent=arch):
            om2=tk.OptionMenu(parent,var,*opts,command=lambda _:self._cus())
            om2.config(bg=BG3,fg=FG,activebackground=BG4,activeforeground=FG,relief='flat')
            om2['menu'].config(bg=BG3,fg=FG); return om2
        self._row(arch,"Input image",  6, mk_menu(self.isv, self.IMG))
        self._row(arch,"Output image", 7, mk_menu(self.osv, self.OUT))
        ttk.Separator(arch,orient='horizontal').grid(row=8,column=0,columnspan=2,sticky='ew',pady=6)
        tk.Label(arch,text="TRAINING",bg=BG,fg=FG2,font=("Courier",9,"bold"),
                 anchor='w').grid(row=9,column=0,columnspan=2,sticky='w',padx=10)
        lf = Frm(arch)
        DScale(lf,self.lrv,0.001,0.5,length=150,command=lambda _:self._cus()).pack(side=tk.LEFT)
        self.lrl=tk.Label(lf,width=6,bg=BG,fg=FG,font=("Courier",10)); self.lrl.pack(side=tk.LEFT,padx=2)
        self.lrv.trace_add("write",lambda *_:self._upd(self.lrl,self.lrv)); self._upd(self.lrl,self.lrv)
        self._row(arch,"Learning rate",10,lf)
        wf = Frm(arch)
        DScale(wf,self.wiv,0.001,0.5,length=150,command=lambda _:self._cus()).pack(side=tk.LEFT)
        self.wil=tk.Label(wf,width=6,bg=BG,fg=FG,font=("Courier",10)); self.wil.pack(side=tk.LEFT,padx=2)
        self.wiv.trace_add("write",lambda *_:self._upd(self.wil,self.wiv)); self._upd(self.wil,self.wiv)
        self._row(arch,"Weight init",11,wf)
        self.sv = tk.StringVar()
        tk.Label(arch,textvariable=self.sv,bg=BG,fg=FG2,font=("Courier",9),
                 justify='left').grid(row=12,column=0,columnspan=2,padx=10,pady=4,sticky='w')
        for v in (self.hv,self.tlv,self.isv): v.trace_add("write",lambda *_:self._sum())
        self._sum(); arch.columnconfigure(1,weight=1)

        # ── Tab 2: Genetics ──────────────────────────────────
        gen = tk.Frame(nb, bg=BG); nb.add(gen, text="   Genetics  ")
        tk.Label(gen, text="Innate temperament — sets the brain's baseline personality.",
                 bg=BG, fg=FG2, font=("Courier",8,"italic"),
                 anchor='w').pack(fill='x', padx=10, pady=(8,4))

        g = self.app.genetics
        self._gen_emo_vars  = {}
        self._gen_inst_vars = {}

        emo_frm = LFrm(gen, "Emotional Susceptibility  (0.2 = resistant · 3.0 = highly reactive)",
                        padx=8, pady=4); emo_frm.pack(fill='x', padx=8, pady=4)
        for name in GeneticsProfile.EMO_NAMES:
            self._gen_slider(emo_frm, name, g.emo_susceptibility,
                             self._gen_emo_vars, EmotionState.BAR_COLORS.get(name, ACN))

        inst_frm = LFrm(gen, "Instinct Vulnerability  (0.2 = resilient · 3.0 = fragile)",
                         padx=8, pady=4); inst_frm.pack(fill='x', padx=8, pady=4)
        for name in GeneticsProfile.INST_NAMES:
            self._gen_slider(inst_frm, name, g.inst_vulnerability,
                             self._gen_inst_vars, InstinctSystem.BAR_COLORS.get(name, YEL))

        pf = Frm(gen, bg=BG); pf.pack(fill='x', padx=10, pady=4)
        tk.Label(pf, text="Plasticity (genetics drift rate):", bg=BG, fg=FG,
                 font=("Courier",9)).pack(side=tk.LEFT)
        self._plas_var = tk.DoubleVar(value=g.plasticity)
        DScale(pf, self._plas_var, 0.0, 1.0, length=130, resolution=0.01,
               command=lambda v: setattr(g, 'plasticity', float(v))).pack(side=tk.LEFT, padx=4)
        self._plas_lbl = tk.Label(pf, text=f"{g.plasticity:.2f}", width=4,
                                   bg=BG, fg=FG2, font=("Courier",8))
        self._plas_lbl.pack(side=tk.LEFT)
        self._plas_var.trace_add("write", lambda *_: self._plas_lbl.config(
            text=f"{self._plas_var.get():.2f}"))

        Btn(gen,"Reset Genetics to Default", cmd=self._reset_genetics,
            color=BG4, font=("Courier",9)).pack(anchor='w', padx=10, pady=4)

        # ── Footer buttons ───────────────────────────────────
        bf = Frm(self, bg=BG2); bf.pack(fill='x', pady=4)
        Btn(bf,"Apply & Reset Brain", cmd=self._apply, color=GRN, fg=BG,
            font=("Courier",11,"bold"), padx=10, pady=6).pack(side=tk.RIGHT, padx=10, pady=8)
        Btn(bf,"Cancel", cmd=self.destroy, color=BG4,
            padx=10, pady=6).pack(side=tk.RIGHT, pady=8)

    def _gen_slider(self, parent, name, store, var_dict, color):
        row = Frm(parent, bg=BG2); row.pack(fill='x', pady=2)
        tk.Label(row, text=name.capitalize(), width=11, anchor='w',
                 bg=BG2, fg=FG, font=("Courier",8)).pack(side=tk.LEFT)
        var = tk.DoubleVar(value=store.get(name, 1.0))
        lbl = tk.Label(row, text=f"{store.get(name,1.0):.2f}", width=4,
                       bg=BG2, fg=color, font=("Courier",8))
        DScale(row, var, 0.2, 3.0, length=130, resolution=0.05,
               bg=BG2).pack(side=tk.LEFT, padx=4)
        lbl.pack(side=tk.LEFT)
        var_dict[name] = (var, lbl, store)
        def sync(n=name, v=var, l=lbl, s=store):
            val = float(v.get()); s[n] = val; l.config(text=f"{val:.2f}")
        var.trace_add("write", lambda *_: sync())

    def _reset_genetics(self):
        g = self.app.genetics
        for name in GeneticsProfile.EMO_NAMES:
            g.emo_susceptibility[name] = 1.0
            var, lbl, _ = self._gen_emo_vars[name]
            var.set(1.0); lbl.config(text="1.00")
        for name in GeneticsProfile.INST_NAMES:
            g.inst_vulnerability[name] = 1.0
            var, lbl, _ = self._gen_inst_vars[name]
            var.set(1.0); lbl.config(text="1.00")
        g.plasticity = 0.1; self._plas_var.set(0.1)

    def _row(self, parent, label, r, w):
        Lbl(parent,label).grid(row=r,column=0,sticky='w',padx=10,pady=2)
        w.grid(row=r,column=1,sticky='w',padx=10,pady=2)

    def _upd(self, l, v, *_):
        try: l.config(text=f"{v.get():.3f}")
        except: pass

    def _sum(self, *_):
        try:
            h=int(self.hv.get()); tl=int(self.tlv.get())
            d=self.IMG.get(self.isv.get(),16); ip=d*d
            self.sv.set(f"Text:{tl}→{h}→{tl}  ({tl*h+h+h*tl+tl:,} params)\n"
                        f"Img :{ip}→{h}→{ip}  ({ip*h+h+h*ip+ip:,} params)")
        except: pass

    def _pre(self, c):
        h,lr,wi = self.PRESETS[c]
        if h: self.hv.set(int(h)); self.lrv.set(float(lr)); self.wiv.set(float(wi))

    def _cus(self, *_): self.pv.set("Custom")

    def _apply(self):
        try:
            h=int(self.hv.get()); lr=float(self.lrv.get()); wi=float(self.wiv.get())
            tl=int(self.tlv.get()); d=self.IMG[self.isv.get()]; od=self.OUT[self.osv.get()]
        except Exception as e:
            messagebox.showerror("Error",str(e),parent=self); return
        if h < 4:
            messagebox.showerror("Error","Hidden neurons ≥ 4",parent=self); return
        if any(v for v in self.app.nn_store.values()):
            if not messagebox.askyesno("Reset?","Erase current brains and reset?",parent=self): return
        self.app.cfg_hidden_size=h; self.app.cfg_learning_rate=lr; self.app.cfg_weight_init=wi
        self.app.cfg_text_len=tl; self.app.cfg_img_lbl=self.isv.get()
        self.app.cfg_img_dim=d; self.app.cfg_out_lbl=self.osv.get(); self.app.cfg_out_dim=od
        self.app.nn_store={'text':None,'image':None}; self.app._upd_badge()
        self.destroy()
        messagebox.showinfo("Applied",f"h={h}  lr={lr}  wi={wi}\ntext={tl}  in={d}x{d}  out={od}x{od}")

    def _center(self):
        self.update_idletasks()
        pw,py = self.master.winfo_rootx(), self.master.winfo_rooty()
        pw2,py2 = self.master.winfo_width(), self.master.winfo_height()
        w,h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw+(pw2-w)//2}+{py+(py2-h)//2}")




# ─────────────────────────────────────────────────────────────
#  Tag Manager
# ─────────────────────────────────────────────────────────────
class TagManagerDialog(tk.Toplevel):
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self.configure(bg=BG)
        self.title("Image Tags"); self.resizable(False,False); self.grab_set(); self.focus_set()
        self._refs={}; self._build(); self._refresh(); self._center(parent)

    def _build(self):
        tk.Label(self,text="  Image Tag Associations",bg=BG2,fg=FG,
                 font=("Courier",13,"bold"),anchor='w',padx=12,pady=10).pack(fill='x')
        af=LFrm(self,"Attach tag to image",padx=8,pady=6); af.pack(fill='x',padx=10,pady=6)
        r1=Frm(af,bg=BG2); r1.pack(fill='x',pady=2)
        Lbl(r1,"Tag keyword:",bg=BG2,width=14).pack(side=tk.LEFT)
        self.ntv=tk.StringVar(); DEntry(r1,textvariable=self.ntv,width=24).pack(side=tk.LEFT,padx=4)
        r2=Frm(af,bg=BG2); r2.pack(fill='x',pady=2)
        Lbl(r2,"Image file:",bg=BG2,width=14).pack(side=tk.LEFT)
        self.niv=tk.StringVar()
        tk.Label(r2,textvariable=self.niv,bg=BG3,fg=FG,width=24,anchor='w',
                 font=("Courier",9)).pack(side=tk.LEFT,padx=4)
        Btn(r2,"Browse...",cmd=self._browse).pack(side=tk.LEFT)
        self.thumb=tk.Label(af,text="(none)",bg=BG3,fg=FG2,width=8,height=4)
        self.thumb.pack(pady=4)
        tk.Label(af, text="One tag per image. Multiple images can share a tag.\n"
                          "Tags connect text and image in joint training.",
                 bg=BG2, fg=FG2, font=("Courier",8), justify='left').pack()
        Btn(af,"Add Tag",cmd=self._add,color=GRN,fg=BG,
            font=("Courier",10,"bold"),padx=8).pack(pady=4)
        lf=LFrm(self,"Existing tags",padx=8,pady=6)
        lf.pack(fill='both',expand=True,padx=10,pady=(0,10))
        self.tree=ttk.Treeview(lf,columns=("Tag","Image"),show='headings',height=5)
        self.tree.heading("Tag",text="Tag"); self.tree.column("Tag",width=100,anchor='w')
        self.tree.heading("Image",text="Image"); self.tree.column("Image",width=280,anchor='w')
        vsb=ttk.Scrollbar(lf,orient='vertical',command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT,fill='both',expand=True); vsb.pack(side=tk.LEFT,fill='y')
        Btn(lf,"Remove selected",cmd=self._remove,color=RED,fg=BG,
            font=("Courier",10),padx=6).pack(pady=6)

    def _browse(self):
        p=filedialog.askopenfilename(filetypes=[("Image","*.png *.jpg *.jpeg *.bmp *.gif")])
        if p:
            self.niv.set(p); ex=self.app.image_tags.get(p,"")
            if ex: self.ntv.set(ex)
            try:
                img=Image.open(p).convert('RGB'); img.thumbnail((80,80))
                ph=ImageTk.PhotoImage(img); self._refs['a']=ph; self.thumb.config(image=ph,text="")
            except: pass

    def _add(self):
        tag=self.ntv.get().strip(); path=self.niv.get().strip()
        if not tag or not path or not os.path.exists(path):
            messagebox.showwarning("Missing","Enter tag and select a valid image.",parent=self); return
        old=self.app.image_tags.get(path)
        if old and old in self.app.tag_registry:
            try: self.app.tag_registry[old].remove(path)
            except: pass
            if not self.app.tag_registry[old]: del self.app.tag_registry[old]
        self.app.image_tags[path]=tag
        self.app.tag_registry.setdefault(tag,[])
        if path not in self.app.tag_registry[tag]: self.app.tag_registry[tag].append(path)
        self.ntv.set(""); self.niv.set(""); self.thumb.config(image='',text="(none)"); self._refresh()

    def _remove(self):
        for item in self.tree.selection():
            tag,path=self.tree.item(item,'values')
            if tag in self.app.tag_registry:
                try: self.app.tag_registry[tag].remove(path)
                except: pass
                if not self.app.tag_registry[tag]: del self.app.tag_registry[tag]
            self.app.image_tags.pop(path,None)
        self._refresh()

    def _refresh(self):
        for r in self.tree.get_children(): self.tree.delete(r)
        for tag,paths in sorted(self.app.tag_registry.items()):
            for p in paths: self.tree.insert('','end',values=(tag,p))

    def _center(self,p):
        self.update_idletasks()
        x=p.winfo_rootx()+(p.winfo_width()-self.winfo_width())//2
        y=p.winfo_rooty()+(p.winfo_height()-self.winfo_height())//2
        self.geometry(f"+{x}+{y}")


# ─────────────────────────────────────────────────────────────
#  Export Dialog  (Brain / Soul / Creature)
# ─────────────────────────────────────────────────────────────
class ExportDialog(tk.Toplevel):
    MODES = [
        ("brain",   "Brain only",         "Save the neural network weights only (.brain.npz)"),
        ("soul",    "Soul only",           "Save the soul neuron weights only (.soul.npz)"),
        ("creature","Creature (combined)", "Save Brain + Soul together in one file (.creature.npz)"),
    ]

    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self.title("Export"); self.configure(bg=BG)
        self.resizable(False, False); self.grab_set(); self.focus_set()
        self._build(); self._center(parent)

    def _build(self):
        tk.Label(self, text="  Export", bg=BG2, fg=FG,
                 font=("Courier",13,"bold"), anchor='w',
                 padx=12, pady=10).pack(fill='x')
        bd = Frm(self, padx=14, pady=10); bd.pack(fill='both')
        self.mode = tk.StringVar(value="brain")
        for val, lbl, desc in self.MODES:
            row = Frm(bd, bg=BG2); row.pack(fill='x', pady=3)
            tk.Radiobutton(row, text=lbl, variable=self.mode, value=val,
                           bg=BG2, fg=FG, selectcolor=BG3,
                           font=("Courier",10,"bold")).pack(anchor='w')
            tk.Label(row, text=f"  {desc}", bg=BG2, fg=FG2,
                     font=("Courier",8), anchor='w').pack(fill='x', padx=12)
        Sep(bd).pack(fill='x', pady=8)

        # Name row
        nr = Frm(bd); nr.pack(fill='x', pady=4)
        tk.Label(nr, text="Brain name:", bg=BG, fg=FG2,
                 font=("Courier",9)).pack(side=tk.LEFT, padx=(0,4))
        self._bn = DEntry(nr, textvariable=self.app.brain_name, width=16)
        self._bn.pack(side=tk.LEFT, padx=(0,10))
        tk.Label(nr, text="Soul name:", bg=BG, fg=FG2,
                 font=("Courier",9)).pack(side=tk.LEFT, padx=(0,4))
        self._sn = DEntry(nr, textvariable=self.app.soul_name, width=16)
        self._sn.pack(side=tk.LEFT)

        bf = Frm(bd); bf.pack(pady=6)
        Btn(bf, "Export...", cmd=self._export, color=GRN, fg=BG,
            font=("Courier",11,"bold"), padx=12).pack(side=tk.LEFT, padx=6)
        Btn(bf, "Cancel",  cmd=self.destroy,
            font=("Courier",11), padx=12).pack(side=tk.LEFT, padx=6)

    def _export(self):
        m = self.mode.get()
        bn = self.app.brain_name.get().strip() or "Brain"
        sn = self.app.soul_name.get().strip()  or "Soul"

        if m == "brain":
            nn = self.app.nn_store.get(self.app._last_itype)
            if not nn:
                messagebox.showwarning("No brain","Run the network first.",parent=self); return
            fp = filedialog.asksaveasfilename(
                defaultextension=".npz",
                initialfile=f"{bn}.brain",
                filetypes=[("Brain file","*.npz"),("All","*.*")], parent=self)
            if not fp: return
            nn.save(fp, name=bn)
            messagebox.showinfo("Exported", f"Brain '{bn}' saved.", parent=self)

        elif m == "soul":
            fp = filedialog.asksaveasfilename(
                defaultextension=".npz",
                initialfile=f"{sn}.soul",
                filetypes=[("Soul file","*.npz"),("All","*.*")], parent=self)
            if not fp: return
            self.app.soul.save(fp, name=sn)
            messagebox.showinfo("Exported", f"Soul '{sn}' saved.", parent=self)

        elif m == "creature":
            nn = self.app.nn_store.get(self.app._last_itype)
            if not nn:
                messagebox.showwarning("No brain","Run the network first.",parent=self); return
            fp = filedialog.asksaveasfilename(
                defaultextension=".npz",
                initialfile=f"{bn}+{sn}.creature",
                filetypes=[("Creature file","*.npz"),("All","*.*")], parent=self)
            if not fp: return
            soul = self.app.soul
            np.savez(fp,
                     # Brain arrays
                     B_W1=nn.W1, B_b1=nn.b1, B_W2=nn.W2, B_b2=nn.b2,
                     B_input_size=nn.input_size, B_hidden_size=nn.hidden_size,
                     B_output_size=nn.output_size, B_weight_init=nn.weight_init,
                     B_name=np.array(bn),
                     # Soul arrays
                     S_W1=soul.W1, S_b1=soul.b1, S_W2=soul.W2, S_b2=soul.b2,
                     S_hidden=soul.hidden, S_experience=soul.experience,
                     S_name=np.array(sn),
                     # Marker
                     creature_marker=np.array(True))
            messagebox.showinfo("Exported",
                                f"Creature '{bn} + {sn}' saved.", parent=self)
        self.destroy()

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_rootx() + (p.winfo_width()  - self.winfo_width())  // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")


# ─────────────────────────────────────────────────────────────
#  Import Dialog  (Brain / Soul / Creature)
# ─────────────────────────────────────────────────────────────
class ImportDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self.title("Import"); self.configure(bg=BG)
        self.resizable(False, False); self.grab_set(); self.focus_set()
        self._build(); self._center(parent)

    def _build(self):
        tk.Label(self, text="  Import", bg=BG2, fg=FG,
                 font=("Courier",13,"bold"), anchor='w',
                 padx=12, pady=10).pack(fill='x')
        bd = Frm(self, padx=14, pady=10); bd.pack(fill='both')
        self.mode = tk.StringVar(value="auto")
        modes = [
            ("auto",    "Auto-detect",         "Inspect file and load whatever is inside"),
            ("brain",   "Brain only",           "Load brain weights from a .brain.npz or .npz"),
            ("soul",    "Soul only",            "Load soul weights from a .soul.npz or .npz"),
            ("creature","Creature (combined)",  "Load both Brain + Soul from a .creature.npz"),
        ]
        for val, lbl, desc in modes:
            row = Frm(bd, bg=BG2); row.pack(fill='x', pady=3)
            tk.Radiobutton(row, text=lbl, variable=self.mode, value=val,
                           bg=BG2, fg=FG, selectcolor=BG3,
                           font=("Courier",10,"bold")).pack(anchor='w')
            tk.Label(row, text=f"  {desc}", bg=BG2, fg=FG2,
                     font=("Courier",8), anchor='w').pack(fill='x', padx=12)
        Sep(bd).pack(fill='x', pady=8)
        self.status_var = tk.StringVar(value="No file selected")
        tk.Label(bd, textvariable=self.status_var, bg=BG, fg=FG2,
                 font=("Courier",8), anchor='w').pack(fill='x', pady=2)
        bf = Frm(bd); bf.pack(pady=6)
        Btn(bf, "Browse & Import...", cmd=self._do_import, color=ACN, fg=BG,
            font=("Courier",11,"bold"), padx=12).pack(side=tk.LEFT, padx=6)
        Btn(bf, "Cancel", cmd=self.destroy,
            font=("Courier",11), padx=12).pack(side=tk.LEFT, padx=6)

    def _do_import(self):
        fp = filedialog.askopenfilename(
            filetypes=[("All supported","*.npz"),("All","*.*")],
            parent=self)
        if not fp: return
        try:
            d    = np.load(fp, allow_pickle=True)
            keys = list(d.keys())
            m    = self.mode.get()

            # Auto-detect
            if m == "auto":
                if 'creature_marker' in keys:  m = "creature"
                elif 'soul_marker'   in keys:  m = "soul"
                elif 'B_W1'          in keys:  m = "creature"
                elif 'hidden'        in keys:  m = "soul"
                else:                          m = "brain"

            if m == "brain":
                nn = SimpleNN(1,1,1); nn.load(fp)
                itype = 'image' if nn.input_size > 128 else 'text'
                self.app.nn_store[itype] = nn
                self.app._last_itype = itype
                self.app.cfg_hidden_size = nn.hidden_size
                if itype == 'text': self.app.cfg_text_len = nn.input_size
                else:
                    import math; d2 = int(math.sqrt(nn.input_size))
                    self.app.cfg_img_dim = d2
                    self.app.cfg_img_lbl = {8:"8x8",16:"16x16",32:"32x32"}.get(d2,"16x16")
                loaded_name = str(d['name'][()]) if 'name' in d else "Brain"
                self.app.brain_name.set(loaded_name)
                self.app.itype.set(itype); self.app.on_itype_change(); self.app._upd_badge()
                self.status_var.set(f"Brain '{loaded_name}' loaded.")

            elif m == "soul":
                self.app.soul.load(fp)
                loaded_name = str(d['name'][()]) if 'name' in d else "Soul"
                self.app.soul_name.set(loaded_name)
                self.status_var.set(f"Soul '{loaded_name}' loaded.")

            elif m == "creature":
                if 'B_W1' not in keys:
                    messagebox.showerror("Error","Not a creature file.",parent=self); return
                # Load brain
                nn = SimpleNN(1,1,1)
                nn.W1 = d['B_W1']; nn.b1 = d['B_b1']
                nn.W2 = d['B_W2']; nn.b2 = d['B_b2']
                nn.input_size  = int(d['B_input_size'])
                nn.hidden_size = int(d['B_hidden_size'])
                nn.output_size = int(d['B_output_size'])
                nn.weight_init = float(d['B_weight_init'])
                nn.a1 = np.zeros((1, nn.hidden_size))
                nn.a2 = np.zeros((1, nn.output_size))
                itype = 'image' if nn.input_size > 128 else 'text'
                self.app.nn_store[itype] = nn
                self.app._last_itype = itype
                self.app.cfg_hidden_size = nn.hidden_size
                if itype == 'text': self.app.cfg_text_len = nn.input_size
                bn = str(d['B_name'][()]) if 'B_name' in d else "Brain"
                self.app.brain_name.set(bn)
                # Load soul
                soul = self.app.soul
                soul.W1 = d['S_W1']; soul.b1 = d['S_b1']
                soul.W2 = d['S_W2']; soul.b2 = d['S_b2']
                soul.hidden     = int(d['S_hidden'])
                soul.experience = float(d['S_experience'])
                soul.a1 = np.zeros((1, soul.hidden))
                soul.a2 = np.zeros((1, 10))
                sn = str(d['S_name'][()]) if 'S_name' in d else "Soul"
                self.app.soul_name.set(sn)
                self.app.itype.set(itype); self.app.on_itype_change(); self.app._upd_badge()
                self.status_var.set(f"Creature '{bn} + {sn}' loaded.")

            messagebox.showinfo("Imported", self.status_var.get(), parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Import error", str(e), parent=self)

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_rootx() + (p.winfo_width()  - self.winfo_width())  // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")


# ─────────────────────────────────────────────────────────────
#  Detachable Face Window
# ─────────────────────────────────────────────────────────────
class DetachedFaceWindow(tk.Toplevel):
    """Floating face window that stays live-synced with the main app."""
    def __init__(self, app):
        super().__init__(app.root)
        self._app  = app
        self._ph   = None
        self.title("Neuron Face")
        self.configure(bg=BG2)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        tk.Label(self, text="FACE", bg=BG2, fg=ACN,
                 font=("Courier",10,"bold")).pack(pady=(8,0))
        self.face_lbl = tk.Label(self, bg=BG2)
        self.face_lbl.pack(padx=16, pady=6)
        self.status_lbl = tk.Label(self, text="—", bg=BG2, fg=FG2,
                                    font=("Courier",7), anchor='center')
        self.status_lbl.pack(pady=(0,4))
        Btn(self, "Dock Back", cmd=self._on_close, color=BG4,
            font=("Courier",9)).pack(pady=(0,10))
        self._update()

    def _update(self):
        try:
            app = self._app
            nn  = app.nn_store.get(app._last_itype)
            img = make_face(nn, app.soul, app.emotions,
                            app.instincts, app.relational, size=160)
            ph  = ImageTk.PhotoImage(img); self.face_lbl.config(image=ph); self._ph = ph
            wb  = int(app.instincts.wellbeing() * 100)
            dom = app.soul.dominant_memory_emotion() if app.soul._memory else "—"
            att = app.relational.attachment; res = app.relational.resentment
            self.status_lbl.config(
                text=f"Wellbeing {wb}%  |  Memory: {dom}  |  Att:{att:.2f}  Res:{res:.2f}")
        except Exception:
            pass
        ms = max(1000, int(float(self._app.face_interval.get()) * 1000))
        self.after(ms, self._update)

    def _on_close(self):
        self._app._face_window = None
        self.destroy()


# ─────────────────────────────────────────────────────────────
#  Organic Neuron Firing Panel
# ─────────────────────────────────────────────────────────────
class RelationalStatusPanel(tk.LabelFrame):
    def __init__(self, parent, relational):
        super().__init__(parent, text=" Relational State",
                         bg=BG2, fg=FG, font=("Courier",10,"bold"), padx=6, pady=4)
        self.rel = relational
        s = ttk.Style()
        s.configure('att.Horizontal.TProgressbar', troughcolor=BG3, background='#94e2d5')
        s.configure('res.Horizontal.TProgressbar', troughcolor=BG3, background='#f38ba8')

        tk.Label(self, text="These hidden metrics silently shape learning behavior.",
                 bg=BG2, fg=FG2, font=("Courier",7,"italic"), anchor='w').pack(fill='x', padx=2)

        ar = Frm(self, bg=BG2); ar.pack(fill='x', pady=2)
        tk.Label(ar,text="Attachment",width=11,anchor='w',bg=BG2,fg='#94e2d5',
                 font=("Courier",9)).pack(side='left')
        self._att_bar = ttk.Progressbar(ar,orient='horizontal',length=160,
                                         mode='determinate',maximum=100,
                                         style='att.Horizontal.TProgressbar')
        self._att_bar.pack(side='left',padx=4)
        self._att_lbl = tk.Label(ar,text="0.30",width=4,bg=BG2,fg='#94e2d5',font=("Courier",8))
        self._att_lbl.pack(side='left')

        rr = Frm(self, bg=BG2); rr.pack(fill='x', pady=2)
        tk.Label(rr,text="Resentment",width=11,anchor='w',bg=BG2,fg='#f38ba8',
                 font=("Courier",9)).pack(side='left')
        self._res_bar = ttk.Progressbar(rr,orient='horizontal',length=160,
                                         mode='determinate',maximum=100,
                                         style='res.Horizontal.TProgressbar')
        self._res_bar.pack(side='left',padx=4)
        self._res_lbl = tk.Label(rr,text="0.05",width=4,bg=BG2,fg='#f38ba8',font=("Courier",8))
        self._res_lbl.pack(side='left')

        self._narr_var = tk.StringVar(value="")
        tk.Label(self,textvariable=self._narr_var,bg=BG2,fg=FG2,
                 font=("Courier",8,"italic"),anchor='w').pack(fill='x',padx=4,pady=(2,0))

    def refresh(self):
        a, r = self.rel.attachment, self.rel.resentment
        self._att_bar['value'] = a * 100; self._att_lbl.config(text=f"{a:.2f}")
        self._res_bar['value'] = r * 100; self._res_lbl.config(text=f"{r:.2f}")
        if r > 0.6:   msg = "Acting out — strong resentment."
        elif r > 0.4: msg = "Friction in learning, pushing back."
        elif a > 0.7: msg = "Strongly bonded — very responsive."
        elif a > 0.5: msg = "Comfortable — learning well."
        else:         msg = "Neutral relational state."
        self._narr_var.set(msg)




# ─────────────────────────────────────────────────────────────
#  Breeding Dialog — combine two .creature.npz files
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
#  Creature-to-Creature Interaction System
# ─────────────────────────────────────────────────────────────
class CreatureState:
    """Lightweight container for a loaded creature's state during interaction."""
    def __init__(self, name, nn_text, nn_image, soul, emotions, instincts, genetics, relational):
        self.name      = name
        self.nn_text   = nn_text
        self.nn_image  = nn_image
        self.soul      = soul
        self.emotions  = emotions
        self.instincts = instincts
        self.genetics  = genetics
        self.relational = relational
        # Mutual relationship metrics
        self.bond      = 0.3   # 0=strangers, 1=close
        self.rivalry   = 0.0   # 0=none, 1=intense conflict
        self.face_img  = None  # cached PIL image for display
        self._face_ref = None  # PhotoImage reference

    @classmethod
    def load(cls, fp):
        """Load a creature from .creature.npz or .brain.npz file."""
        d    = np.load(fp, allow_pickle=True)
        name = str(d.get('name', np.array(os.path.basename(fp).split('.')[0])))

        def _load_nn(prefix):
            k = prefix + '_W1'
            if k not in d: return None
            in_s  = int(d[prefix+'_in'])  if prefix+'_in'  in d else int(d.get('input_size',  np.array(32)))
            hid_s = int(d[prefix+'_hid']) if prefix+'_hid' in d else int(d.get('hidden_size', np.array(64)))
            out_s = int(d[prefix+'_out']) if prefix+'_out' in d else int(d.get('output_size', np.array(32)))
            nn = SimpleNN(in_s, hid_s, out_s)
            nn.W1 = d[prefix+'_W1']; nn.b1 = d[prefix+'_b1']
            nn.W2 = d[prefix+'_W2']; nn.b2 = d[prefix+'_b2']
            nn._init_momentum()
            return nn

        # Try creature format (B_/S_ prefix) then plain format
        nn_text  = _load_nn('B') or _load_nn('text')
        nn_image = _load_nn('BI') if 'BI_W1' in d else None

        soul = SoulNN()
        if 'S_W1' in d:
            soul.W1 = d['S_W1']; soul.b1 = d['S_b1']
            soul.W2 = d['S_W2']; soul.b2 = d['S_b2']
            soul.experience = float(d.get('S_experience', np.array(0.0)))
        elif 'soul_marker' in d:
            soul.W1 = d['W1']; soul.b1 = d['b1']
            soul.W2 = d['W2']; soul.b2 = d['b2']
            soul.experience = float(d.get('experience', np.array(0.0)))
        if 'soul_mem_vecs' in d:
            vecs   = d['soul_mem_vecs']
            labels = d['soul_mem_labels'] if 'soul_mem_labels' in d else ['neutral']*len(vecs)
            soul._memory = [(vecs[i], str(labels[i])) for i in range(len(vecs))]
        soul.name = str(d.get('S_name', d.get('name', np.array(name))))

        em  = EmotionState()
        ins = InstinctSystem()
        gen = GeneticsProfile()
        rel = RelationalState()
        if 'genetics_emo' in d:
            g = d['genetics_emo'].flatten()
            for i,nm in enumerate(EmotionState.NAMES[:len(g)]):
                gen.emo_susceptibility[nm] = float(g[i])
        return cls(name, nn_text, nn_image, soul, em, ins, gen, rel)


class CreatureInteractionDialog(tk.Toplevel):
    """Interactive chamber where two loaded creatures communicate and form relationships."""
    EXCHANGE_INTERVAL = 4000   # ms between auto-exchanges

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app   = app
        self.title(" Creature Interaction Chamber")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.geometry("1100x780")

        self._ca: CreatureState = None
        self._cb: CreatureState = None
        self._running  = False
        self._exchange_count = 0
        self._pending_reward = None  # which creature's action is pending user eval

        self._build()
        self._center(parent)

    def _build(self):
        # ── Top: load creatures ───────────────────────────────
        top = Frm(self, bg=BG2); top.pack(fill='x', pady=0)
        tk.Label(top, text="   Creature Interaction Chamber", bg=BG2, fg='#f38ba8',
                 font=("Courier",13,"bold"), pady=8, padx=10).pack(side=tk.LEFT)

        for side, label, cmd in [('left','Load Creature A', self._load_a),
                                  ('left','Load Creature B', self._load_b)]:
            Btn(top, label, cmd=cmd, color=BG4, font=("Courier",9)).pack(
                side=tk.LEFT, padx=4, pady=6)

        self._status_var = tk.StringVar(value="Load both creatures to begin.")
        tk.Label(top, textvariable=self._status_var, bg=BG2, fg=FG2,
                 font=("Courier",8,"italic"), padx=10).pack(side=tk.LEFT)

        # ── Main area: two faces + log in the middle ──────────
        main = Frm(self); main.pack(fill='both', expand=True, padx=6, pady=4)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        # Creature A panel (left)
        self._ca_frm = self._creature_panel(main, 'A')
        self._ca_frm.grid(row=0, column=0, sticky='nsew', padx=(0,4))

        # Centre log
        centre = Frm(main); centre.grid(row=0, column=1, sticky='nsew')
        centre.rowconfigure(1, weight=1)
        centre.columnconfigure(0, weight=1)

        tk.Label(centre, text="Interaction Log", bg=BG, fg=ACN,
                 font=("Courier",10,"bold")).grid(row=0,column=0,sticky='w',pady=(0,2))
        self._log = tk.Text(centre, bg='#05050f', fg=FG2, font=("Courier",8),
                            state=tk.DISABLED, wrap=tk.WORD)
        self._log.grid(row=1, column=0, sticky='nsew')
        sb = tk.Scrollbar(centre, command=self._log.yview, bg=BG3)
        sb.grid(row=1, column=1, sticky='ns')
        self._log.config(yscrollcommand=sb.set)

        # Bond/Rivalry meters
        metrics = Frm(centre, bg=BG); metrics.grid(row=2, column=0, columnspan=2,
                                                     sticky='ew', pady=(4,0))
        tk.Label(metrics, text="Bond:", bg=BG, fg=GRN, font=("Courier",8)).pack(side=tk.LEFT)
        self._bond_var = tk.DoubleVar(value=0.3)
        self._bond_bar = ttk.Progressbar(metrics, variable=self._bond_var,
                                          maximum=1.0, length=120)
        self._bond_bar.pack(side=tk.LEFT, padx=4)
        tk.Label(metrics, text="Rivalry:", bg=BG, fg=RED, font=("Courier",8)).pack(side=tk.LEFT, padx=(10,0))
        self._riv_var = tk.DoubleVar(value=0.0)
        self._riv_bar = ttk.Progressbar(metrics, variable=self._riv_var,
                                         maximum=1.0, length=120)
        self._riv_bar.pack(side=tk.LEFT, padx=4)

        # Creature B panel (right)
        self._cb_frm = self._creature_panel(main, 'B')
        self._cb_frm.grid(row=0, column=2, sticky='nsew', padx=(4,0))

        # ── Bottom controls ────────────────────────────────────
        ctrl = Frm(self, bg=BG3); ctrl.pack(fill='x', side=tk.BOTTOM)

        # Row 1: playback controls + prompt
        row1 = Frm(ctrl, bg=BG3); row1.pack(fill='x', pady=(4,0))
        self._start_btn = Btn(row1,"Start Auto-Exchange", cmd=self._start,
                               color=GRN, fg=BG, font=("Courier",9,"bold"))
        self._start_btn.pack(side=tk.LEFT, padx=6, pady=4)
        self._stop_btn = Btn(row1,"Stop", cmd=self._stop,
                              color=BG4, font=("Courier",9))
        self._stop_btn.pack(side=tk.LEFT, padx=4)
        Btn(row1,"Single Exchange", cmd=self._single_exchange,
            color=ACN, fg=BG, font=("Courier",9)).pack(side=tk.LEFT, padx=4)

        tk.Label(row1, text="Prompt:", bg=BG3, fg=FG,
                 font=("Courier",8)).pack(side=tk.LEFT, padx=(12,2))
        self._prompt_var = tk.StringVar()
        tk.Entry(row1, textvariable=self._prompt_var, bg=BG4, fg=FG,
                 font=("Courier",9), width=22, insertbackground=FG).pack(side=tk.LEFT)
        Btn(row1,"Send to Both", cmd=self._send_prompt,
            color=YEL, fg=BG, font=("Courier",8)).pack(side=tk.LEFT, padx=4)

        Btn(row1,"[+] Reward Last", cmd=lambda: self._user_eval(True),
            color=GRN, fg=BG, font=("Courier",8)).pack(side=tk.RIGHT, padx=4)
        Btn(row1,"[-] Punish Last", cmd=lambda: self._user_eval(False),
            color=RED, fg=BG, font=("Courier",8)).pack(side=tk.RIGHT, padx=4)

        # Row 2: save + breed
        row2 = Frm(ctrl, bg=BG3); row2.pack(fill='x', pady=(2,4))
        Btn(row2,"Save Creature A", cmd=self._save_a,
            color=BG4, font=("Courier",9)).pack(side=tk.LEFT, padx=6)
        Btn(row2,"Save Creature B", cmd=self._save_b,
            color=BG4, font=("Courier",9)).pack(side=tk.LEFT, padx=4)
        Btn(row2,"Breed A x B ...", cmd=self._open_breed,
            color='#f38ba8', fg=BG, font=("Courier",9,"bold")).pack(side=tk.LEFT, padx=8)

        # Style tags for log
        self._log.tag_config('A',  foreground=ACN)
        self._log.tag_config('B',  foreground=PRP)
        self._log.tag_config('sys', foreground=FG2, font=("Courier",7,"italic"))
        self._log.tag_config('bond', foreground=GRN)
        self._log.tag_config('riv',  foreground=RED)

    def _creature_panel(self, parent, side):
        """Return a frame with face canvas + emotion bars + name for one creature."""
        frm = LFrm(parent, f"Creature {side}", padx=6, pady=4)
        frm.columnconfigure(0, weight=1)
        # Face canvas
        if side == 'A':
            self._face_a = tk.Canvas(frm, bg=BG3, width=96, height=96,
                                      highlightthickness=1, highlightbackground=BG4)
            self._face_a.grid(row=0, column=0, pady=(0,4))
            self._face_a.create_text(48, 48, text="No\ncreature", fill=FG2,
                                      font=("Courier",7), tags="ph")
            self._name_a = tk.Label(frm, text="—", bg=BG2, fg=ACN,
                                     font=("Courier",9,"bold"))
            self._name_a.grid(row=1, column=0)
            self._emo_a_var = tk.StringVar(value="—")
            tk.Label(frm, textvariable=self._emo_a_var, bg=BG2, fg=FG2,
                     font=("Courier",7), wraplength=140).grid(row=2, column=0)
        else:
            self._face_b = tk.Canvas(frm, bg=BG3, width=96, height=96,
                                      highlightthickness=1, highlightbackground=BG4)
            self._face_b.grid(row=0, column=0, pady=(0,4))
            self._face_b.create_text(48, 48, text="No\ncreature", fill=FG2,
                                      font=("Courier",7), tags="ph")
            self._name_b = tk.Label(frm, text="—", bg=BG2, fg=PRP,
                                     font=("Courier",9,"bold"))
            self._name_b.grid(row=1, column=0)
            self._emo_b_var = tk.StringVar(value="—")
            tk.Label(frm, textvariable=self._emo_b_var, bg=BG2, fg=FG2,
                     font=("Courier",7), wraplength=140).grid(row=2, column=0)
        return frm

    def _load_a(self):
        fp = filedialog.askopenfilename(title="Load Creature A",
            filetypes=[("Creature/Brain","*.creature.npz *.brain.npz *.npz"),("All","*.*")])
        if fp:
            try:
                self._ca = CreatureState.load(fp)
                self._name_a.config(text=self._ca.name)
                self._update_face_canvas(self._ca, self._face_a)
                self._log_msg(f"Creature A '{self._ca.name}' loaded.", 'sys')
                self._check_ready()
            except Exception as e:
                messagebox.showerror("Load Error", str(e))

    def _load_b(self):
        fp = filedialog.askopenfilename(title="Load Creature B",
            filetypes=[("Creature/Brain","*.creature.npz *.brain.npz *.npz"),("All","*.*")])
        if fp:
            try:
                self._cb = CreatureState.load(fp)
                self._name_b.config(text=self._cb.name)
                self._update_face_canvas(self._cb, self._face_b)
                self._log_msg(f"Creature B '{self._cb.name}' loaded.", 'sys')
                self._check_ready()
            except Exception as e:
                messagebox.showerror("Load Error", str(e))

    def _check_ready(self):
        if self._ca and self._cb:
            self._status_var.set(
                f"Ready: {self._ca.name} ↔ {self._cb.name}. Press Start.")

    def _update_face_canvas(self, c: CreatureState, canvas: tk.Canvas):
        try:
            img = make_face(c.nn_text or c.nn_image, c.soul, c.emotions,
                            c.instincts, c.relational, size=96)
            ph  = ImageTk.PhotoImage(img)
            c._face_ref = ph
            canvas.delete("all")
            canvas.create_image(0, 0, anchor='nw', image=ph)
        except Exception:
            pass

    def _update_emo_label(self, c: CreatureState, var: tk.StringVar):
        ev = c.emotions.v
        dominant = max(ev, key=ev.get)
        lines = [f"{dominant.upper()}: {ev[dominant]:.2f}"]
        for nm, val in sorted(ev.items(), key=lambda x: -x[1]):
            if nm != dominant:
                lines.append(f"  {nm[:4]}: {val:.2f}")
        var.set('\n'.join(lines[:4]))

    def _log_msg(self, msg, tag='sys'):
        self._log.config(state=tk.NORMAL)
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        self._log.insert(tk.END, f"[{ts}] {msg}\n", tag)
        self._log.see(tk.END)
        self._log.config(state=tk.DISABLED)

    def _generate_output(self, c: CreatureState, input_vec=None, itype='text') -> tuple:
        """Run creature's network and return (output_vec, readable_string)."""
        nn = c.nn_text if itype == 'text' else (c.nn_image or c.nn_text)
        if nn is None: return None, "(no network)"
        ev = c.emotions.to_vec()
        soul_out = c.soul.forward(ev).flatten()
        if input_vec is not None:
            x = np.clip(input_vec, 0, 1)
        else:
            rand = np.random.rand(1, nn.input_size)
            soul_mod = np.resize(soul_out, nn.input_size).reshape(1, -1)
            x = rand * 0.65 + soul_mod * 0.35
        noise = c.emotions.v.get('curiosity', 0.3) * 0.05 + 0.03
        out = nn.forward(x, noise=noise)
        if itype == 'text':
            txt = vec_to_text(out.flatten(), False)
            return out, txt[:50]
        else:
            return out, "[image]"

    def _exchange(self):
        """One exchange cycle: A outputs → B receives, then B outputs → A receives."""
        if not (self._ca and self._cb): return
        self._exchange_count += 1
        ec = self._exchange_count

        # ── A speaks ──────────────────────────────────────────
        out_a, txt_a = self._generate_output(self._ca, itype='text')
        self._log_msg(f"{self._ca.name}: \"{txt_a}\"", 'A')

        # B receives A's output → train B lightly + update B emotions
        if out_a is not None and self._cb.nn_text is not None:
            b_in  = np.resize(out_a.flatten(), self._cb.nn_text.input_size).reshape(1,-1)
            b_out = self._cb.nn_text.forward(b_in)
            b_mse = float(np.mean((b_out - b_in)**2))
            # Understanding → lower MSE = better bond
            if b_mse < 0.15:
                self._cb.bond = min(1.0, self._ca.bond + 0.03)
                self._ca.bond = min(1.0, self._cb.bond + 0.02)
                self._log_msg(f"  → {self._cb.name} understood (MSE={b_mse:.3f})", 'bond')
            else:
                self._cb.rivalry = min(1.0, self._cb.rivalry + 0.02)
                self._log_msg(f"  → {self._cb.name} confused (MSE={b_mse:.3f})", 'riv')
            # B trains on A's output gently — knowledge sharing
            self._cb.nn_text.train(b_in, lr=0.008)

        # ── Emotional contagion A→B ────────────────────────────
        self._emotional_contagion(self._ca, self._cb, strength=0.06)

        # ── B responds ────────────────────────────────────────
        b_input = np.resize(out_a.flatten(), self._cb.nn_text.input_size).reshape(1,-1) \
                  if (out_a is not None and self._cb.nn_text) else None
        out_b, txt_b = self._generate_output(self._cb, input_vec=b_input, itype='text')
        self._log_msg(f"{self._cb.name}: \"{txt_b}\"", 'B')

        # A receives B's output
        if out_b is not None and self._ca.nn_text is not None:
            a_in  = np.resize(out_b.flatten(), self._ca.nn_text.input_size).reshape(1,-1)
            a_mse = float(np.mean((self._ca.nn_text.forward(a_in) - a_in)**2))
            if a_mse < 0.15:
                self._ca.bond = min(1.0, self._ca.bond + 0.02)
            else:
                self._ca.rivalry = min(1.0, self._ca.rivalry + 0.01)
            self._ca.nn_text.train(a_in, lr=0.006)

        # ── Emotional contagion B→A ────────────────────────────
        self._emotional_contagion(self._cb, self._ca, strength=0.05)

        # ── Soul memory: record interaction ───────────────────
        self._ca.soul.add_memory(self._ca.emotions.to_vec(), 'neutral')
        self._cb.soul.add_memory(self._cb.emotions.to_vec(), 'neutral')

        # ── Influence factor: prolonged exposure tweaks genetics ──
        if ec % 8 == 0:
            self._cross_influence()

        # Store last exchange creature for reward/punish
        self._pending_reward = (self._ca, self._cb)

        # Update UI
        self._update_faces()
        self._update_emo_label(self._ca, self._emo_a_var)
        self._update_emo_label(self._cb, self._emo_b_var)
        avg_bond = (self._ca.bond + self._cb.bond) / 2
        avg_riv  = (self._ca.rivalry + self._cb.rivalry) / 2
        self._bond_var.set(avg_bond)
        self._riv_var.set(avg_riv)
        if ec % 5 == 0:
            self._log_msg(
                f"[Exchange {ec}]  Bond: {avg_bond:.2f}  Rivalry: {avg_riv:.2f}", 'sys')

    def _emotional_contagion(self, source: CreatureState, target: CreatureState, strength=0.05):
        """Emotions subtly transfer between creatures."""
        for nm in EmotionState.NAMES:
            delta = (source.emotions.v[nm] - target.emotions.v[nm]) * strength
            target.emotions.v[nm] = max(0.0, min(1.0, target.emotions.v[nm] + delta))

    def _cross_influence(self):
        """Prolonged interaction gradually influences each creature's genetic expression."""
        for attr in ('play_style',):
            if hasattr(self._ca.soul, attr) and hasattr(self._cb.soul, attr):
                va, vb = getattr(self._ca.soul, attr), getattr(self._cb.soul, attr)
                mid  = (va + vb) / 2
                noise = random.gauss(0, 0.02)
                setattr(self._ca.soul, attr, max(0,min(1, va + (mid-va)*0.05 + noise)))
                setattr(self._cb.soul, attr, max(0,min(1, vb + (mid-vb)*0.05 - noise)))

    def _update_faces(self):
        self._update_face_canvas(self._ca, self._face_a)
        self._update_face_canvas(self._cb, self._face_b)

    def _send_prompt(self):
        prompt = self._prompt_var.get().strip()
        if not prompt or not (self._ca and self._cb): return
        vec = text_to_vec(prompt, 32)
        a_in = np.resize(vec.flatten(), self._ca.nn_text.input_size if self._ca.nn_text else 32)
        b_in = np.resize(vec.flatten(), self._cb.nn_text.input_size if self._cb.nn_text else 32)
        out_a, txt_a = self._generate_output(self._ca, a_in.reshape(1,-1))
        out_b, txt_b = self._generate_output(self._cb, b_in.reshape(1,-1))
        self._log_msg(f"[Prompt] \"{prompt}\"", 'sys')
        self._log_msg(f"{self._ca.name}: \"{txt_a}\"", 'A')
        self._log_msg(f"{self._cb.name}: \"{txt_b}\"", 'B')
        self._update_faces()
        self._prompt_var.set("")

    def _user_eval(self, reward: bool):
        if not self._pending_reward: return
        ca, cb = self._pending_reward
        ev_a, ev_b = ca.emotions.to_vec(), cb.emotions.to_vec()
        if reward:
            ca.soul.reward(ev_a, s=0.12); cb.soul.reward(ev_b, s=0.12)
            ca.bond = min(1.0, ca.bond + 0.05); cb.bond = min(1.0, cb.bond + 0.05)
            self._log_msg("User rewarded this exchange — bond strengthened.", 'bond')
        else:
            ca.soul.punish(ev_a, s=0.08); cb.soul.punish(ev_b, s=0.08)
            ca.rivalry = min(1.0, ca.rivalry + 0.04)
            cb.rivalry = min(1.0, cb.rivalry + 0.04)
            self._log_msg("User punished this exchange — tension increased.", 'riv')
        self._update_faces()

    def _single_exchange(self):
        if not (self._ca and self._cb):
            self._status_var.set("Load both creatures first."); return
        self._exchange()

    def _start(self):
        if not (self._ca and self._cb):
            self._status_var.set("Load both creatures first."); return
        self._running = True
        self._start_btn.config(state=tk.DISABLED)
        self._status_var.set("Auto-exchange running...")
        self._auto_exchange()

    def _auto_exchange(self):
        if not self._running: return
        self._exchange()
        self.after(self.EXCHANGE_INTERVAL, self._auto_exchange)

    def _stop(self):
        self._running = False
        self._start_btn.config(state=tk.NORMAL)
        self._status_var.set("Stopped.")

    def _save_creature(self, c: 'CreatureState', label: str):
        """Save an interacted creature back as a .creature.npz file."""
        if c is None:
            messagebox.showwarning("No Creature", f"Creature {label} is not loaded.")
            return
        fp = filedialog.asksaveasfilename(
            title=f"Save Creature {label}",
            initialfile=f"{c.name}_interacted.creature.npz",
            defaultextension=".creature.npz",
            filetypes=[("Creature","*.creature.npz"),("NPZ","*.npz"),("All","*.*")])
        if not fp: return
        try:
            out = {}
            out['creature_marker'] = np.array(True)
            out['name']            = np.array(c.name)
            if c.nn_text:
                out['B_W1'] = c.nn_text.W1;  out['B_b1'] = c.nn_text.b1
                out['B_W2'] = c.nn_text.W2;  out['B_b2'] = c.nn_text.b2
                out['B_in']  = np.array(c.nn_text.input_size)
                out['B_hid'] = np.array(c.nn_text.hidden_size)
                out['B_out'] = np.array(c.nn_text.output_size)
            if c.nn_image:
                out['BI_W1'] = c.nn_image.W1; out['BI_b1'] = c.nn_image.b1
                out['BI_W2'] = c.nn_image.W2; out['BI_b2'] = c.nn_image.b2
                out['BI_in']  = np.array(c.nn_image.input_size)
                out['BI_hid'] = np.array(c.nn_image.hidden_size)
                out['BI_out'] = np.array(c.nn_image.output_size)
            out['S_W1'] = c.soul.W1; out['S_b1'] = c.soul.b1
            out['S_W2'] = c.soul.W2; out['S_b2'] = c.soul.b2
            out['S_experience'] = np.array(c.soul.experience)
            out['S_name'] = np.array(c.soul.name if hasattr(c.soul,'name') else c.name)
            if hasattr(c.soul, '_memory') and c.soul._memory:
                vecs   = np.array([m[0] for m in c.soul._memory])
                labels = np.array([m[1] for m in c.soul._memory])
                out['soul_mem_vecs']   = vecs
                out['soul_mem_labels'] = labels
            # Emotion/instinct state
            out['relational_att'] = np.array(c.relational.attachment)
            out['relational_res'] = np.array(c.relational.resentment)
            out['interact_bond']  = np.array(c.bond)
            out['interact_riv']   = np.array(c.rivalry)
            out['saved_at'] = np.array(
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            np.savez(fp, **out)
            self._status_var.set(f"Creature {label} saved: {os.path.basename(fp)}")
            messagebox.showinfo("Saved",
                f"Creature {label} '{c.name}' saved.\n"
                f"Bond: {c.bond:.2f}  Rivalry: {c.rivalry:.2f}\n"
                f"Load with Import... in the main window.")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _save_a(self): self._save_creature(self._ca, 'A')
    def _save_b(self): self._save_creature(self._cb, 'B')

    def _open_breed(self):
        if not (self._ca and self._cb):
            messagebox.showwarning("Breed", "Load both creatures first."); return
        # Pre-save both to temp files then open BreedingDialog
        import tempfile
        def _tmp_save(c):
            tf = tempfile.NamedTemporaryFile(suffix='.creature.npz', delete=False)
            tf.close()
            out = {}
            out['creature_marker'] = np.array(True)
            out['name'] = np.array(c.name)
            if c.nn_text:
                out['B_W1']=c.nn_text.W1; out['B_b1']=c.nn_text.b1
                out['B_W2']=c.nn_text.W2; out['B_b2']=c.nn_text.b2
                out['B_in']=np.array(c.nn_text.input_size)
                out['B_hid']=np.array(c.nn_text.hidden_size)
                out['B_out']=np.array(c.nn_text.output_size)
            out['S_W1']=c.soul.W1; out['S_b1']=c.soul.b1
            out['S_W2']=c.soul.W2; out['S_b2']=c.soul.b2
            np.savez(tf.name, **out)
            return tf.name
        try:
            pa = _tmp_save(self._ca)
            pb = _tmp_save(self._cb)
            dlg = BreedingDialog(self, self.app)
            dlg._pa_full = pa; dlg._pa_path.set(self._ca.name)
            dlg._pb_full = pb; dlg._pb_path.set(self._cb.name)
        except Exception as e:
            messagebox.showerror("Breed Error", str(e))

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_rootx() + (p.winfo_width()  - self.winfo_width())  // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")


class BreedingDialog(tk.Toplevel):
    """Genetics Lab: load two parent creature files, blend traits, produce offspring."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title(" Genetics Lab — Creature Breeding")
        self.configure(bg=BG); self.grab_set(); self.focus_set()
        self.resizable(False, False)

        tk.Label(self, text="   Genetics Lab", bg=BG2, fg='#f38ba8',
                 font=("Courier",14,"bold"), padx=12, pady=10, anchor='w').pack(fill='x')
        tk.Label(self, text="  Combine two creatures to produce a unique offspring.",
                 bg=BG2, fg=FG2, font=("Courier",8,"italic"), padx=12, pady=2,
                 anchor='w').pack(fill='x')

        body = Frm(self, padx=14); body.pack(fill='both', expand=True, pady=6)

        # Parent selectors
        self._pa_path = tk.StringVar(value="")
        self._pb_path = tk.StringVar(value="")
        self._mut_var = tk.DoubleVar(value=0.10)
        self._status_var = tk.StringVar(value="Select both parents to begin.")

        for label, var, btn_cmd in [
            ("Parent A:", self._pa_path, self._browse_a),
            ("Parent B:", self._pb_path, self._browse_b),
        ]:
            rf = Frm(body); rf.pack(fill='x', pady=4)
            tk.Label(rf, text=label, width=10, anchor='w', bg=BG, fg=FG,
                     font=("Courier",9,"bold")).pack(side=tk.LEFT)
            tk.Label(rf, textvariable=var, bg=BG3, fg=FG, anchor='w',
                     font=("Courier",8), width=36).pack(side=tk.LEFT, padx=4)
            Btn(rf, "Browse...", cmd=btn_cmd, color=BG4).pack(side=tk.LEFT)

        # Mutation rate
        mr = Frm(body); mr.pack(fill='x', pady=4)
        tk.Label(mr, text="Mutation rate:", width=14, anchor='w', bg=BG, fg=FG,
                 font=("Courier",9)).pack(side=tk.LEFT)
        DScale(mr, self._mut_var, 0.0, 0.5, length=160,
               resolution=0.01, bg=BG).pack(side=tk.LEFT)
        self._mut_lbl = tk.Label(mr, text="10%", width=5, bg=BG, fg=YEL,
                                  font=("Courier",9))
        self._mut_lbl.pack(side=tk.LEFT)
        self._mut_var.trace_add("write", self._upd_mut_lbl)

        # Preview area
        prev_frm = LFrm(body, "Offspring Preview", padx=8, pady=6)
        prev_frm.pack(fill='x', pady=6)
        self._prev_txt = tk.Text(prev_frm, height=8, width=52, bg=BG3, fg=FG2,
                                  font=("Courier",8), state=tk.DISABLED)
        self._prev_txt.pack(fill='x')
        Btn(prev_frm, "Preview Genetics", cmd=self._preview,
            color=ACN, fg=BG, font=("Courier",9,"bold")).pack(pady=4)

        # Status
        tk.Label(body, textvariable=self._status_var, bg=BG, fg=GRN,
                 font=("Courier",8,"italic"), anchor='w').pack(fill='x', pady=4)

        # Buttons
        br = Frm(body); br.pack(fill='x', pady=6)
        Btn(br, "  Breed Offspring", cmd=self._breed,
            color='#f38ba8', fg=BG, font=("Courier",10,"bold"), padx=10).pack(side=tk.LEFT, padx=4)
        Btn(br, "Close", cmd=self.destroy, color=BG4).pack(side=tk.LEFT, padx=4)

        self._center(parent)

    def _upd_mut_lbl(self, *_):
        try: self._mut_lbl.config(text=f"{int(self._mut_var.get()*100)}%")
        except: pass

    def _browse_a(self):
        fp = filedialog.askopenfilename(title="Select Parent A",
            filetypes=[("Creature","*.creature.npz"),("NPZ","*.npz"),("All","*.*")])
        if fp: self._pa_path.set(os.path.basename(fp)); self._pa_full = fp

    def _browse_b(self):
        fp = filedialog.askopenfilename(title="Select Parent B",
            filetypes=[("Creature","*.creature.npz"),("NPZ","*.npz"),("All","*.*")])
        if fp: self._pb_path.set(os.path.basename(fp)); self._pb_full = fp

    def _load_parent(self, fp):
        d = np.load(fp, allow_pickle=True)
        return d

    def _blend(self, a, b, mut):
        """Blend two scalar/array values 50/50 with optional mutation."""
        alpha = random.uniform(0.4, 0.6)
        v     = alpha * a + (1 - alpha) * b
        if random.random() < mut:
            # Mutate: shift by ±15% of the value's range
            rng = abs(max(float(np.max(a)), float(np.max(b))) -
                      min(float(np.min(a)), float(np.min(b)))) + 0.1
            v  += np.random.normal(0, 0.15 * rng, np.array(v).shape)
        return v

    def _preview(self):
        if not (hasattr(self,'_pa_full') and hasattr(self,'_pb_full')):
            self._status_var.set("Select both parents first."); return
        try:
            da = self._load_parent(self._pa_full)
            db = self._load_parent(self._pb_full)
            mut = float(self._mut_var.get())
            lines = ["Predicted offspring genetics:\n"]
            for key in ('B_W1','B_W2','S_W1','S_W2'):
                if key in da and key in db:
                    va, vb = da[key], db[key]
                    if va.shape == vb.shape:
                        blended = self._blend(va, vb, mut)
                        lines.append(f"  {key:6s}: shape {blended.shape}  "
                                     f"mean={float(np.mean(blended)):.4f}")
            # Genetics if present
            if 'genetics_emo' in da and 'genetics_emo' in db:
                ga = da['genetics_emo'].flatten()
                gb = db['genetics_emo'].flatten()
                blended_g = self._blend(ga, gb, mut)
                lines.append(f"\n  Emo susceptibility blend:")
                for i, nm in enumerate(EmotionState.NAMES[:len(blended_g)]):
                    lines.append(f"    {nm:10s}: {blended_g[i]:.3f}")
            lines.append(f"\n  Mutation rate: {mut*100:.0f}%")
            lines.append(f"  Parent A: {self._pa_path.get()}")
            lines.append(f"  Parent B: {self._pb_path.get()}")
            self._prev_txt.config(state=tk.NORMAL)
            self._prev_txt.delete(1.0, tk.END)
            self._prev_txt.insert(tk.END, '\n'.join(lines))
            self._prev_txt.config(state=tk.DISABLED)
            self._status_var.set("Preview ready. Click Breed to create offspring.")
        except Exception as e:
            self._status_var.set(f"Preview error: {e}")

    def _breed(self):
        if not (hasattr(self,'_pa_full') and hasattr(self,'_pb_full')):
            self._status_var.set("Select both parents first."); return
        fp = filedialog.asksaveasfilename(
            title="Save Offspring Creature",
            defaultextension=".creature.npz",
            filetypes=[("Creature","*.creature.npz"),("All","*.*")])
        if not fp: return
        try:
            da  = self._load_parent(self._pa_full)
            db  = self._load_parent(self._pb_full)
            mut = float(self._mut_var.get())
            out = {}

            # Mark as offspring + lineage
            out['creature_marker'] = np.array(True)
            out['lineage_a'] = np.array(self._pa_path.get())
            out['lineage_b'] = np.array(self._pb_path.get())
            out['generation'] = np.array(
                max(int(da.get('generation', np.array(0))),
                    int(db.get('generation', np.array(0)))) + 1)
            out['bred_at'] = np.array(
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

            # Blend all matching array keys
            for key in set(da.keys()) & set(db.keys()):
                try:
                    va, vb = da[key], db[key]
                    arr_a, arr_b = np.array(va), np.array(vb)
                    if arr_a.shape == arr_b.shape and arr_a.dtype.kind in 'fc':
                        out[key] = self._blend(arr_a, arr_b, mut).astype(arr_a.dtype)
                    elif key not in ('creature_marker','soul_marker',
                                     'generation','bred_at','lineage_a','lineage_b'):
                        out[key] = va   # copy from A for non-blendable
                except Exception:
                    pass

            # Keys only in A or B
            for key in set(da.keys()) - set(db.keys()):
                if key not in out: out[key] = da[key]
            for key in set(db.keys()) - set(da.keys()):
                if key not in out: out[key] = db[key]

            # Distill soul memory: keep top 20 highest-weight memories from each parent
            if 'soul_mem_vecs' in da and 'soul_mem_vecs' in db:
                va = da['soul_mem_vecs'][:20] if len(da['soul_mem_vecs'])>20 else da['soul_mem_vecs']
                vb = db['soul_mem_vecs'][:20] if len(db['soul_mem_vecs'])>20 else db['soul_mem_vecs']
                seed_vecs   = np.concatenate([va, vb], axis=0)
                seed_labels = np.concatenate([
                    da.get('soul_mem_labels', np.array(['neutral']*len(va)))[:len(va)],
                    db.get('soul_mem_labels', np.array(['neutral']*len(vb)))[:len(vb)]
                ])
                out['soul_mem_vecs']   = seed_vecs
                out['soul_mem_labels'] = seed_labels

            # Add slight random mutation to weights for spontaneous traits
            if random.random() < mut * 2:
                for wk in [k for k in out if k.endswith('_W1') or k.endswith('_W2')]:
                    out[wk] = out[wk] + np.random.normal(0, 0.02, out[wk].shape).astype(out[wk].dtype)

            np.savez(fp, **out)
            gen = int(out.get('generation', np.array(1)))
            self._status_var.set(
                f"Offspring (Gen {gen}) saved to: {os.path.basename(fp)}")
            messagebox.showinfo("Breeding Complete",
                f"New creature (Generation {gen}) saved!\n\n"
                f"Parent A: {self._pa_path.get()}\n"
                f"Parent B: {self._pb_path.get()}\n"
                f"Mutation rate: {mut*100:.0f}%\n\n"
                f"Load the offspring with Import... to bring it to life.")
        except Exception as e:
            self._status_var.set(f"Breed error: {e}")
            messagebox.showerror("Error", str(e))

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_rootx() + (p.winfo_width()  - self.winfo_width())  // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")


class App:
    CFG = dict(cfg_hidden_size=64, cfg_learning_rate=0.1, cfg_weight_init=0.1,
               cfg_text_len=32, cfg_img_lbl="16x16", cfg_img_dim=16,
               cfg_out_lbl="64x64", cfg_out_dim=64)

    def __init__(self, root):
        self.root = root
        self.root.title("Neuron 20")
        self.root.configure(bg=BG)
        self.root.geometry("1300x860")
        _apply_dark_style()

        self.nn_store     = {'text': None, 'image': None}
        self._last_x      = None
        self._last_itype  = 'text'
        self._running     = False
        self._rp_steps    = 0
        self._face_window = None

        # ── Core systems ──────────────────────────────────────
        self.emotions         = EmotionState()
        self.soul             = SoulNN(hidden=20)
        self.instincts        = InstinctSystem()
        self.genetics         = GeneticsProfile()
        self.relational       = RelationalState()
        self.tag_image_memory = TagImageMemory()

        self.tag_registry    = {}
        self.image_tags      = {}
        self.knowledge_files = []
        self.word_dict: list = []   # loaded vocabulary for generation

        # ── Play system ───────────────────────────────────────
        self._last_interaction = datetime.datetime.now()  # inactivity timer
        self._play_mode        = False
        self._last_play_action = None   # for approve/discourage

        # Naming
        self.brain_name = tk.StringVar(value="Brain")
        self.soul_name  = tk.StringVar(value="Soul")

        # UI vars
        self.itype       = tk.StringVar(value="text")
        self.noise_lv    = tk.DoubleVar(value=0.0)
        self.iters       = tk.IntVar(value=1)
        self.out_text    = tk.BooleanVar(value=True)
        self.out_graph   = tk.BooleanVar(value=False)
        self.out_heat    = tk.BooleanVar(value=False)
        self.alpha_filt  = tk.BooleanVar(value=False)
        self.rp_str      = tk.DoubleVar(value=0.3)
        self.pred_steps  = tk.IntVar(value=5)
        self.emo_lr      = tk.BooleanVar(value=True)
        self.face_interval = tk.DoubleVar(value=10.0)

        for k, v in self.CFG.items(): setattr(self, k, v)
        self._face_ref = None

        self._build_layout()
        self._schedule_face()
        self._schedule_emotions()
        self._schedule_soul()
        self.root.after(3000, self._passive_train_tick)

    # ── Layout ────────────────────────────────────────────────
    def _build_layout(self):
        pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                              sashwidth=5, bg=BG4)
        pane.pack(fill='both', expand=True)
        lsf = ScrollableFrame(pane)
        rsf = ScrollableFrame(pane)
        pane.add(lsf, width=500, minsize=360)
        pane.add(rsf, minsize=340)
        self.left  = lsf.inner
        self.right = rsf.inner
        self._build_left()
        self._build_right()
        self.on_itype_change()
        self._refresh_out()

    # ── LEFT PANE ─────────────────────────────────────────────
    def _build_left(self):
        L = self.left
        P = dict(padx=10, pady=4)

        tk.Label(L, text="USER / INPUT", bg=BG, fg=ACN,
                 font=("Courier",13,"bold")).grid(row=0,column=0,columnspan=3,
                                                sticky='w',padx=10,pady=(10,2))
        Sep(L).grid(row=1,column=0,columnspan=3,sticky='ew',padx=8)

        # Input type selector
        Lbl(L,"Input type:").grid(row=2,column=0,sticky='w',**P)
        itf=Frm(L); itf.grid(row=2,column=1,columnspan=2,sticky='w',**P)
        for val,txt in [("text","Text"),("image","Image")]:
            tk.Radiobutton(itf,text=txt,variable=self.itype,value=val,
                           bg=BG,fg=FG,selectcolor=BG3,font=("Courier",10),
                           command=self.on_itype_change).pack(side=tk.LEFT,padx=4)

        # ── Text input widgets ─────────────────────────────────
        self.w_tl = Lbl(L,"Enter text:")
        self.w_te = DEntry(L,width=36)

        # Multi-input list (shown with text mode)
        self.w_lb = None  # multi-input removed

        # ── Image input widgets ────────────────────────────────
        self.w_il   = Lbl(L,"Image file:")
        self.w_ipv  = tk.StringVar()
        self.w_id   = tk.Label(L,textvariable=self.w_ipv,bg=BG3,fg=FG,
                               width=28,anchor='w',font=("Courier",9))
        self.w_ib   = Btn(L,"Browse...",cmd=self.browse_image)
        self.w_tagl = Lbl(L,"Tag (optional):")
        self.w_tagv = tk.StringVar()
        self.w_tage = DEntry(L,textvariable=self.w_tagv,width=22)
        self.w_tagn = tk.Label(L,text="Same tag across images = same concept → joint training",
                               bg=BG,fg=FG2,font=("Courier",8),anchor='w')

        # ── Noise ────────────────────────────────────────────────
        Sep(L).grid(row=9,column=0,columnspan=3,sticky='ew',padx=8,pady=3)
        Lbl(L,"Noise:").grid(row=10,column=0,sticky='w',**P)
        DScale(L,self.noise_lv,0.0,1.0).grid(row=10,column=1,columnspan=2,sticky='ew',**P)

        # ── Iterations ────────────────────────────────────────────
        Lbl(L,"Iterations:").grid(row=11,column=0,sticky='w',**P)
        itrf=Frm(L); itrf.grid(row=11,column=1,columnspan=2,sticky='w',**P)
        DSpin(itrf,self.iters,1,100000).pack(side=tk.LEFT,padx=(0,6))
        for v in (1,10,50,100,500):
            Btn(itrf,str(v),cmd=lambda x=v:self.iters.set(x),
                color=BG3,font=("Courier",9),width=4).pack(side=tk.LEFT,padx=1)

        # ── Output options ────────────────────────────────────────
        Sep(L).grid(row=12,column=0,columnspan=3,sticky='ew',padx=8,pady=3)
        tk.Label(L,text="OUTPUTS",bg=BG,fg=ACN,
                 font=("Courier",12,"bold")).grid(row=13,column=0,columnspan=3,
                                                sticky='w',padx=10,pady=(2,2))
        cbf=Frm(L); cbf.grid(row=14,column=0,columnspan=3,sticky='w',padx=10,pady=2)
        for var,txt in [(self.out_text,"Text"),(self.out_graph,"Graph"),(self.out_heat,"Heatmap")]:
            tk.Checkbutton(cbf,text=txt,variable=var,bg=BG,fg=FG,
                           selectcolor=BG3,font=("Courier",10),
                           command=self._refresh_out).pack(side=tk.LEFT,padx=5)

        ff=Frm(L); ff.grid(row=15,column=0,columnspan=3,sticky='w',padx=14,pady=2)
        Lbl(ff,"Text filter:",fg=FG2,font=("Courier",9)).pack(side=tk.LEFT,padx=(0,4))
        self.w_rrb=tk.Radiobutton(ff,text="Raw",variable=self.alpha_filt,value=False,
                                   bg=BG,fg=FG,selectcolor=BG3,font=("Courier",9))
        self.w_arb=tk.Radiobutton(ff,text="A-Z",variable=self.alpha_filt,value=True,
                                   bg=BG,fg=FG,selectcolor=BG3,font=("Courier",9))
        self.w_rrb.pack(side=tk.LEFT,padx=3); self.w_arb.pack(side=tk.LEFT,padx=3)

        tk.Checkbutton(L,text="Emotions modify learning rate & noise",
                       variable=self.emo_lr,bg=BG,fg=FG2,selectcolor=BG3,
                       font=("Courier",9)).grid(row=16,column=0,columnspan=3,
                                              sticky='w',padx=14,pady=2)

        # ── Run / Stop / Predict ──────────────────────────────────
        Sep(L).grid(row=17,column=0,columnspan=3,sticky='ew',padx=8,pady=5)
        bfr=Frm(L); bfr.grid(row=18,column=0,columnspan=3,pady=4,padx=10,sticky='w')
        self.run_btn=Btn(bfr,"Run & Learn",cmd=self.start_run,
                         color='#1e3a6e',fg=FG,font=("Courier",10,"bold"),width=12)
        self.run_btn.pack(side=tk.LEFT,padx=4)
        self.stop_btn=Btn(bfr,"Stop",cmd=self.stop_run,color=RED,fg=BG,width=7,state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT,padx=4)
        Btn(bfr,"Predict →",cmd=self.predict_sequence,color=PRP,fg=BG,
            font=("Courier",10)).pack(side=tk.LEFT,padx=4)
        Lbl(bfr,"×",fg=FG2,font=("Courier",9)).pack(side=tk.LEFT,padx=(6,2))
        DSpin(bfr,self.pred_steps,1,50,width=4).pack(side=tk.LEFT)

        # ── Reward / Punish ───────────────────────────────────────
        bfr2=Frm(L); bfr2.grid(row=19,column=0,columnspan=3,pady=2,padx=10,sticky='w')
        self.rew_btn=Btn(bfr2,"Reward (+10)",cmd=self.apply_reward,
                         color=GRN,fg=BG,font=("Courier",10,"bold"),state=tk.DISABLED)
        self.rew_btn.pack(side=tk.LEFT,padx=4)
        self.pun_btn=Btn(bfr2,"Punish (+10)",cmd=self.apply_punish,
                         color=RED,fg=BG,font=("Courier",10,"bold"),state=tk.DISABLED)
        self.pun_btn.pack(side=tk.LEFT,padx=4)
        sf2=Frm(bfr2); sf2.pack(side=tk.LEFT,padx=(8,0))
        Lbl(sf2,"Str:",fg=FG2,font=("Courier",9)).pack(side=tk.LEFT)
        DSpin(sf2,self.rp_str,0.05,2.0,inc=0.05,fmt="%.2f",width=5).pack(side=tk.LEFT,padx=2)

        self.rp_var=tk.StringVar(value="")
        tk.Label(L,textvariable=self.rp_var,bg=BG,fg=FG2,
                 font=("Courier",8),anchor='w').grid(row=20,column=0,columnspan=3,
                                                   sticky='w',padx=14)

        # ── Tools ─────────────────────────────────────────────────
        Sep(L).grid(row=21,column=0,columnspan=3,sticky='ew',padx=8,pady=5)
        tf=Frm(L); tf.grid(row=22,column=0,columnspan=3,padx=10,pady=4,sticky='w')
        Btn(tf,"Train Text File...",cmd=self.open_text_train,
            color=CYN,fg=BG,font=("Courier",10),padx=8).pack(side=tk.LEFT,padx=4)
        Btn(tf,"Image Tags...",cmd=self.open_tag_mgr,
            color=YEL,fg=BG,font=("Courier",10),padx=8).pack(side=tk.LEFT,padx=4)
        Btn(tf," Dictionary...",cmd=self.load_dictionary,
            color=PRP,fg=BG,font=("Courier",10),padx=8).pack(side=tk.LEFT,padx=4)
        self._dict_lbl = tk.Label(tf,text="No dict",bg=BG,fg=FG2,font=("Courier",8))
        self._dict_lbl.pack(side=tk.LEFT,padx=4)

        # Memory row
        Sep(L).grid(row=23,column=0,columnspan=3,sticky='ew',padx=8,pady=3)
        mf=Frm(L); mf.grid(row=24,column=0,columnspan=3,padx=10,pady=4,sticky='w')
        Btn(mf," Save Long-Term Memory",cmd=self.save_long_term_memory,
            color=BG4,font=("Courier",9),padx=6).pack(side=tk.LEFT,padx=4)
        Btn(mf," Load Long-Term Memory",cmd=self.load_long_term_memory,
            color=BG4,font=("Courier",9),padx=6).pack(side=tk.LEFT,padx=4)
        Btn(mf," Breed...",cmd=self.open_breed_dialog,
            color='#f38ba8',fg=BG,font=("Courier",9,"bold"),padx=6).pack(side=tk.LEFT,padx=4)
        Btn(mf," Interact...",cmd=self.open_interact_dialog,
            color=CYN,fg=BG,font=("Courier",9,"bold"),padx=6).pack(side=tk.LEFT,padx=4)

        L.columnconfigure(1,weight=1)

    # ── RIGHT PANE ────────────────────────────────────────────
    def _build_right(self):
        R = self.right

        # row 0 — header bar (buttons + face)
        hf = Frm(R,bg=BG2); hf.grid(row=0,column=0,columnspan=2,sticky='ew',padx=8,pady=(10,4))
        tk.Label(hf,text="BRAIN",bg=BG2,fg=ACN,
                 font=("Courier",13,"bold")).pack(side=tk.LEFT,padx=4,pady=6)
        Btn(hf,"Brain Setup",cmd=self.open_setup,color=PRP,fg=BG,
            font=("Courier",10,"bold"),padx=8).pack(side=tk.LEFT,padx=4)
        Btn(hf,"Export...",cmd=self.open_save_dialog,color=BG4).pack(side=tk.LEFT,padx=3)
        Btn(hf,"Import...",cmd=self.open_load_dialog,color=BG4).pack(side=tk.LEFT,padx=3)
        Btn(hf," Detach Face",cmd=self._detach_face,color=BG3,
            font=("Courier",8)).pack(side=tk.LEFT,padx=3)

        # Face image — lives inside the header bar on the right
        face_frm=LFrm(hf,"Face",bg=BG2,padx=3,pady=3)
        face_frm.pack(side=tk.RIGHT,padx=8)
        self.face_lbl=tk.Label(face_frm,bg=BG2,width=96,height=96,
                               text="(updates\nevery 10s)",fg=FG2,font=("Courier",7))
        self.face_lbl.pack()
        # Face refresh speed slider
        face_spd = Frm(face_frm, bg=BG2); face_spd.pack(fill='x', pady=(2,0))
        tk.Label(face_spd, text="Refresh:", bg=BG2, fg=FG2,
                 font=("Courier",7)).pack(side=tk.LEFT)
        DScale(face_spd, self.face_interval, 1.0, 60.0, length=82,
               resolution=1.0, bg=BG2, font=("Courier",7)).pack(side=tk.LEFT)
        self._face_spd_lbl = tk.Label(face_spd, text="10s", bg=BG2, fg=FG2, font=("Courier",7))
        self._face_spd_lbl.pack(side=tk.LEFT)
        self.face_interval.trace_add("write", self._upd_face_spd_lbl)

        # row 1 — name fields
        nr = Frm(R,bg=BG3); nr.grid(row=1,column=0,columnspan=2,sticky='ew',padx=8,pady=0)
        tk.Label(nr,text="Brain name:",bg=BG3,fg=FG2,font=("Courier",9)).pack(side=tk.LEFT,padx=(8,4),pady=4)
        DEntry(nr,textvariable=self.brain_name,width=18,bg=BG3,
               font=("Courier",10)).pack(side=tk.LEFT,padx=(0,14))
        tk.Label(nr,text="Soul name:",bg=BG3,fg=FG2,font=("Courier",9)).pack(side=tk.LEFT,padx=(0,4))
        DEntry(nr,textvariable=self.soul_name,width=18,bg=BG3,
               font=("Courier",10)).pack(side=tk.LEFT)

        # row 2 — separator
        Sep(R).grid(row=2,column=0,columnspan=2,sticky='ew',padx=8)

        # row 3 — config badge
        self.badge_var=tk.StringVar()
        tk.Label(R,textvariable=self.badge_var,bg=BG,fg=FG2,
                 font=("Courier",8),anchor='w').grid(row=3,column=0,columnspan=2,
                                                   sticky='w',padx=10,pady=2)
        self._upd_badge()

        # row 4 — progress
        self.prog_var=tk.StringVar(value="")
        tk.Label(R,textvariable=self.prog_var,bg=BG,fg=FG,
                 font=("Courier",9),anchor='w').grid(row=4,column=0,columnspan=2,
                                                     sticky='ew',padx=10,pady=2)

        # Output widgets (toggled by checkboxes)
        self.out_txt_w=tk.Text(R,height=5,width=55,bg=BG3,fg=FG,
                               insertbackground=FG,font=("Courier",10))

        # Persistent image canvas — always visible, shows soul/tag-lookup images reliably
        IMG_DISP = 128  # display size in pixels
        self._img_canvas = tk.Canvas(R, bg=BG3, width=IMG_DISP, height=IMG_DISP,
                                      highlightthickness=1, highlightbackground=BG4)
        self._img_canvas.grid(row=5, column=0, columnspan=2, padx=8, pady=4)
        self._img_canvas.create_text(IMG_DISP//2, IMG_DISP//2,
                                      text="Soul images appear here",
                                      fill=FG2, font=("Courier", 8), tags="placeholder")
        self._img_canvas_size = IMG_DISP
        self._out_img_ref = None
        # Keep the label name for backward compat in existing code
        self.out_img_lbl = self._img_canvas   # alias

        self.fig_g=plt.Figure(figsize=(3.8,3.8),dpi=80)
        self.ax_g=self.fig_g.add_subplot(111)
        self.cv_g=FigureCanvasTkAgg(self.fig_g,master=R)

        self.fig_h=plt.Figure(figsize=(3.8,3.8),dpi=80)
        self.cv_h=FigureCanvasTkAgg(self.fig_h,master=R)

        # Emotion panel  (row 9)
        self.emo_panel=EmotionPanel(R,self.emotions)
        self.emo_panel.grid(row=9,column=0,columnspan=2,sticky='ew',padx=8,pady=4)

        # Instinct panel  (row 10)
        self.inst_panel=InstinctPanel(R,self.instincts)
        self.inst_panel.grid(row=10,column=0,columnspan=2,sticky='ew',padx=8,pady=4)
        self.inst_panel.feed_btn.config(command=self.care_feed)
        self.inst_panel.sleep_btn.config(command=self.care_sleep)
        self.inst_panel.play_btn.config(command=self.care_play)
        self.inst_panel.soothe_btn.config(command=self.care_soothe)

        # Soul panel  (row 11)
        self.soul_panel=SoulPanel(R,self.soul)
        self.soul_panel.grid(row=11,column=0,columnspan=2,sticky='ew',padx=8,pady=4)
        self.soul_panel.rew_soul_btn.config(command=self.reward_soul)
        self.soul_panel.pun_soul_btn.config(command=self.punish_soul)
        self.soul_panel.approve_btn.config(command=self.approve_care_action)
        self.soul_panel.discourage_btn.config(command=self.discourage_care_action)
        self.soul_panel.approve_play_btn.config(command=self._approve_play)
        self.soul_panel.discourage_play_btn.config(command=self._discourage_play)

        # Soul output area
        sf=LFrm(R,"Soul Output",padx=6,pady=4)
        sf.grid(row=12,column=0,columnspan=2,sticky='ew',padx=8,pady=4)
        self.soul_out_txt=tk.Text(sf,height=4,width=55,bg=BG3,fg=CYN,
                                  font=("Courier",9),state=tk.DISABLED)
        self.soul_out_txt.pack(fill='x')

        # History
        self.hist=HistoryPanel(R)
        self.hist.grid(row=13,column=0,columnspan=2,sticky='ew',padx=8,pady=(4,4))

        # Relational Status Panel (row 14)
        self.rel_panel = RelationalStatusPanel(R, self.relational)
        self.rel_panel.grid(row=14,column=0,columnspan=2,sticky='ew',padx=8,pady=(4,8))

        R.columnconfigure(0,weight=1)

    # ── Panel visibility ──────────────────────────────────────
    def _refresh_out(self,*_):
        R=self.right
        if self.out_text.get():
            self.out_txt_w.grid(row=6,column=0,columnspan=2,padx=8,pady=4,sticky='ew',in_=R)
        else: self.out_txt_w.grid_remove()
        if self.out_graph.get():
            self.cv_g.get_tk_widget().grid(row=7,column=0,columnspan=2,padx=8,pady=4,in_=R)
        else: self.cv_g.get_tk_widget().grid_remove()
        if self.out_heat.get():
            self.cv_h.get_tk_widget().grid(row=8,column=0,columnspan=2,padx=8,pady=4,in_=R)
        else: self.cv_h.get_tk_widget().grid_remove()
        fs=tk.NORMAL if self.out_text.get() else tk.DISABLED
        self.w_rrb.config(state=fs); self.w_arb.config(state=fs)

    def _upd_badge(self):
        self.badge_var.set(
            f"h={self.cfg_hidden_size}  lr={self.cfg_learning_rate}  "
            f"tl={self.cfg_text_len}  in={self.cfg_img_dim}x{self.cfg_img_dim}  "
            f"out={self.cfg_out_dim}x{self.cfg_out_dim}")

    # ── Input switching ───────────────────────────────────────
    def on_itype_change(self):
        t=self.itype.get()
        for w in (self.w_tl,self.w_te,
                  self.w_il,self.w_id,self.w_ib,self.w_tagl,self.w_tage,self.w_tagn):
            w.grid_remove()
        L=self.left; P=dict(padx=10,pady=4)
        if t=="text":
            self.w_tl.grid(row=3,column=0,sticky='w',in_=L,**P)
            self.w_te.grid(row=3,column=1,columnspan=2,sticky='ew',in_=L,**P)
        elif t=="image":
            self.w_il.grid(row=3,column=0,sticky='w',in_=L,**P)
            self.w_id.grid(row=3,column=1,sticky='ew',in_=L,**P)
            self.w_ib.grid(row=3,column=2,in_=L,padx=4,pady=4)
            self.w_tagl.grid(row=4,column=0,sticky='w',in_=L,**P)
            self.w_tage.grid(row=4,column=1,sticky='w',in_=L,**P)
            self.w_tagn.grid(row=5,column=0,columnspan=3,sticky='w',in_=L,padx=14,pady=0)

    def browse_image(self):
        p=filedialog.askopenfilename(filetypes=[("Image","*.png *.jpg *.jpeg *.bmp *.gif")])
        if p:
            self.w_ipv.set(p); ex=self.image_tags.get(p,"")
            if ex: self.w_tagv.set(ex)

    def _ensure_nn(self, itype, req_in, req_out):
        """Return existing network unchanged if dimensions match — persistent learning."""
        nn = self.nn_store.get(itype)
        if (nn is None
                or nn.input_size  != req_in
                or nn.output_size != req_out
                or nn.hidden_size != self.cfg_hidden_size):
            nn = SimpleNN(req_in, self.cfg_hidden_size, req_out,
                          w_init=self.cfg_weight_init)
            self.nn_store[itype] = nn
        return nn

    def _eff_lr(self):
        lr = self.cfg_learning_rate
        if self.emo_lr.get():
            lr *= self.emotions.lr_mult()
            lr *= self.instincts.lr_mult()
        lr *= self.relational.lr_mult()
        return max(0.001, min(0.5, lr))

    def _eff_noise(self):
        base = float(self.noise_lv.get())
        if self.emo_lr.get():
            base += self.emotions.noise_add()
            base += self.instincts.noise_add()
        base += self.relational.noise_add()
        return max(0.0, base)

    # ── Reward / Punish ───────────────────────────────────────
    def apply_reward(self):
        self._last_interaction = datetime.datetime.now()
        if self._play_mode: self._exit_play_mode()
        if self._last_x is None: return
        nn=self.nn_store.get(self._last_itype)
        if not nn: return
        s=float(self.rp_str.get())
        nn.reward(self._last_x,s=s,steps=10)
        self._rp_steps+=10
        self.emotions.on_reward(self.genetics)
        self.instincts.on_reward()
        self.relational.on_reward()
        self.genetics.record('reward')
        self.soul.add_memory(self.emotions.to_vec(), 'reward')
        final=nn.forward(self._last_x); mse=float(np.mean((final-self._last_x)**2))
        self.prog_var.set(f"REWARDED +10 (total: {self._rp_steps} steps)  MSE:{mse:.6f}")
        self.rp_var.set(f"Reward steps stacked this session: {self._rp_steps}")
        self._render(self._last_x,final,mse,nn,self._last_itype,event="Reward")

    def apply_punish(self):
        self._last_interaction = datetime.datetime.now()
        if self._play_mode: self._exit_play_mode()
        if self._last_x is None: return
        nn=self.nn_store.get(self._last_itype)
        if not nn: return
        s=float(self.rp_str.get())
        nn.punish(self._last_x,s=s,steps=10)
        self._rp_steps-=10
        self.emotions.on_punish(self.genetics)
        self.instincts.on_punish()
        self.relational.on_punish()
        self.genetics.record('punish')
        self.soul.add_memory(self.emotions.to_vec(), 'punish')
        final=nn.forward(self._last_x); mse=float(np.mean((final-self._last_x)**2))
        self.prog_var.set(f"PUNISHED +10 (total: {abs(self._rp_steps)} steps)  MSE:{mse:.6f}")
        self.rp_var.set(f"Punish steps stacked this session: {abs(self._rp_steps)}")
        self._render(self._last_x,final,mse,nn,self._last_itype,event="Punish")

    def reward_soul(self):
        ev = self.emotions.to_vec()
        self.soul.reward(ev)
        self.relational.on_reward()
        self.soul_panel.log("Soul rewarded. ")
        self._update_face()

    def punish_soul(self):
        ev = self.emotions.to_vec()
        self.soul.punish(ev)
        self.relational.on_punish()
        self.soul_panel.log("Soul punished.")
        self._update_face()

    def approve_care_action(self):
        """User approves the last autonomous care action."""
        ev = self.emotions.to_vec()
        self.soul.approve_care(ev, self.relational)
        self.emotions.on_reward(self.genetics)
        self.soul_panel.log(f"Care approved → '{self.soul.last_care[0] if self.soul.last_care else '?'}' weight ↑")
        self._update_face()

    def discourage_care_action(self):
        """User discourages the last autonomous care action."""
        ev = self.emotions.to_vec()
        self.soul.discourage_care(ev, self.relational)
        self.emotions.on_punish(self.genetics)
        self.soul_panel.log(f"Care discouraged → '{self.soul.last_care[0] if self.soul.last_care else '?'}' weight ↓")
        self._update_face()

    def _approve_play(self):
        """User approves the last play output — treats it like care approval."""
        if self._last_play_action:
            self.soul.care_weights[self._last_play_action] = min(
                4.0, self.soul.care_weights.get(self._last_play_action, 1.0) * 1.25)
            self.soul.reward(self.emotions.to_vec(), s=0.12)
            self.soul_panel.log(f"Play '{self._last_play_action}' approved ↑")
            self.relational.on_reward()
        self._update_face()

    def _discourage_play(self):
        if self._last_play_action:
            self.soul.care_weights[self._last_play_action] = max(
                0.1, self.soul.care_weights.get(self._last_play_action, 1.0) * 0.75)
            self.soul.punish(self.emotions.to_vec(), s=0.08)
            self.soul_panel.log(f"Play '{self._last_play_action}' discouraged ↓")
            self.relational.on_punish()
        self._update_face()


    # ── Predict / Extrapolate ─────────────────────────────────
    def predict_sequence(self):
        nn=self.nn_store.get('text')
        if nn is None or self.itype.get()!='text':
            messagebox.showinfo("Predict","Switch to Text mode and run training first.")
            return
        seed=self.w_te.get()
        if not seed: messagebox.showwarning("Empty","Enter seed text."); return
        steps=int(self.pred_steps.get())
        current=text_to_vec(seed,self.cfg_text_len)
        chain=[seed[:self.cfg_text_len]]
        for _ in range(steps):
            out=nn.forward(current,noise=self._eff_noise()*0.3)
            chain.append(self._dict_text(out))
            current=out
        self.out_txt_w.delete(1.0,tk.END)
        self.out_txt_w.insert(tk.END,"── PREDICTION CHAIN ──\n")
        for i,c in enumerate(chain):
            self.out_txt_w.insert(tk.END,f"[{i}] {c}\n")

    # ── Run loop ──────────────────────────────────────────────
    def start_run(self):
        if not any([self.out_text.get(),self.out_graph.get(),self.out_heat.get()]):
            messagebox.showwarning("No output","Select at least one output."); return
        itype=self.itype.get()
        tag_vecs=[]
        if itype=="text":
            t=self.w_te.get()
            if not t: messagebox.showwarning("No input","Enter text."); return
            vecs=[text_to_vec(t,self.cfg_text_len)]
            nn=self._ensure_nn('text',self.cfg_text_len,self.cfg_text_len)
            x=vecs[0]
            for ip in self.tag_registry.get(t.strip(),[]):
                if os.path.exists(ip):
                    tag_vecs.append(image_to_vec(ip,(self.cfg_img_dim,self.cfg_img_dim)))
            # Text→image: if we have image vectors for this tag, generate matching image
            if tag_vecs and self.out_graph.get():
                self.root.after(100, lambda tv=tag_vecs: self._render_tag_image(tv))
        elif itype=="image":
            p=self.w_ipv.get()
            if not p or not os.path.exists(p):
                messagebox.showwarning("No image","Select an image."); return
            d=self.cfg_img_dim; x=image_to_vec(p,(d,d)); vecs=[x]
            nn=self._ensure_nn('image',d*d,d*d)
            tag=self.w_tagv.get().strip()
            if tag:
                old=self.image_tags.get(p)
                if old and old!=tag:
                    try: self.tag_registry[old].remove(p)
                    except: pass
                    if old in self.tag_registry and not self.tag_registry[old]:
                        del self.tag_registry[old]
                self.image_tags[p]=tag
                self.tag_registry.setdefault(tag,[])
                if p not in self.tag_registry[tag]: self.tag_registry[tag].append(p)
        try:
            total=int(self.iters.get())
            if total<1: raise ValueError
        except: messagebox.showwarning("Bad","Iterations ≥ 1."); return

        self._last_x=x; self._last_itype=itype; self._rp_steps=0; self.rp_var.set("")
        self._last_interaction = datetime.datetime.now()   # user active — exit play mode
        if self._play_mode:
            self._exit_play_mode()
        self._running=True
        self.run_btn.config(state=tk.DISABLED); self.stop_btn.config(state=tk.NORMAL)
        self.rew_btn.config(state=tk.DISABLED); self.pun_btn.config(state=tk.DISABLED)
        self.out_txt_w.delete(1.0,tk.END)
        self._iterate(vecs,tag_vecs,nn,itype,0,total)

    def _iterate(self,vecs,tag_vecs,nn,itype,cur,total):
        if not self._running or cur>=total:
            self._finish(vecs[0],tag_vecs,nn,itype,cur,total); return
        try:
            lr=self._eff_lr(); noise=self._eff_noise()
            for v in vecs:
                nn.forward(v,noise=noise); nn.train(v,lr=lr)
            if tag_vecs:
                img_nn=self._ensure_nn('image',self.cfg_img_dim**2,self.cfg_img_dim**2)
                for iv in tag_vecs:
                    img_nn.forward(iv,noise=noise); img_nn.train(iv,lr=lr)
            # Store image hidden activations for cross-modal recall
            if itype == 'image':
                tag = self.w_tagv.get().strip()
                if tag and nn is not None:
                    conf = max(0.0, 1.0 - float(np.mean((nn.a2 - vecs[0][:nn.a2.shape[1]] if vecs[0].shape[1] >= nn.a2.shape[1] else nn.a2)**2)))
                    self.tag_image_memory.record(tag, nn.a1.copy(), confidence=conf)
            out=nn.forward(vecs[0]); mse=float(np.mean((out-vecs[0])**2))
            self.emotions.on_mse(mse, self.genetics)
            self.instincts.on_training(mse, len(vecs))
            rf=max(1,total//200)
            if cur%rf==0 or cur==total-1:
                pct=int((cur+1)/total*100); bar=(""*(pct//5)).ljust(20)
                jnt=f"  +{len(tag_vecs)}img" if tag_vecs else ""
                self.prog_var.set(f"[{bar}] {pct}%  {cur+1}/{total}  MSE:{mse:.6f}{jnt}")
                self.root.update_idletasks()
        except Exception as e:
            self._finish(vecs[0],tag_vecs,nn,itype,cur,total)
            self.prog_var.set(f"Error during iteration: {e}")
            return
        self.root.after(0,self._iterate,vecs,tag_vecs,nn,itype,cur+1,total)

    def _finish(self,x,tag_vecs,nn,itype,cur,total):
        self._running=False
        self.run_btn.config(state=tk.NORMAL); self.stop_btn.config(state=tk.DISABLED)
        if cur==0: self.prog_var.set("Stopped before any iterations."); return
        final=nn.forward(x); mse=float(np.mean((final-x)**2))
        st="Complete" if cur>=total else f"Stopped@{cur}"
        self.prog_var.set(f"{''*20} {st}  MSE:{mse:.6f}")
        self._render(x,final,mse,nn,itype,event="Run")
        self.rew_btn.config(state=tk.NORMAL); self.pun_btn.config(state=tk.NORMAL)

    def stop_run(self): self._running=False

    # ── Render ────────────────────────────────────────────────
    def _render(self,x,final,mse,nn,itype,event="Run"):
        flat=final.flatten(); td=""

        if self.out_text.get():
            td=vec_to_text(flat,self.alpha_filt.get())
            fl="Alpha" if self.alpha_filt.get() else "Raw  "
            self.out_txt_w.delete(1.0,tk.END)
            if event!="Run": self.out_txt_w.insert(tk.END,f"[{event}]\n")
            self.out_txt_w.insert(tk.END,f"{fl}: {td}\nMSE : {mse:.6f}\n")

        pil_img=None
        if self.out_graph.get():
            od=self.cfg_out_dim
            if itype=="image":
                d=self.cfg_img_dim; raw=(flat.reshape(d,d)*255).astype(np.uint8)
            else:
                raw=(flat*255).astype(np.uint8).reshape(1,-1)
            pil_img=Image.fromarray(raw,'L').resize((od,od),Image.NEAREST)
            self.fig_g.clf(); ax=self.fig_g.add_subplot(111)
            ax.imshow(np.array(pil_img),cmap='gray',vmin=0,vmax=255,interpolation='nearest')
            ax.set_title(f"Network output ({od}×{od})  MSE:{mse:.4f}",fontsize=8)
            ax.axis('off'); self.fig_g.tight_layout(); self.cv_g.draw()

        if self.out_heat.get():
            # Use fig.clf() every time — prevents colorbar accumulation / shrinkage
            self.fig_h.clf()
            ax=self.fig_h.add_subplot(111)
            grid=nn.hidden_grid()
            side=grid.shape[0]
            im=ax.imshow(grid,cmap='inferno',vmin=0,vmax=1,
                         interpolation='nearest',aspect='equal')
            ax.set_title(f"Hidden activations — {nn.hidden_size} neurons ({side}×{side} grid)",
                         fontsize=8)
            ax.set_xlabel("Neuron col",fontsize=7); ax.set_ylabel("Neuron row",fontsize=7)
            ax.tick_params(labelsize=6)
            self.fig_h.colorbar(im,ax=ax,fraction=0.046,pad=0.04)
            self.fig_h.tight_layout(); self.cv_h.draw()

        self.hist.push({"timestamp":datetime.datetime.now().strftime("%H:%M:%S"),
                        "itype":itype,"text_out":td,"mse":mse,
                        "pil_image":pil_img,"event":event})

    # ── Face image ────────────────────────────────────────────
    def _update_face(self):
        try:
            nn  = self.nn_store.get(self._last_itype)
            img = make_face(nn, self.soul, self.emotions, self.instincts,
                            self.relational, size=96)
            ph  = ImageTk.PhotoImage(img); self._face_ref = ph
            self.face_lbl.config(image=ph, text="")
        except: pass
        self._schedule_face()

    def _schedule_face(self):
        ms = max(1000, int(float(self.face_interval.get()) * 1000))
        self.root.after(ms, self._update_face)

    def _upd_face_spd_lbl(self, *_):
        try:
            v = float(self.face_interval.get())
            self._face_spd_lbl.config(text=f"{v:.0f}s")
        except: pass

    # ── Emotion tick ──────────────────────────────────────────
    def _emotion_tick(self):
        try:
            self.instincts.tick()
            self.instincts.influence_emotions(self.emotions)
            self.relational.tick(self.instincts)
            self.genetics.slow_drift()
            # Record neglect event if instincts are high
            if self.instincts.v['hunger'] > 0.75 or self.instincts.v['boredom'] > 0.80:
                self.genetics.record('neglect')
            self.emo_panel.refresh()
            self.inst_panel.refresh()
            self.soul_panel.refresh(self.emotions)
            # Refresh relational panel if visible
            try: self.rel_panel.refresh()
            except: pass
        except: pass
        self.root.after(2000, self._emotion_tick)

    def _schedule_emotions(self):
        self.root.after(2000,self._emotion_tick)

    # ── Soul tick ─────────────────────────────────────────────
    # ── Soul tick (care + spontaneous) ────────────────────────
    def _soul_tick(self):
        try:
            if self.soul_panel.auto_generate:
                self.soul.forward(self.emotions.to_vec())

                # ── Autonomous self-care ──────────────────────
                care = self.soul.decide_care(
                    self.instincts, self.emotions, self.relational)
                if care:
                    action, desc = care
                    self.soul_panel.set_care_action(action, desc)
                    self._execute_care_action(action, desc)

                # ── Random spontaneous generation ─────────────
                boredom_boost    = self.instincts.boredom_gen_boost()
                resentment_boost = self.relational.gen_boost()
                fm = self.soul_panel.freq_mult + boredom_boost*4.0 + resentment_boost*2.0
                if self.soul.should_spontaneously_generate(self.emotions, fm):
                    self._soul_spontaneous('spontaneous')

                # ── Inactivity → play mode ────────────────────
                idle_s = (datetime.datetime.now() - self._last_interaction).total_seconds()
                if (not self._play_mode
                        and idle_s >= self.soul_panel.play_threshold
                        and not self._running):
                    self._enter_play_mode()
                elif self._play_mode:
                    self._play_tick()

                # ── Brain weight nudge ────────────────────────
                pp = 0.07*self.emotions.v['curiosity'] + 0.04*self.relational.resentment
                if random.random() < pp:
                    nn = self.nn_store.get(self._last_itype)
                    if nn:
                        scale = self.soul.weight_noise_scale(self.emotions)
                        if scale > 0.0005:
                            nn.add_weight_noise(scale)
                            self.soul_panel.log(f"Nudged weights ±{scale:.4f}")

                # ── LR suggestion ─────────────────────────────
                if random.random() < 0.04:
                    new_lr = self.soul.suggest_lr_perturb(
                        self.emotions, self.cfg_learning_rate)
                    if abs(new_lr - self.cfg_learning_rate) > 0.005:
                        self.soul_panel.log(
                            f"Suggests lr={new_lr:.4f} (was {self.cfg_learning_rate:.4f})")
        except Exception:
            pass
        self.root.after(8000, self._soul_tick)

    def _schedule_soul(self):
        self.root.after(8000, self._soul_tick)

    # ── Autonomous care execution ──────────────────────────────
    def _execute_care_action(self, action, desc):
        """Run the chosen autonomous care action — real physiological effects."""
        ev = self.emotions.to_vec()
        if action == 'rest':
            # Enter low-effort consolidation: slow tiredness, replay memory
            self.instincts.v['tiredness'] = max(0.0,
                self.instincts.v['tiredness'] - 0.08)
            nn = self.nn_store.get(self._last_itype)
            consolidated = 0
            if nn:
                consolidated = nn.consolidate(passes=1, lr=0.004)
            self.soul.reward(ev, s=0.06)
            self.soul_panel.log(f" Resting — tiredness ↓, consolidated {consolidated} memories")
            self.inst_panel.flash(" Soul initiated rest.")

        elif action in ('generate_text', 'generate_image'):
            # Generate something real to alleviate boredom
            self.instincts.v['boredom'] = max(0.0,
                self.instincts.v['boredom'] - 0.12)
            self.emotions.v['curiosity'] = min(1.0,
                self.emotions.v['curiosity'] + 0.08)
            itype = 'text' if action == 'generate_text' else 'image'
            self._soul_spontaneous(source='care_boredom', forced_itype=itype)
            self.soul_panel.log(f" Generated {itype} to relieve boredom.")
            self.inst_panel.flash(f" Soul playing ({itype})!")

        elif action == 'soothe':
            # Generate calming internal patterns
            self.instincts.v['pain'] = max(0.0,
                self.instincts.v['pain'] - 0.10)
            self.emotions.v['calm'] = min(1.0,
                self.emotions.v['calm'] + 0.12)
            self.emotions.v['fear'] = max(0.0,
                self.emotions.v['fear'] - 0.08)
            self.soul.reward(ev, s=0.08)
            self._soul_spontaneous(source='care_soothe', forced_itype='image')
            self.soul_panel.log(" Soothing pain with comforting generation.")
            self.inst_panel.flash(" Soul is soothing itself.")

        elif action == 'seek_food':
            # Can't feed itself — nudge user with status message
            msg = self.soul.hunger_nudge_msg()
            self.prog_var.set(f"[Soul] {msg}")
            self.soul_panel.log(f" {msg}")
            self.inst_panel.flash(" Soul is hungry — feed it!")

        self._update_face()

    # ── Play mode ─────────────────────────────────────────────
    def _enter_play_mode(self):
        self._play_mode = True
        self.instincts.v['boredom'] = max(0.0,
            self.instincts.v['boredom'] - 0.05)  # slight relief on entry
        self.soul_panel.set_play_state(True, "starting...")
        self.soul_panel.log(" Entering play mode (idle too long).")

    def _exit_play_mode(self):
        if self._play_mode:
            self._play_mode = False
            self.soul_panel.set_play_state(False)
            self.soul_panel.log(" User returned — exiting play mode.")

    def _play_tick(self):
        """One step of autonomous play behaviour."""
        em = self.emotions.v
        iv = self.instincts.v
        # Don't play if very tired or in pain — physiological needs first
        if iv['tiredness'] > 0.80 or iv['pain'] > 0.70:
            self.soul_panel.set_play_state(True, "resting instead...")
            self.instincts.v['tiredness'] = max(0.0, iv['tiredness'] - 0.04)
            return

        # Pick activity weighted by play_style and emotional state
        ps = self.soul.play_style
        # Options: generate_text, generate_image, memory_replay, brain_explore
        weights = {
            'generate_image': (1.0 - ps) * 2.0 + em['happiness'] * 0.5,
            'generate_text':  ps * 2.0 + em['curiosity'] * 0.5,
            'memory_replay':  0.5 + em['sadness'] * 0.8,
            'brain_explore':  0.3 + em['curiosity'] * 0.6,
        }
        choices = list(weights.keys())
        w_vals  = np.array([weights[c] for c in choices])
        w_vals /= w_vals.sum()
        activity = random.choices(choices, weights=w_vals, k=1)[0]

        self.soul_panel.set_play_state(True, activity.replace('_', ' '))
        self._last_play_action = activity

        if activity == 'generate_image':
            self._soul_spontaneous(source='play', forced_itype='image')
            msg = "Imagined something — dreaming in images."
        elif activity == 'generate_text':
            self._soul_spontaneous(source='play', forced_itype='text')
            msg = "Composed some thoughts — daydreaming."
        elif activity == 'memory_replay':
            # Re-run a past working-memory sample through current state
            nn = self.nn_store.get(self._last_itype)
            if nn and nn._working_mem:
                x, _ = random.choice(nn._working_mem)
                out  = nn.forward(x, noise=0.05)
                txt  = self._dict_text(out)[:36]
                msg  = f'Replayed memory: "{txt}..."'
            else:
                msg = "Tried to replay a memory, but mind is blank."
        elif activity == 'brain_explore':
            nn = self.nn_store.get(self._last_itype)
            if nn:
                scale = 0.002 + em['curiosity'] * 0.003
                nn.add_weight_noise(scale)
                msg = f"Explored by nudging weights ±{scale:.4f}."
            else:
                msg = "Explored, but no brain to play with yet."

        # Wellbeing effects of play
        self.instincts.v['boredom'] = max(0.0, iv['boredom'] - 0.06)
        self.emotions.v['happiness'] = min(1.0, em['happiness'] + 0.04)
        self.emotions.v['sadness']   = max(0.0, em['sadness']   - 0.02)
        # Attachment maintenance during absence
        self.relational.attachment = min(1.0, self.relational.attachment + 0.005)
        # Play trains the network slightly — play contributes to learning
        if activity == 'brain_explore':
            nn = self.nn_store.get(self._last_itype)
            if nn and nn._working_mem:
                x, _ = random.choice(nn._working_mem)
                nn.forward(x); nn.train(x, lr=self.cfg_learning_rate * 0.02)
        elif activity == 'memory_replay':
            nn = self.nn_store.get(self._last_itype)
            if nn and nn._working_mem:
                # Replay a memory — consolidate at very low LR
                nn.consolidate(passes=1, lr=0.003)

        self.soul.add_memory(self.emotions.to_vec(), 'neutral')
        self.soul_panel.log_play(msg)
        self._soul_out(f"[Play] {msg}")

    # ── Tangible spontaneous generation ───────────────────────
    def _soul_spontaneous(self, source='spontaneous', forced_itype=None):
        """Generate real, visible output — text in text box, image in image box."""
        itype = forced_itype or self._last_itype
        nn    = self.nn_store.get(itype)
        if nn is None:
            # Try the other modality
            itype = 'image' if itype == 'text' else 'text'
            nn    = self.nn_store.get(itype)
        if nn is None:
            self.soul_panel.log("(no network yet for generation)")
            return

        ev    = self.emotions.to_vec()
        noise = self._eff_noise() + 0.08 + self.emotions.v['anger'] * 0.05
        # Blend random seed with soul output for emotional colouring
        rand_in = np.random.rand(1, nn.input_size)
        soul_out = self.soul.forward(ev).flatten()
        soul_mod = soul_out[:nn.input_size] if len(soul_out) >= nn.input_size \
                   else np.resize(soul_out, nn.input_size)
        x = rand_in * 0.7 + soul_mod.reshape(1, -1) * 0.3
        out = nn.forward(x, noise=noise)
        thought = self.soul.get_thought(self.emotions)

        label_prefix = {
            'spontaneous':   '',
            'care_boredom':  '',
            'care_soothe':   '',
            'play':          '',
        }.get(source, '')

        if itype == 'text':
            txt = self._dict_text(out)
            display = f"{label_prefix} [Soul] {thought}\n   → \"{txt[:60]}\"\n"
            try:
                self.out_txt_w.config(state=tk.NORMAL)
                self.out_txt_w.insert(tk.END, display)
                self.out_txt_w.see(tk.END)
                self.out_txt_w.config(state=tk.DISABLED if not self.out_text.get() else tk.NORMAL)
            except Exception:
                pass
            self.soul_panel.log(f"{label_prefix} Text: \"{txt[:28]}...\"")
            self._soul_out(display)
        else:
            # Render emotionally-tinted image → reliably display on canvas + matplotlib
            try:
                d   = self.cfg_img_dim
                pix = np.clip(out.flatten()[:d*d], 0, 1)
                r_e, g_e, b_e = _emotion_rgb(self.emotions)
                r = np.clip(pix * (0.6 + 0.4*r_e), 0, 1)
                g = np.clip(pix * (0.6 + 0.4*g_e), 0, 1)
                b = np.clip(pix * (0.6 + 0.4*b_e), 0, 1)
                rgb   = (np.stack([r,g,b],axis=-1)*255).astype(np.uint8)
                small = Image.fromarray(rgb.reshape(d,d,3),'RGB')
                sz    = self._img_canvas_size
                big   = small.resize((sz, sz), Image.NEAREST)
                ph    = ImageTk.PhotoImage(big)
                self._out_img_ref = ph   # MUST hold reference or GC kills it
                self._img_canvas.delete("all")
                self._img_canvas.create_image(0, 0, anchor='nw', image=ph)
                lbl_text = f"{label_prefix} {source}"
                self._img_canvas.create_text(4, sz-12, anchor='sw',
                    text=lbl_text, fill='#f9e2af', font=("Courier",7))
                # Also paint into matplotlib graph if visible
                try:
                    self.fig_g.clf()
                    ax = self.fig_g.add_subplot(111)
                    ax.imshow(np.array(big), interpolation='nearest')
                    ax.set_title(f"{label_prefix} Soul dream — {thought[:40]}",
                                 fontsize=7, color='#f9e2af')
                    ax.axis('off')
                    self.fig_g.patch.set_facecolor('#0f0f1a')
                    ax.set_facecolor('#0f0f1a')
                    self.fig_g.tight_layout()
                    self.cv_g.draw()
                except Exception:
                    pass
            except Exception as img_err:
                self.soul_panel.log(f"[img err] {img_err}")
            msg = f"{label_prefix} Image dreamed ({source})"
            self.soul_panel.log(msg)
            self._soul_out(f"{label_prefix} [Soul] {thought}\n   → [image generated]")

        # ── Reinforce via training on generated output (dreaming strengthens networks) ──
        if nn is not None:
            try:
                train_lr = self._eff_lr() * 0.03  # very gentle — play learning
                nn.forward(x); nn.train(x, lr=train_lr)
                # For image generation also slightly reinforce the output pattern
                if itype == 'image':
                    out_clamped = np.clip(out, 0.05, 0.95)
                    nn.forward(out_clamped); nn.train(out_clamped, lr=train_lr * 0.5)
                self.soul.experience = min(2.0, self.soul.experience + 0.005)
            except Exception:
                pass

        self.soul.add_memory(ev, 'neutral')

    def _soul_out(self, msg):
        self.soul_out_txt.config(state=tk.NORMAL)
        self.soul_out_txt.insert(tk.END,
            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n\n")
        self.soul_out_txt.see(tk.END)
        self.soul_out_txt.config(state=tk.DISABLED)

    # ── Manual care actions (instinct panel buttons) ───────────
    def care_feed(self):
        self._last_interaction = datetime.datetime.now()
        self.instincts.feed()
        self.emotions.on_reward(self.genetics)
        self.relational.on_care()
        self.genetics.record('care')
        self.soul.reward(self.emotions.to_vec(), s=0.15)
        self.soul_panel.log(" Fed — hunger reduced.")
        self.inst_panel.flash(" Fed! Hunger reduced.")
        self._update_face()

    def care_sleep(self):
        self._last_interaction = datetime.datetime.now()
        self.instincts.sleep()
        self.emotions.v['calm']      = min(1.0, self.emotions.v['calm']      + 0.25)
        self.emotions.v['happiness'] = min(1.0, self.emotions.v['happiness'] + 0.10)
        self.relational.on_care()
        self.genetics.record('care')
        # Consolidate working memory during sleep
        for nn in self.nn_store.values():
            if nn: nn.consolidate(passes=3, lr=0.005)
        self.soul_panel.log(" Slept — tiredness reset, memories consolidated.")
        self.inst_panel.flash(" Rested! Memories consolidated.")
        self._update_face()

    def care_play(self):
        self._last_interaction = datetime.datetime.now()
        self.instincts.play()
        self.emotions.v['curiosity'] = min(1.0, self.emotions.v['curiosity'] + 0.20)
        self.emotions.v['happiness'] = min(1.0, self.emotions.v['happiness'] + 0.15)
        self.relational.on_care()
        self.genetics.record('care')
        if random.random() < 0.5:
            self._soul_spontaneous(source='care_boredom')
        self.soul_panel.log(" Played — boredom reduced.")
        self.inst_panel.flash(" Played! Boredom reduced.")
        self._update_face()

    def care_soothe(self):
        self._last_interaction = datetime.datetime.now()
        self.instincts.soothe()
        self.emotions.v['fear']  = max(0.0, self.emotions.v['fear']  - 0.25)
        self.emotions.v['anger'] = max(0.0, self.emotions.v['anger'] - 0.20)
        self.emotions.v['calm']  = min(1.0, self.emotions.v['calm']  + 0.30)
        self.relational.on_care()
        self.genetics.record('care')
        self.soul_panel.log(" Soothed — pain reduced.")
        self.inst_panel.flash(" Soothed! Pain reduced.")
        self._update_face()

    def _detach_face(self):
        if self._face_window and self._face_window.winfo_exists():
            self._face_window.lift(); return
        self._face_window = DetachedFaceWindow(self)

    # ── Export / Import dialogs ───────────────────────────────
    def open_save_dialog(self):
        ExportDialog(self.root, self)

    def open_load_dialog(self):
        ImportDialog(self.root, self)

    def save_nn(self): self.open_save_dialog()
    def load_nn(self): self.open_load_dialog()

    # ── Knowledge library ─────────────────────────────────────
    def _render_tag_image(self, tag_vecs):
        """When text input has known image tags, generate a matching image output."""
        img_nn = self.nn_store.get('image')
        if img_nn is None: return
        try:
            avg   = np.mean(np.vstack(tag_vecs), axis=0, keepdims=True)
            noise = self._eff_noise() * 0.3
            out   = img_nn.forward(avg, noise=noise)
            d     = self.cfg_img_dim
            sz    = self._img_canvas_size
            pix   = np.clip(out.flatten()[:d*d], 0, 1)
            r_e, g_e, b_e = _emotion_rgb(self.emotions)
            r = np.clip(pix * (0.55 + 0.45*r_e), 0, 1)
            g = np.clip(pix * (0.55 + 0.45*g_e), 0, 1)
            b = np.clip(pix * (0.55 + 0.45*b_e), 0, 1)
            rgb   = (np.stack([r,g,b],axis=-1)*255).astype(np.uint8)
            small = Image.fromarray(rgb.reshape(d,d,3),'RGB')
            big   = small.resize((sz, sz), Image.NEAREST)
            ph    = ImageTk.PhotoImage(big)
            self._out_img_ref = ph
            self._img_canvas.delete("all")
            self._img_canvas.create_image(0, 0, anchor='nw', image=ph)
            self._img_canvas.create_text(4, sz-12, anchor='sw',
                text=" tag match", fill='#a6e3a1', font=("Courier",7))
            # Also update graph if visible
            try:
                self.fig_g.clf(); ax = self.fig_g.add_subplot(111)
                ax.imshow(np.array(big), interpolation='nearest')
                ax.set_title("Tag-matched image from text", fontsize=8)
                ax.axis('off'); self.fig_g.tight_layout(); self.cv_g.draw()
            except Exception:
                pass
        except Exception:
            pass

    # ── Passive dictionary training ───────────────────────────
    def _passive_train_tick(self):
        """Passively train text network on dictionary words when not actively training."""
        try:
            if (not self._running
                    and self.word_dict
                    and self.nn_store.get('text') is not None):
                nn   = self.nn_store['text']
                word = random.choice(self.word_dict)
                x    = text_to_vec(word, self.cfg_text_len)
                lr   = self.cfg_learning_rate * 0.05   # very gentle — passive
                nn.forward(x); nn.train(x, lr=lr)
        except Exception:
            pass
        self.root.after(3000, self._passive_train_tick)

    # ── Short/Long-term memory system ─────────────────────────
    def save_long_term_memory(self):
        """Convert working memory (short-term) → long-term memory file.
        Runs consolidation passes then saves weights to a .ltm.npz file."""
        fp = filedialog.asksaveasfilename(
            title="Save Long-Term Memory",
            defaultextension=".ltm.npz",
            filetypes=[("Long-term memory","*.ltm.npz"),("All files","*.*")])
        if not fp: return
        try:
            consolidated = {}
            for itype, nn in self.nn_store.items():
                if nn is None: continue
                # Consolidate working memory first
                n = nn.consolidate(passes=4, lr=0.004)
                consolidated[f"{itype}_W1"]  = nn.W1
                consolidated[f"{itype}_b1"]  = nn.b1
                consolidated[f"{itype}_W2"]  = nn.W2
                consolidated[f"{itype}_b2"]  = nn.b2
                consolidated[f"{itype}_in"]  = np.array(nn.input_size)
                consolidated[f"{itype}_hid"] = np.array(nn.hidden_size)
                consolidated[f"{itype}_out"] = np.array(nn.output_size)
                consolidated[f"{itype}_wm_count"] = np.array(len(nn._working_mem))
            # Soul emotional memory
            if self.soul._memory:
                vecs   = np.array([m[0] for m in self.soul._memory])
                labels = np.array([m[1] for m in self.soul._memory])
                consolidated['soul_mem_vecs']   = vecs
                consolidated['soul_mem_labels'] = labels
            # Dictionary
            if self.word_dict:
                consolidated['word_dict'] = np.array(self.word_dict)
            consolidated['tag_registry_keys'] = np.array(
                list(self.tag_registry.keys()))
            consolidated['relational_att'] = np.array(self.relational.attachment)
            consolidated['relational_res'] = np.array(self.relational.resentment)
            consolidated['saved_at'] = np.array(
                datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            np.savez(fp, **consolidated)
            messagebox.showinfo("Memory Saved",
                f"Long-term memory consolidated and saved to:\n{fp}\n"
                f"({sum(len(nn._working_mem) for nn in self.nn_store.values() if nn)} working memories consolidated)")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def load_long_term_memory(self):
        """Load a long-term memory file — restores weights and memories."""
        fp = filedialog.askopenfilename(
            title="Load Long-Term Memory",
            filetypes=[("Long-term memory","*.ltm.npz"),("All files","*.*")])
        if not fp: return
        try:
            d = np.load(fp, allow_pickle=True)
            for itype in ('text', 'image'):
                if f"{itype}_W1" not in d: continue
                in_s  = int(d[f"{itype}_in"])
                hid_s = int(d[f"{itype}_hid"])
                out_s = int(d[f"{itype}_out"])
                nn    = SimpleNN(in_s, hid_s, out_s)
                nn.W1 = d[f"{itype}_W1"]; nn.b1 = d[f"{itype}_b1"]
                nn.W2 = d[f"{itype}_W2"]; nn.b2 = d[f"{itype}_b2"]
                nn._init_momentum()
                self.nn_store[itype] = nn
                self.cfg_hidden_size  = hid_s
            if 'soul_mem_vecs' in d:
                vecs   = d['soul_mem_vecs']
                labels = d['soul_mem_labels']
                self.soul._memory = [(vecs[i], str(labels[i]))
                                     for i in range(len(vecs))]
            if 'word_dict' in d:
                self.word_dict = list(d['word_dict'])
                try: self._dict_lbl.config(text=f"{len(self.word_dict)} words")
                except: pass
            if 'relational_att' in d:
                self.relational.attachment = float(d['relational_att'])
                self.relational.resentment = float(d['relational_res'])
            saved_at = str(d['saved_at']) if 'saved_at' in d else '?'
            self._upd_badge()
            messagebox.showinfo("Memory Loaded",
                f"Long-term memory loaded.\nSaved: {saved_at}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def load_dictionary(self):
        """Load a .txt word list — one word per line or space-separated."""
        fp = filedialog.askopenfilename(
            title="Load Word Dictionary",
            filetypes=[("Text files","*.txt"),("All files","*.*")])
        if not fp: return
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                raw = f.read()
            words = [w.strip().lower() for w in raw.replace('\n',' ').split()
                     if w.strip() and w.strip().isalpha()]
            words = sorted(set(words))
            self.word_dict = words
            self._dict_lbl.config(text=f"{len(words)} words")
            messagebox.showinfo("Dictionary Loaded",
                f"Loaded {len(words)} unique words from:\n{fp}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _dict_text(self, vec):
        """Convert output vector to words using loaded dictionary when available.
        Falls back to standard vec_to_text if no dictionary is loaded."""
        if not self.word_dict:
            return vec_to_text(vec, self.alpha_filt.get())
        flat = vec.flatten()
        # Map each fixed-size chunk to a word index
        n     = len(self.word_dict)
        chunk = max(1, len(flat) // 6)   # pick ~6 words per output
        parts = []
        for i in range(0, len(flat), chunk):
            val = float(np.mean(flat[i:i+chunk]))
            idx = int(val * (n - 1))
            parts.append(self.word_dict[max(0, min(n-1, idx))])
        return ' '.join(parts)

    def open_interact_dialog(self): CreatureInteractionDialog(self.root, self)
    def open_breed_dialog(self): BreedingDialog(self.root, self)

    def open_setup(self):    BrainSetupDialog(self.root,self)
    def open_tag_mgr(self):  TagManagerDialog(self.root,self)
    def open_text_train(self):
        self._ensure_nn('text',self.cfg_text_len,self.cfg_text_len)
        TextTrainDialog(self.root,self)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()