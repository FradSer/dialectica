"""Ten transparent authored Python bug fixtures, NOT claimed historical bugs.

Each fixture includes a known broken implementation, executable regression tests,
and a reference fix used ONLY by the offline smoke adapter. Live agents receive
neither the reference fix nor this module in their workspace.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BugFixture:
    id: str
    description: str
    broken: str
    fixed: str
    assertions: str
    provenance: str = "authored reproducible fixture; not a historical repository bug"


FIXTURES = [
    BugFixture(
        "inclusive-range",
        "Include both ends of a numeric range.",
        "def values(a, b):\n    return list(range(a, b))\n",
        "def values(a, b):\n    return list(range(a, b + 1))\n",
        "assert values(1, 3) == [1, 2, 3]\nassert values(2, 2) == [2]\nassert values(3, 1) == []",
    ),
    BugFixture(
        "mutable-default",
        "Each omitted output list must be independent.",
        "def append(value, output=[]):\n    output.append(value)\n    return output\n",
        "def append(value, output=None):\n    if output is None:\n        output = []\n    output.append(value)\n    return output\n",
        "assert append(1) == [1]\nassert append(2) == [2]\nx = []\nassert append(3, x) is x\nassert x == [3]",
    ),
    BugFixture(
        "empty-mean",
        "Return None for an empty mean, preserving a zero mean.",
        "def mean(xs):\n    return sum(xs) / len(xs)\n",
        "def mean(xs):\n    return sum(xs) / len(xs) if xs else None\n",
        "assert mean([]) is None\nassert mean([-1, 1]) == 0\nassert mean([2, 4]) == 3",
    ),
    BugFixture(
        "zero-setting",
        "Preserve explicit zero and False settings.",
        "def setting(config, key, default):\n    return config.get(key) or default\n",
        "def setting(config, key, default):\n    return config.get(key, default)\n",
        "assert setting({'x': 0}, 'x', 3) == 0\nassert setting({'x': False}, 'x', True) is False\nassert setting({}, 'x', 3) == 3",
    ),
    BugFixture(
        "unicode-key",
        "Canonical equivalents must produce the same casefolded key.",
        "def key(text):\n    return text.lower()\n",
        "import unicodedata\ndef key(text):\n    return unicodedata.normalize('NFC', text).casefold()\n",
        "assert key('Cafe\\u0301') == key('Caf\\u00e9')\nassert key('Straße') == key('STRASSE')",
    ),
    BugFixture(
        "numeric-sort",
        "Sort decimal integer strings by numeric value.",
        "def sort_numbers(xs):\n    return sorted(xs)\n",
        "def sort_numbers(xs):\n    return sorted(xs, key=int)\n",
        "assert sort_numbers(['10', '2', '-1']) == ['-1', '2', '10']\nassert sort_numbers([]) == []",
    ),
    BugFixture(
        "file-suffix",
        "Use the last suffix, without a dot; support dotted directories.",
        "def extension(path):\n    return path.split('.')[1]\n",
        "from pathlib import PurePath\ndef extension(path):\n    return PurePath(path).suffix.lstrip('.')\n",
        "assert extension('a.tar.gz') == 'gz'\nassert extension('dir.v1/file') == ''\nassert extension('a.txt') == 'txt'",
    ),
    BugFixture(
        "century-leap",
        "Apply the Gregorian century exception.",
        "def leap(year):\n    return year % 4 == 0\n",
        "def leap(year):\n    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)\n",
        "assert not leap(1900)\nassert leap(2000)\nassert leap(2024)\nassert not leap(2023)",
    ),
    BugFixture(
        "remove-during-iteration",
        "Remove negative dictionary values in place.",
        "def remove_negative(data):\n    for key, value in data.items():\n        if value < 0:\n            del data[key]\n    return data\n",
        "def remove_negative(data):\n    for key, value in list(data.items()):\n        if value < 0:\n            del data[key]\n    return data\n",
        "x = {'a': -1, 'b': 0, 'c': -2}\nassert remove_negative(x) is x\nassert x == {'b': 0}",
    ),
    BugFixture(
        "binary-search-edge",
        "Return an index for any present target or -1 if absent.",
        "def search(xs, target):\n    lo, hi = 0, len(xs) - 1\n    while lo < hi:\n        mid = (lo + hi) // 2\n        if xs[mid] == target:\n            return mid\n        if xs[mid] < target:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return -1\n",
        "def search(xs, target):\n    lo, hi = 0, len(xs) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if xs[mid] == target:\n            return mid\n        if xs[mid] < target:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return -1\n",
        "assert search([1], 1) == 0\nassert search([1, 3, 5], 5) == 2\nassert search([], 1) == -1\nassert search([1, 3, 5], 2) == -1",
    ),
]
