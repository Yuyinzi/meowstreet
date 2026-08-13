_JSON_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

_INVALID_ESCAPE = object()

_SCAN = "scan"
_READ_KEY = "read_key"
_AFTER_KEY = "after_key"
_READ_VALUE = "read_value"
_SKIP_STRING = "skip_string"

_ANSWER_TEXT_KEY = "answer_text"


class AnswerTextStreamExtractor:
    def __init__(self):
        self._raw = ""
        self._pos = 0
        self._stack = []
        self._last = None
        self._state = _SCAN
        self._pending_key = []
        self._expect_answer_text_value = False
        self._answer_text_found = False
        self._answer_text_closed = False
        self._duplicate_found = False
        self._invalid_escape = False

    def feed(self, delta):
        if not isinstance(delta, str):
            raise ValueError("answer text delta is required")
        if not delta:
            return ""
        self._raw += delta
        return self._scan()

    def finish(self):
        if self._duplicate_found:
            raise ValueError("duplicate top-level answer_text")
        if self._invalid_escape:
            raise ValueError("invalid escape")
        if not self._answer_text_found:
            raise ValueError("answer_text missing")
        if not self._answer_text_closed:
            raise ValueError("answer_text string incomplete")

    def _scan(self):
        emitted = []
        while self._pos < len(self._raw):
            if self._state == _SCAN:
                made_progress = self._scan_char()
            elif self._state == _READ_KEY:
                made_progress = self._read_key_char()
            elif self._state == _AFTER_KEY:
                made_progress = self._after_key_char()
            elif self._state == _READ_VALUE:
                made_progress = self._read_value_char(emitted)
            else:
                made_progress = self._skip_string_char()
            if not made_progress:
                break
        return "".join(emitted)

    def _scan_char(self):
        ch = self._raw[self._pos]
        if ch == '"':
            if self._last in ("open", "comma") and self._stack and self._stack[-1]:
                self._pos += 1
                if len(self._stack) == 1:
                    self._state = _READ_KEY
                    self._pending_key = []
                else:
                    self._state = _SKIP_STRING
                return True
            if self._expect_answer_text_value:
                self._expect_answer_text_value = False
                self._state = _READ_VALUE
                self._pos += 1
                return True
            self._state = _SKIP_STRING
            self._pos += 1
            return True
        if ch == "{":
            self._expect_answer_text_value = False
            self._stack.append(True)
            self._last = "open"
            self._pos += 1
            return True
        if ch == "[":
            self._expect_answer_text_value = False
            self._stack.append(False)
            self._last = "open"
            self._pos += 1
            return True
        if ch == "}":
            self._expect_answer_text_value = False
            if self._stack:
                self._stack.pop()
            self._last = "value"
            self._pos += 1
            return True
        if ch == "]":
            self._expect_answer_text_value = False
            if self._stack:
                self._stack.pop()
            self._last = "value"
            self._pos += 1
            return True
        if ch == ",":
            self._last = "comma"
            self._pos += 1
            return True
        if ch == ":":
            self._last = "colon"
            self._pos += 1
            return True
        if ch.isspace():
            self._pos += 1
            return True
        self._expect_answer_text_value = False
        self._pos += 1
        return True

    def _read_key_char(self):
        ch = self._raw[self._pos]
        if ch == '"':
            key = "".join(self._pending_key)
            self._pos += 1
            if key == _ANSWER_TEXT_KEY:
                if self._answer_text_found:
                    self._duplicate_found = True
                else:
                    self._answer_text_found = True
                    self._expect_answer_text_value = True
            self._state = _AFTER_KEY
            return True
        if ch == "\\":
            result = self._read_escape(self._pos)
            if result is None:
                return False
            decoded, self._pos = result
            if decoded is _INVALID_ESCAPE:
                self._pending_key.append("\\")
            else:
                self._pending_key.append(decoded)
            return True
        self._pending_key.append(ch)
        self._pos += 1
        return True

    def _after_key_char(self):
        ch = self._raw[self._pos]
        if ch.isspace():
            self._pos += 1
            return True
        if ch == ":":
            self._last = "colon"
            self._state = _SCAN
            self._pos += 1
            return True
        self._state = _SCAN
        self._last = "colon"
        return True

    def _read_value_char(self, emitted):
        ch = self._raw[self._pos]
        if ch == '"':
            self._answer_text_closed = True
            self._state = _SCAN
            self._last = "value"
            self._pos += 1
            return True
        if ch == "\\":
            result = self._read_escape(self._pos)
            if result is None:
                return False
            decoded, self._pos = result
            if decoded is _INVALID_ESCAPE:
                self._invalid_escape = True
            else:
                emitted.append(decoded)
            return True
        emitted.append(ch)
        self._pos += 1
        return True

    def _skip_string_char(self):
        ch = self._raw[self._pos]
        if ch == '"':
            self._state = _SCAN
            self._last = "value"
            self._pos += 1
            return True
        if ch == "\\":
            result = self._read_escape(self._pos)
            if result is None:
                return False
            _, self._pos = result
            return True
        self._pos += 1
        return True

    def _read_escape(self, pos):
        if pos + 1 >= len(self._raw):
            return None
        code = self._raw[pos + 1]
        if code == "u":
            if pos + 6 > len(self._raw):
                return None
            hex_chars = self._raw[pos + 2 : pos + 6]
            if any(digit not in _HEX_DIGITS for digit in hex_chars):
                return _INVALID_ESCAPE, pos + 6
            value = int(hex_chars, 16)
            if 0xD800 <= value <= 0xDBFF:
                return self._read_surrogate_pair(pos, value)
            if 0xDC00 <= value <= 0xDFFF:
                return _INVALID_ESCAPE, pos + 6
            return chr(value), pos + 6
        decoded = _JSON_ESCAPES.get(code)
        if decoded is None:
            return _INVALID_ESCAPE, pos + 2
        return decoded, pos + 2

    def _read_surrogate_pair(self, pos, high_value):
        low_start = pos + 6
        if low_start >= len(self._raw):
            return None
        if self._raw[low_start : low_start + 2] != "\\u":
            return _INVALID_ESCAPE, pos + 6
        if low_start + 6 > len(self._raw):
            return None
        low_hex = self._raw[low_start + 2 : low_start + 6]
        if any(digit not in _HEX_DIGITS for digit in low_hex):
            return _INVALID_ESCAPE, pos + 6
        low_value = int(low_hex, 16)
        if not 0xDC00 <= low_value <= 0xDFFF:
            return _INVALID_ESCAPE, pos + 6
        combined = 0x10000 + ((high_value - 0xD800) << 10) + (low_value - 0xDC00)
        return chr(combined), low_start + 6
