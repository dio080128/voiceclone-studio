# -*- coding: utf-8 -*-
"""文本规范化：面向中文 / 英文混合 Unicode 文本的 TTS 前置处理。

覆盖内容：
  * Unicode NFC/NFKC 归一、全角转半角、零宽字符与不可见控制符清理
  * 表情符号 / 装饰性符号移除（可关闭），常用数学、货币符号转读法
  * 中文语境标点回填（, -> ，；. -> 。 等）
  * 数字读法：整数、小数、年份、电话长串、百分比、货币、时间、日期、区间
  * 中英文之间自动补空格，利于声学模型断句
  * 逐字符覆盖度检查，报告引擎无法处理的字符
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple

# --------------------------------------------------------------------------- #
# 字符分类
# --------------------------------------------------------------------------- #

CJK_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x3400, 0x4DBF),    # 扩展 A
    (0x4E00, 0x9FFF),    # 基本区
    (0xF900, 0xFAFF),    # 兼容汉字
    (0x20000, 0x2FA1F),  # 扩展 B~F
)

CJK_PUNCT = "，。！？；：、（）《》〈〉「」『』【】“”‘’…—～·"
ASCII_PUNCT = ",.!?;:()[]\"'-/%&@#*+=<>~|\\{}_`$"

EMOJI_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x1F000, 0x1FAFF),
    (0x1F1E6, 0x1F1FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),
    (0x1F900, 0x1F9FF),
    (0x2190, 0x21FF),
    (0x2700, 0x27BF),
    (0xE000, 0xF8FF),   # 私有区
    (0x200B, 0x200F),   # 零宽
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0xFEFF, 0xFEFF),
)

SYMBOL_MAP_CN = {
    "×": "乘", "÷": "除以", "±": "正负", "≈": "约等于",
    "≥": "大于等于", "≤": "小于等于", "≠": "不等于",
    "→": "到", "←": "从", "↑": "上", "↓": "下",
    "℃": "摄氏度", "°": "度", "№": "编号", "§": "第",
    "①": "一", "②": "二", "③": "三", "④": "四", "⑤": "五",
    "⑥": "六", "⑦": "七", "⑧": "八", "⑨": "九", "⑩": "十",
}

SYMBOL_MAP_EN = {
    "×": " times ", "÷": " divided by ", "±": " plus or minus ",
    "≈": " about ", "≥": " greater than or equal to ",
    "≤": " less than or equal to ", "≠": " not equal to ",
    "→": " to ", "←": " from ",
    "℃": " degrees Celsius", "°": " degrees",
}

CN_DIGITS = "零一二三四五六七八九"
CN_UNITS = ("千", "百", "十", "")
CN_BIG = ("", "万", "亿", "万亿")

EN_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
EN_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
           "eighty", "ninety")

DIGIT_CN = {str(i): CN_DIGITS[i] for i in range(10)}


# --------------------------------------------------------------------------- #
# 字符判定
# --------------------------------------------------------------------------- #

def is_cjk(ch: str) -> bool:
    o = ord(ch)
    for lo, hi in CJK_RANGES:
        if lo <= o <= hi:
            return True
    return False


def is_emoji(ch: str) -> bool:
    o = ord(ch)
    for lo, hi in EMOJI_RANGES:
        if lo <= o <= hi:
            return True
    return False


def _is_latin(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    if 0x41 <= o <= 0x5A or 0x61 <= o <= 0x7A:
        return True
    return 0x00C0 <= o <= 0x024F and ch.isalpha()


def _is_digit(ch: str) -> bool:
    return ch.isdigit() and ord(ch) < 128


# --------------------------------------------------------------------------- #
# 数字 -> 读法
# --------------------------------------------------------------------------- #

def _cn_below_10000(n: int) -> str:
    digits = [int(d) for d in str(n).zfill(4)]
    out = ""
    zero = False
    started = False
    for d, u in zip(digits, CN_UNITS):
        if d == 0:
            zero = True
        else:
            if zero and started:
                out += "零"
            out += CN_DIGITS[d] + u
            zero = False
            started = True
    return out


def cn_int(n: int) -> str:
    """整数转中文读法，如 10005 -> 一万零五。"""
    if n < 0:
        return "负" + cn_int(-n)
    if n == 0:
        return "零"
    if n < 10:
        return CN_DIGITS[n]
    if n < 20:
        return "十" + (CN_DIGITS[n - 10] if n > 10 else "")

    groups: List[int] = []
    x = n
    while x > 0:
        groups.append(x % 10000)
        x //= 10000

    out = ""
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        if out and g < 1000 and not out.endswith("零"):
            out += "零"
        out += _cn_below_10000(g) + CN_BIG[idx] if idx < len(CN_BIG) else str(g)
    return out


def cn_digits(text: str) -> str:
    """逐位读，用于年份 / 电话号码。"""
    return "".join(DIGIT_CN.get(c, c) for c in text if c != ",")


def en_int(n: int) -> str:
    if n < 0:
        return "minus " + en_int(-n)
    if n < 20:
        return EN_ONES[n]
    if n < 100:
        return EN_TENS[n // 10] + ((" " + EN_ONES[n % 10]) if n % 10 else "")
    if n < 1000:
        head = EN_ONES[n // 100] + " hundred"
        return head + ((" " + en_int(n % 100)) if n % 100 else "")
    for div, name in ((1_000_000_000_000, "trillion"), (1_000_000_000, "billion"),
                      (1_000_000, "million"), (1_000, "thousand")):
        if n >= div:
            head = en_int(n // div) + " " + name
            return head + ((" " + en_int(n % div)) if n % div else "")
    return str(n)


def en_digits(text: str) -> str:
    return " ".join(EN_ONES[int(c)] for c in text if c.isdigit())


def _cn_decimal(num: str) -> str:
    if "." in num:
        int_part, dec_part = num.split(".", 1)
        return cn_int(int(int_part or 0)) + "点" + cn_digits(dec_part)
    return cn_int(int(num))


def _en_decimal(num: str) -> str:
    if "." in num:
        int_part, dec_part = num.split(".", 1)
        return en_int(int(int_part or 0)) + " point " + en_digits(dec_part)
    return en_int(int(num))


# --------------------------------------------------------------------------- #
# 语境判定
# --------------------------------------------------------------------------- #

def _context_lang(text: str, start: int, end: int, window: int = 12) -> str:
    """查看数字左右最近的文字字符，判断应该按中文还是英文读。"""
    left = ""
    i = start - 1
    steps = 0
    while i >= 0 and steps < window:
        ch = text[i]
        if is_cjk(ch):
            return "cn"
        if _is_latin(ch):
            return "en"
        if not ch.isspace() and ch not in ASCII_PUNCT + CJK_PUNCT:
            steps += 1
        i -= 1
        steps += 1

    i = end
    steps = 0
    while i < len(text) and steps < window:
        ch = text[i]
        if is_cjk(ch):
            return "cn"
        if _is_latin(ch):
            return "en"
        if not ch.isspace() and ch not in ASCII_PUNCT + CJK_PUNCT:
            steps += 1
        i += 1
        steps += 1

    return left or "cn"


def _global_lang(text: str) -> str:
    """判断整段文本的主导语言，用于处理「型号/版本号」这类嵌入数字。"""
    cn = sum(1 for ch in text if is_cjk(ch))
    en = sum(1 for ch in text if _is_latin(ch))
    if cn + en == 0:
        return "cn"
    # 汉字信息密度高于拉丁字母，按 1:2 折算更贴近真实语感
    return "cn" if cn * 2 >= en else "en"


# --------------------------------------------------------------------------- #
# 各类数字模式
# --------------------------------------------------------------------------- #

_RE_TIME = re.compile(r"\b(\d{1,2})\s*[:：]\s*(\d{2})(?:\s*[:：]\s*(\d{2}))?\b")
_RE_DATE_CN = re.compile(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?")
_RE_YEAR_CN = re.compile(r"(\d{4})\s*年")
_RE_CUR_CN = re.compile(r"[¥￥]\s*(\d+(?:\.\d+)?)\s*([万亿])?")
_RE_CUR_EN = re.compile(r"\$\s*(\d+(?:,\d{3})*(?:\.\d+)?)")
_RE_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*[%％]")
_RE_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~～—]\s*(\d+(?:\.\d+)?)")
_RE_NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")


def _read_number(token: str, lang: str, embedded: bool = False) -> str:
    raw = token.replace(",", "")
    digits_only = raw.replace(".", "")
    # 长数字串（手机号、身份证、编号）逐位读
    if len(digits_only) >= 7 and "." not in raw:
        return cn_digits(raw) if lang == "cn" else en_digits(raw)
    # 紧贴字母的型号/版本号，如 F5、Python3.13、RTX4090，逐位读更自然
    if embedded:
        if lang == "cn":
            if "." in raw:
                a, b = raw.split(".", 1)
                return cn_digits(a) + "点" + cn_digits(b)
            return cn_digits(raw)
        if "." in raw:
            a, b = raw.split(".", 1)
            return en_digits(a) + " point " + en_digits(b)
        return en_digits(raw)
    if raw.endswith(".0"):
        raw = raw[:-2]
    return _cn_decimal(raw) if lang == "cn" else _en_decimal(raw)


def _replace_patterns(text: str) -> str:
    # 时间
    def _time(m: re.Match) -> str:
        h, mi, s = m.group(1), m.group(2), m.group(3)
        lang = _context_lang(text, m.start(), m.end())
        if lang == "cn":
            out = f"{cn_int(int(h))}点"
            if mi != "00":
                out += f"{cn_int(int(mi))}分"
            if s:
                out += f"{cn_int(int(s))}秒"
            return out
        out = en_int(int(h)) + " " + (("o'clock" if mi == "00" else en_int(int(mi)))
                                      if int(mi) < 60 else mi)
        return out

    text = _RE_TIME.sub(_time, text)

    # 日期（中文语境）
    def _date(m: re.Match) -> str:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        lang = _context_lang(text, m.start(), m.end())
        if lang == "en":
            return f"{EN_ONES[mo] if mo < 20 else en_int(mo)} {en_int(d)}"
        return f"{cn_digits(str(y))}年{cn_int(mo)}月{cn_int(d)}日"

    text = _RE_DATE_CN.sub(_date, text)

    # 年份
    text = _RE_YEAR_CN.sub(lambda m: cn_digits(m.group(1)) + "年", text)

    # 货币
    def _cur_cn(m: re.Match) -> str:
        val, unit = m.group(1), m.group(2) or ""
        num = _cn_decimal(val)
        return f"{num}{unit}元"

    text = _RE_CUR_CN.sub(_cur_cn, text)
    text = _RE_CUR_EN.sub(
        lambda m: _en_decimal(m.group(1).replace(",", "")) + " dollars", text)

    # 百分比
    def _pct(m: re.Match) -> str:
        lang = _context_lang(text, m.start(), m.end())
        val = m.group(1)
        return (f"百分之{_cn_decimal(val)}" if lang == "cn"
                else _en_decimal(val) + " percent")

    text = _RE_PERCENT.sub(_pct, text)

    # 区间 3-5
    def _rng(m: re.Match) -> str:
        lang = _context_lang(text, m.start(), m.end())
        a, b = m.group(1), m.group(2)
        if lang == "cn":
            return f"{_cn_decimal(a)}到{_cn_decimal(b)}"
        return f"{_en_decimal(a)} to {_en_decimal(b)}"

    text = _RE_RANGE.sub(_rng, text)

    # 普通数字
    glob = _global_lang(text)

    def _plain_num(m: re.Match) -> str:
        s, e = m.start(), m.end()
        token = m.group(0)
        prev_ch = text[s - 1] if s > 0 else ""
        next_ch = text[e] if e < len(text) else ""
        embedded = bool((prev_ch and _is_latin(prev_ch)) or (next_ch and _is_latin(next_ch)))
        lang = glob if embedded else _context_lang(text, s, e)
        out = _read_number(token, lang, embedded)
        if prev_ch and _is_latin(prev_ch) and not out.startswith(" "):
            out = " " + out
        if next_ch and _is_latin(next_ch) and not out.endswith(" "):
            out = out + " "
        return out

    text = _RE_NUM.sub(_plain_num, text)
    return text


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

@dataclass
class TextStats:
    total: int = 0
    cn_chars: int = 0
    en_letters: int = 0
    digits: int = 0
    punctuation: int = 0
    removed: List[str] = field(default_factory=list)

    @property
    def cn_ratio(self) -> float:
        s = self.cn_chars + self.en_letters
        return self.cn_chars / s if s else 0.0

    def summary(self) -> str:
        lang = "中文为主" if self.cn_ratio >= 0.5 else "英文为主"
        if self.cn_chars and self.en_letters:
            lang = "中英混合"
        return (f"{self.total} 字符 · 汉字 {self.cn_chars} · 拉丁字母 {self.en_letters} "
                f"· 数字 {self.digits} · {lang}")


def _strip_invisible(text: str, strip_emoji: bool) -> Tuple[str, List[str]]:
    removed: List[str] = []
    out = []
    for ch in text:
        o = ord(ch)
        if ch in "\n\t":
            out.append(" ")
            continue
        if o < 32 or o == 127:
            continue
        if ch.isspace():
            out.append(" ")
            continue
        if ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00ad"):
            continue
        if strip_emoji and is_emoji(ch):
            if ch not in removed:
                removed.append(ch)
            continue
        out.append(ch)
    return "".join(out), removed


def _restore_cjk_punct(text: str) -> str:
    """中文字符之间的 ASCII 标点换回全角，保证韵律自然。"""
    pairs = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；",
             "(": "（", ")": "）"}
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch not in pairs:
            continue
        if ch == "." and i + 1 < len(chars) and chars[i + 1].isdigit() \
                and i > 0 and chars[i - 1].isdigit():
            continue  # 小数点
        prev_cjk = any(is_cjk(chars[j]) for j in range(max(0, i - 2), i))
        next_cjk = any(is_cjk(chars[j]) for j in range(i + 1, min(len(chars), i + 3)))
        if prev_cjk or next_cjk:
            chars[i] = pairs[ch]
    return "".join(chars)


def _collapse_punct(text: str) -> str:
    text = re.sub(r"[。．\.]{3,}", "……", text)
    text = re.sub(r"…{3,}", "……", text)
    text = re.sub(r"[，,]{2,}", "，", text)
    text = re.sub(r"([！？!?]){2,}", r"\1", text)
    text = re.sub(r"[、，]{2,}", "、", text)
    text = re.sub(r"^[\s，。、；：,.;:]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _space_around_latin(text: str) -> str:
    def _f(m: re.Match) -> str:
        return f"{m.group(1)} {m.group(2)}"

    for _ in range(2):
        text = re.sub(r"([\u3400-\u9fff])([A-Za-z0-9])", _f, text)
        text = re.sub(r"([A-Za-z0-9])([\u3400-\u9fff])", _f, text)
    return text


def _clean_symbols(text: str) -> str:
    """摄氏度 / 运算符 / 连接符等转成可朗读文字。"""
    text = text.replace("℃", "摄氏度").replace("°C", "摄氏度").replace("°F", "华氏度")
    cn = _global_lang(text) == "cn"
    ops = {
        "=": (" 等于 ", " equals "),
        "&": (" 和 ", " and "),
        "@": (" 艾特 ", " at "),
        "+": (" 加 ", " plus "),
    }
    for sym, (zh, en) in ops.items():
        if sym in text:
            text = text.replace(sym, zh if cn else en)
    return text


def normalize(
    text: str,
    *,
    use_cn_numbers: bool = True,
    strip_emoji: bool = True,
    add_spaces: bool = True,
    lang: str = "auto",
) -> str:
    """把任意文本规范成适合语音合成的字符串。"""
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text, _ = _strip_invisible(text, strip_emoji)
    text = _clean_symbols(text)

    if strip_emoji:
        sym = SYMBOL_MAP_CN
        text = "".join(sym.get(c, c) for c in text)
    else:
        for c in list(SYMBOL_MAP_CN):
            text = text.replace(c, SYMBOL_MAP_CN[c])

    if use_cn_numbers:
        text = _replace_patterns(text)

    text = _restore_cjk_punct(text)
    text = _collapse_punct(text)
    if add_spaces:
        text = _space_around_latin(text)
    # 汉字之间的空格无意义，去掉；标点前的空格一并清理
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"\s+([，。！？；：、）】》”’])", r"\1", text)
    text = re.sub(r"([（【《“‘])\s+", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    # 最终字符过滤：只保留已知可读字符类
    kept: List[str] = []
    for ch in text:
        if ch in "\n " or is_cjk(ch) or _is_latin(ch) or _is_digit(ch):
            kept.append(ch)
        elif ch in CJK_PUNCT or ch in ASCII_PUNCT:
            kept.append(ch)
        elif unicodedata.category(ch).startswith("L"):
            kept.append(ch)   # 其它语言的字母（希腊、西里尔等）保留
        elif unicodedata.category(ch).startswith("P"):
            kept.append(ch)
        # 其余（符号、装饰、数学）丢弃
    text = "".join(kept)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return text


def analyze(text: str) -> TextStats:
    stats = TextStats(total=len(text))
    for ch in text:
        if is_cjk(ch):
            stats.cn_chars += 1
        elif _is_latin(ch):
            stats.en_letters += 1
        elif _is_digit(ch):
            stats.digits += 1
        elif ch in CJK_PUNCT or ch in ASCII_PUNCT or unicodedata.category(ch).startswith("P"):
            stats.punctuation += 1
    return stats


def unsupported_chars(text: str) -> List[str]:
    """返回规范化后仍可能读不出的字符（非中英文字符）。"""
    bad: List[str] = []
    for ch in text:
        if ch.isspace() or is_cjk(ch) or _is_latin(ch) or _is_digit(ch):
            continue
        if ch in CJK_PUNCT or ch in ASCII_PUNCT:
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P"):
            continue
        if ch not in bad:
            bad.append(ch)
    return bad


def detect_language(text: str) -> str:
    stats = analyze(text)
    if stats.cn_chars == 0:
        return "en"
    if stats.en_letters == 0:
        return "zh"
    return "mix"
