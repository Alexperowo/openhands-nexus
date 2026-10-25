import ctypes
import re
import threading
from functools import lru_cache


# Familiar Russian names take precedence over English phonetics and initialisms.
TERMS = {
    "openhands": "Оупен Хэндс", "github": "Гитхаб", "linux": "Линукс",
    "python": "Пайтон", "readme": "ридми", "json": "джейсон",
    "docker": "докер", "ubuntu": "убунту", "nexus": "нексус",
    "silero": "силеро", "gigaam": "гига ам", "fastapi": "фаст эй-пи-ай",
    "javascript": "джаваскрипт", "typescript": "тайпскрипт",
    "git": "гит", "pip": "пип", "uv": "ю-ви", "npm": "эн-пи-эм",
    "sudo": "судо", "bash": "баш", "curl": "кёрл", "pytest": "пай тест",
    "py": "пай", "md": "эм-ди", "ts": "ти-эс", "tsx": "ти-эс-экс",
    "yaml": "ямл", "yml": "ямл", "toml": "томл", "txt": "текст",
    "sql": "эс-кью-эл", "localhost": "локал хост",
    "service": "сервис", "server": "сервер", "user": "юзер", "queue": "кью",
}
LETTERS = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", (
    "эй", "би", "си", "ди", "и", "эф", "джи", "эйч", "ай", "джей",
    "кей", "эл", "эм", "эн", "оу", "пи", "кью", "ар", "эс", "ти",
    "ю", "ви", "дабл-ю", "экс", "уай", "зед",
)))
# Flite's CMU phones use ax for schwa and append 0/1 for vowel stress.
PHONES = {
    "aa": "а", "ae": "э", "ah": "а", "ao": "о", "aw": "ау",
    "ax": "э", "ay": "ай", "b": "б", "ch": "ч", "d": "д",
    "dh": "з", "eh": "э", "er": "ёр", "ey": "эй", "f": "ф",
    "g": "г", "hh": "х", "ih": "и", "iy": "и", "jh": "дж",
    "k": "к", "l": "л", "m": "м", "n": "н", "ng": "нг",
    "ow": "оу", "oy": "ой", "p": "п", "r": "р", "s": "с",
    "sh": "ш", "t": "т", "th": "с", "uh": "у", "uw": "у",
    "v": "в", "w": "у", "y": "й", "z": "з", "zh": "ж",
}
_flite_lock = threading.Lock()
_flite = None
_cmu = None
_lexicon = None


def _load_flite():
    global _flite, _cmu, _lexicon
    if _flite is not None:
        return
    try:
        lib = ctypes.CDLL("libflite.so.1", mode=ctypes.RTLD_GLOBAL)
        cmu = ctypes.CDLL("libflite_cmulex.so.1")
    except OSError as error:
        raise RuntimeError("English pronunciation requires the system package libflite1") from error
    lib.flite_init.argtypes = []
    lib.flite_init.restype = ctypes.c_int
    cmu.cmu_lex_init.argtypes = []
    cmu.cmu_lex_init.restype = ctypes.c_void_p
    lib.lex_lookup.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
                              ctypes.POINTER(ctypes.c_int)]
    lib.lex_lookup.restype = ctypes.c_void_p
    for name in ("val_car", "val_cdr"):
        getattr(lib, name).argtypes = [ctypes.c_void_p]
        getattr(lib, name).restype = ctypes.c_void_p
    lib.val_string.argtypes = [ctypes.c_void_p]
    lib.val_string.restype = ctypes.c_char_p
    lib.delete_val.argtypes = [ctypes.c_void_p]
    lib.delete_val.restype = None
    lib.flite_init()
    lexicon = cmu.cmu_lex_init()
    if not lexicon:
        raise RuntimeError("Flite could not initialize its CMU lexicon")
    _cmu, _lexicon, _flite = cmu, lexicon, lib


@lru_cache(maxsize=4096)
def _english(word: str) -> str:
    # Flite owns global state; serialize initialization, lookup and list cleanup.
    with _flite_lock:
        _load_flite()
        values = _flite.lex_lookup(_lexicon, word.encode("ascii"), None, None)
        try:
            result, node = [], values
            while node:
                phone = _flite.val_string(_flite.val_car(node)).decode("ascii")
                result.append(PHONES[phone.rstrip("012")])
                node = _flite.val_cdr(node)
        finally:
            _flite.delete_val(values)
    if not result:
        raise ValueError(f"Flite returned no pronunciation for {word!r}")
    return "".join(result)


def _word(word: str) -> str:
    if word.lower() in TERMS:
        return TERMS[word.lower()]
    if word.isupper() or len(word) == 1:
        return "-".join(LETTERS[c] for c in word.upper())
    try:
        return _english(word.lower())
    except (RuntimeError, ValueError, KeyError):
        # Without Flite or with an unknown phone, letters are still better than the silence Silero gives.
        return "-".join(LETTERS[c] for c in word.upper())


def _identifier(match: re.Match) -> str:
    token = match.group()
    if len(token) > 64 or (token.isupper() and len(token) > 16):
        return "идентификатор"
    # HTTPServer -> HTTP Server; camelCase -> camel Case; snake_case -> snake case.
    token = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", token)
    token = re.sub(r"([a-z])([A-Z])", r"\1 \2", token)
    token = token.replace("_", " ")
    return re.sub(r"[A-Za-z]+", lambda m: _word(m.group()), token)


_TRAIL = ".,;:!?…"
_URL = re.compile(r"(?:[a-zA-Z][a-zA-Z0-9+.-]*://|www\.)[^\s<>\[\]()«»\"'`]+", re.I)
_DOMAIN = re.compile(r"(?<![\w@])(?:[a-zA-Z0-9-]+\.)+(?:com|org|net|io|dev|ru|рф)\b"
                     r"(?:/[^\s<>\[\]()«»\"'`]+)?", re.I)
_PATH = re.compile(r"(?<![\w])(?:[A-Za-z]:[\\/]|~?/|\.{1,2}/|"
                   r"(?=[\w.-]+/[\w.-]+/))[\w./\\-]+")
_HASH = re.compile(r"\b(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{16,}|"
                   r"(?=[0-9a-fA-F]{7,}\b)(?=[0-9a-fA-F]*\d)[0-9a-fA-F]*[a-fA-F][0-9a-fA-F]*)\b")


def _shorten(match: re.Match, replacement: str) -> str:
    raw = match.group()
    return replacement + raw[len(raw.rstrip(_TRAIL)):]


def _path(match: re.Match) -> str:
    raw = match.group().rstrip(_TRAIL)
    parts = [p for p in re.split(r"[/\\]", raw) if p and p not in ("~", ".", "..")]
    replacement = "путь к файлу" if len(raw) > 50 or len(parts) > 2 else (parts[-1] if parts else "путь")
    return _shorten(match, replacement)


def for_silero(text: str) -> str:
    text = _URL.sub(lambda m: _shorten(m, "ссылка"), text)
    text = _DOMAIN.sub(lambda m: _shorten(m, "ссылка"), text)
    text = _PATH.sub(_path, text)
    text = _HASH.sub("хэш", text)
    text = re.sub(r"(?<=[A-Za-z0-9])\.(?=[A-Za-z])", " точка ", text)
    # Protect conventional names before splitting their internal capital letters.
    text = re.sub(r"[A-Za-z][A-Za-z0-9_]*", lambda m: TERMS.get(m.group().lower())
                  or _identifier(m), text)
    text = text.replace("`", "")
    return text
