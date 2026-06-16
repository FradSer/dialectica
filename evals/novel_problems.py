"""Novel, uncontaminated code-generation benchmark.

Every problem is an original invented specification with several interacting
custom rules, written for the "fails-but-fixable" band: a strong model may slip
on a rule interaction or edge case on the first pass, but can fix it once a
failing assert is shown. Nothing here is copied from HumanEval / LeetCode /
MBPP / competitive-programming archives — the scenarios and rule sets are made
up so the answer cannot be memorized and must be reasoned from the spec.

Tests are assert-based and self-contained: they reference only the target
function and run in a subprocess via ``python -c "<code>\n\n<tests>"`` (see
``evals/code_eval.py``). Reference solutions live in ``novel_solutions.py``.
"""

from evals.code_problems import CodeProblem

NOVEL_PROBLEMS = [
    CodeProblem(
        id="glyph-checksum",
        entry_point="glyph_checksum",
        prompt='''def glyph_checksum(code: str) -> int:
    """Compute the checksum of a glyph code using these rules, applied to each
    character in order (index starts at 0):

    1. Non-alphabetic characters are skipped entirely (they contribute 0 and do
       NOT advance any vowel/case logic).
    2. For an alphabetic character, start with its base value: a/A=1, b/B=2, ...
       z/Z=26 (case-insensitive for the base).
    3. If the letter is a vowel (a, e, i, o, u), double the base value. Apply
       this BEFORE the steps below.
    4. If the character is at an ODD index in the original string, add 3.
    5. If the character is uppercase, square the running value for this
       character (after steps 2-4).
    6. Sum every character's value, then return the sum modulo 1000.

    >>> glyph_checksum("a")
    2
    >>> glyph_checksum("aA")
    27
    """
''',
        tests="""assert glyph_checksum("") == 0
assert glyph_checksum("a") == 2
assert glyph_checksum("b") == 2
assert glyph_checksum("ab") == 2 + (2 + 3)
assert glyph_checksum("aA") == 2 + ((2 + 3) ** 2)
assert glyph_checksum("A") == 4
assert glyph_checksum("E") == 100
assert glyph_checksum("a1b") == 2 + 2
assert glyph_checksum("zzz") == 26 + (26 + 3) + 26
assert glyph_checksum("Hi") == (8 ** 2) + ((9 * 2) + 3)
""",
    ),
    CodeProblem(
        id="tide-windows",
        entry_point="tide_windows",
        prompt='''def tide_windows(levels: list[int], threshold: int) -> list[tuple[int, int]]:
    """Given a list of integer tide levels indexed by hour, find every maximal
    run of consecutive hours whose level is at or above the threshold, but only
    report runs that last at least 2 hours.

    Return a list of (start_index, end_index) inclusive tuples, in order. A run
    of length 1 (a single hour at/above threshold surrounded by lower hours) is
    NOT reported. Runs must be maximal (cannot be extended on either side).

    >>> tide_windows([1, 3, 3, 1, 4, 4, 4], 3)
    [(1, 2), (4, 6)]
    >>> tide_windows([5, 1, 5], 3)
    []
    """
''',
        tests="""assert tide_windows([], 3) == []
assert tide_windows([1, 3, 3, 1, 4, 4, 4], 3) == [(1, 2), (4, 6)]
assert tide_windows([5, 1, 5], 3) == []
assert tide_windows([3, 3], 3) == [(0, 1)]
assert tide_windows([3, 3, 3], 3) == [(0, 2)]
assert tide_windows([2, 2, 2], 3) == []
assert tide_windows([4, 4, 1, 4], 4) == [(0, 1)]
assert tide_windows([4, 4, 1, 4, 4], 4) == [(0, 1), (3, 4)]
assert tide_windows([3, 3, 3], 4) == []
""",
    ),
    CodeProblem(
        id="lumen-id",
        entry_point="lumen_id",
        prompt='''def lumen_id(code: str) -> bool:
    """Validate a Lumen ID string. A valid Lumen ID has the exact form
    "LL-DDDDDC" where:

    - It is exactly 9 characters long.
    - Characters 0-1 are uppercase letters (A-Z). Call them L1, L2.
    - Character 2 is a literal hyphen '-'.
    - Characters 3-7 are digits (0-9). Call their integer values d1..d5.
    - Character 8 is a single uppercase check letter.

    The check letter is computed as: let S = d1 + d2 + d3 + d4 + d5 + position(L1)
    + position(L2), where position(A)=1, position(B)=2, ..., position(Z)=26.
    The check letter must equal chr(ord('A') + (S mod 26)).

    Return True only if every rule holds, else False.

    >>> lumen_id("AB-00000C")
    False
    >>> lumen_id("AA-00000C")
    True
    """
''',
        tests="""assert lumen_id("AA-00000C") is True
assert lumen_id("AB-00000C") is False
assert lumen_id("AB-00000D") is True
assert lumen_id("aa-00000C") is False
assert lumen_id("AA-0000C") is False
assert lumen_id("AA-00000c") is False
assert lumen_id("A1-00000C") is False
assert lumen_id("AA000000C") is False
assert lumen_id("ZZ-99999A") is False
assert lumen_id("AA-00001D") is True
assert lumen_id("AB-00001E") is True
""",
    ),
    CodeProblem(
        id="spiral-fold",
        entry_point="spiral_fold",
        prompt='''def spiral_fold(text: str, width: int) -> list[str]:
    """Lay out a string into rows of the given width (the last row may be
    shorter), then reverse every odd-numbered row (0-indexed), boustrophedon
    style.

    Concretely: split the text into consecutive chunks of length `width` in
    order. Row 0 stays as-is, row 1 is reversed, row 2 as-is, row 3 reversed,
    and so on. Return the list of resulting row strings.

    >>> spiral_fold("abcdef", 3)
    ['abc', 'fed']
    >>> spiral_fold("abcdefg", 3)
    ['abc', 'fed', 'g']
    """
''',
        tests="""assert spiral_fold("abcdef", 3) == ["abc", "fed"]
assert spiral_fold("abcdefg", 3) == ["abc", "fed", "g"]
assert spiral_fold("", 3) == []
assert spiral_fold("ab", 5) == ["ab"]
assert spiral_fold("abcdefghij", 2) == ["ab", "dc", "ef", "hg", "ij"]
assert spiral_fold("x", 1) == ["x"]
assert spiral_fold("xy", 1) == ["x", "y"]
assert spiral_fold("xyz", 1) == ["x", "y", "z"]
""",
    ),
    CodeProblem(
        id="festival-seats",
        entry_point="festival_seats",
        prompt='''def festival_seats(requests: list[tuple[int, int]], capacity: int) -> int:
    """Seat groups in a single row of `capacity` seats (indices 0..capacity-1).
    Each request is (group_size, is_vip) where is_vip is 1 or 0.

    Process requests in this priority order: all VIP requests (is_vip == 1)
    before all non-VIP, and within the same VIP class in order of increasing
    group_size; ties keep their original input order.

    For each request, seat the group only if there exists a block of
    `group_size` consecutive currently-empty seats; place the group in the
    LEFTMOST such block (filling those seats). If no such block exists, skip the
    request — EXCEPT if a VIP request cannot be seated, immediately abort and
    return -1.

    Return the total number of people successfully seated.

    >>> festival_seats([(2, 0), (1, 1)], 3)
    3
    >>> festival_seats([(5, 1)], 3)
    -1
    """
''',
        tests="""assert festival_seats([], 5) == 0
assert festival_seats([(2, 0), (1, 1)], 3) == 3
assert festival_seats([(5, 1)], 3) == -1
assert festival_seats([(3, 0), (2, 0)], 4) == 2
assert festival_seats([(1, 0), (1, 0), (1, 0)], 2) == 2
assert festival_seats([(2, 1), (2, 1)], 4) == 4
assert festival_seats([(2, 0), (2, 1)], 3) == 2
assert festival_seats([(1, 0), (2, 1)], 3) == 3
""",
    ),
    CodeProblem(
        id="rune-decay",
        entry_point="rune_decay",
        prompt='''def rune_decay(runes: str) -> str:
    """A rune string decays by repeatedly removing adjacent equal pairs until no
    adjacent equal characters remain anywhere.

    Scan left to right; whenever two adjacent characters are equal, both are
    removed. Removals can cause new adjacencies, so keep applying the rule until
    the string is stable. This is the classic "cancel adjacent duplicates"
    collapse, fully resolved.

    >>> rune_decay("abba")
    ''
    >>> rune_decay("abccba")
    ''
    >>> rune_decay("aabxx")
    'b'
    """
''',
        tests="""assert rune_decay("") == ""
assert rune_decay("abba") == ""
assert rune_decay("abccba") == ""
assert rune_decay("aabxx") == "b"
assert rune_decay("abc") == "abc"
assert rune_decay("aa") == ""
assert rune_decay("aaa") == "a"
assert rune_decay("mississippi") == "m"
assert rune_decay("aabccba") == "a"
""",
    ),
    CodeProblem(
        id="ledger-balance",
        entry_point="ledger_balance",
        prompt='''def ledger_balance(entries: list[str]) -> int:
    """Compute a running balance from ledger entries starting at 0. Each entry
    is a string like "+50" or "-20": a sign ('+' or '-') followed by a
    non-negative integer amount.

    Rule: a withdrawal ('-') incurs a penalty if it is the 3rd or later
    withdrawal in an UNINTERRUPTED streak of withdrawals. The 1st and 2nd
    consecutive withdrawals are normal; from the 3rd consecutive withdrawal
    onward, the withdrawn amount is DOUBLED before subtracting. Any deposit
    ('+') resets the streak counter to zero. Deposits are never penalized.

    Return the final balance.

    >>> ledger_balance(["+100", "-10", "-10", "-10"])
    60
    >>> ledger_balance(["-5", "+5", "-5"])
    -5
    """
''',
        tests="""assert ledger_balance([]) == 0
assert ledger_balance(["+100"]) == 100
assert ledger_balance(["+100", "-10", "-10", "-10"]) == 60
assert ledger_balance(["-5", "+5", "-5"]) == -5
assert ledger_balance(["-10", "-10", "-10"]) == -40
assert ledger_balance(["-10", "-10", "-10", "-10"]) == -60
assert ledger_balance(["-10", "-10", "+1", "-10", "-10"]) == -39
assert ledger_balance(["+0", "-0", "-0", "-0"]) == 0
""",
    ),
    CodeProblem(
        id="echo-compress",
        entry_point="echo_compress",
        prompt='''def echo_compress(s: str) -> str:
    """Compress a string using a custom run-length scheme:

    - A run of length 1 is written as the single character.
    - A run of length 2 or 3 is written out literally (the repeated characters,
      no number).
    - A run of length 4 or more is written as the character immediately
      followed by the run length as a decimal number (e.g. 5 'a's -> "a5").

    Process runs left to right and concatenate the encodings. The input
    contains no digits.

    >>> echo_compress("aaaa")
    'a4'
    >>> echo_compress("aaabbc")
    'aaabbc'
    >>> echo_compress("aaaab")
    'a4b'
    """
''',
        tests="""assert echo_compress("") == ""
assert echo_compress("a") == "a"
assert echo_compress("aa") == "aa"
assert echo_compress("aaa") == "aaa"
assert echo_compress("aaaa") == "a4"
assert echo_compress("aaaaa") == "a5"
assert echo_compress("aaabbc") == "aaabbc"
assert echo_compress("aaaab") == "a4b"
assert echo_compress("aaaaaaaaaa") == "a10"
assert echo_compress("abc") == "abc"
assert echo_compress("aabbbbcc") == "aab4cc"
""",
    ),
    CodeProblem(
        id="warden-patrol",
        entry_point="warden_patrol",
        prompt='''def warden_patrol(moves: str) -> tuple[int, int]:
    """Simulate a warden on an infinite grid starting at (0, 0) facing North.
    Directions: North = +y, East = +x, South = -y, West = -x.

    Process each command character:
    - 'F': step one unit forward in the current facing.
    - 'J': jump two units forward in the current facing (one move, distance 2).
    - 'R': turn right 90 degrees (do not move).
    - 'L': turn left 90 degrees (do not move).

    Any other character is ignored (no move, no turn). Return the final (x, y).

    >>> warden_patrol("FF")
    (0, 2)
    >>> warden_patrol("FRF")
    (1, 1)
    >>> warden_patrol("J")
    (0, 2)
    """
''',
        tests="""assert warden_patrol("") == (0, 0)
assert warden_patrol("FF") == (0, 2)
assert warden_patrol("FRF") == (1, 1)
assert warden_patrol("J") == (0, 2)
assert warden_patrol("RJ") == (2, 0)
assert warden_patrol("LF") == (-1, 0)
assert warden_patrol("RRFF") == (0, -2)
assert warden_patrol("FxF") == (0, 2)
assert warden_patrol("RRRRF") == (0, 1)
assert warden_patrol("LLLLJ") == (0, 2)
""",
    ),
    CodeProblem(
        id="token-bucket",
        entry_point="token_bucket",
        prompt='''def token_bucket(events: list[tuple[int, int]], capacity: int, refill: int) -> list[bool]:
    """Simulate a token-bucket rate limiter. The bucket starts full with
    `capacity` tokens. Each event is (timestamp, cost), given in non-decreasing
    timestamp order; timestamps start counting from 0.

    Before processing an event at time t: refill the bucket by
    (t - last_time) * refill tokens, capped at `capacity` (never exceed it).
    last_time starts at 0. Then, if the bucket has at least `cost` tokens,
    consume `cost` tokens and the event is allowed (True); otherwise the event
    is rejected (False) and NO tokens are consumed. Update last_time to t
    regardless.

    Return the list of booleans, one per event.

    >>> token_bucket([(0, 2), (0, 1)], 2, 1)
    [True, False]
    >>> token_bucket([(0, 2), (2, 2)], 2, 1)
    [True, True]
    """
''',
        tests="""assert token_bucket([], 5, 1) == []
assert token_bucket([(0, 2), (0, 1)], 2, 1) == [True, False]
assert token_bucket([(0, 2), (2, 2)], 2, 1) == [True, True]
assert token_bucket([(0, 1), (1, 1), (2, 1)], 1, 1) == [True, True, True]
assert token_bucket([(0, 1), (0, 1), (0, 1)], 2, 1) == [True, True, False]
assert token_bucket([(0, 3)], 2, 1) == [False]
assert token_bucket([(0, 2), (10, 2)], 2, 1) == [True, True]
assert token_bucket([(0, 0)], 0, 0) == [True]
""",
    ),
    CodeProblem(
        id="harvest-yield",
        entry_point="harvest_yield",
        prompt='''def harvest_yield(plots: list[int]) -> int:
    """You harvest a row of plots, each with a (possibly negative) yield. You
    may NOT harvest two adjacent plots in the same pass. Choose a subset of
    non-adjacent plots that maximizes the total yield.

    Picking a plot is optional, so you can always achieve at least 0 by picking
    nothing. Return the maximum achievable total (>= 0).

    >>> harvest_yield([3, 2, 5, 10, 7])
    15
    >>> harvest_yield([-1, -2, -3])
    0
    """
''',
        tests="""assert harvest_yield([]) == 0
assert harvest_yield([5]) == 5
assert harvest_yield([-5]) == 0
assert harvest_yield([3, 2, 5, 10, 7]) == 15
assert harvest_yield([-1, -2, -3]) == 0
assert harvest_yield([2, 1, 4, 9]) == 11
assert harvest_yield([5, 5, 10, 100, 10, 5]) == 110
assert harvest_yield([1, 20, 3]) == 20
assert harvest_yield([10, -5, 10]) == 20
""",
    ),
    CodeProblem(
        id="cipher-shift",
        entry_point="cipher_shift",
        prompt='''def cipher_shift(text: str, key: str) -> str:
    """Encrypt text with a repeating-key Caesar shift, but the key only advances
    on letters.

    For each character of `text`: if it is a letter, shift it forward in the
    alphabet by an amount equal to the position of the current key letter
    (a/A -> 0, b/B -> 1, ..., z/Z -> 25), wrapping within its case (uppercase
    stays uppercase, lowercase stays lowercase), then advance to the next key
    letter (the key repeats cyclically). If the character is NOT a letter, copy
    it unchanged and do NOT advance the key.

    The key consists of letters only and is non-empty.

    >>> cipher_shift("abc", "b")
    'bcd'
    >>> cipher_shift("a b", "bc")
    'b d'
    """
''',
        tests="""assert cipher_shift("abc", "a") == "abc"
assert cipher_shift("abc", "b") == "bcd"
assert cipher_shift("a b", "bc") == "b d"
assert cipher_shift("xyz", "b") == "yza"
assert cipher_shift("Hello, World!", "a") == "Hello, World!"
assert cipher_shift("AAAA", "abc") == "ABCA"
assert cipher_shift("a-a-a", "bcd") == "b-c-d"
assert cipher_shift("Zz", "b") == "Aa"
""",
    ),
    CodeProblem(
        id="snake-path",
        entry_point="snake_path",
        prompt='''def snake_path(n: int) -> list[list[int]]:
    """Build an n x n grid (list of n rows, each a list of n ints) filled with
    1..n*n in a column-wise boustrophedon (snake) order:

    - Fill column 0 top to bottom with 1, 2, ..., n.
    - Fill column 1 bottom to top with n+1, ..., 2n.
    - Fill column 2 top to bottom, column 3 bottom to top, and so on.

    Return the grid as rows.

    >>> snake_path(1)
    [[1]]
    >>> snake_path(2)
    [[1, 4], [2, 3]]
    """
''',
        tests="""assert snake_path(1) == [[1]]
assert snake_path(2) == [[1, 4], [2, 3]]
assert snake_path(3) == [[1, 6, 7], [2, 5, 8], [3, 4, 9]]
assert snake_path(4) == [
    [1, 8, 9, 16],
    [2, 7, 10, 15],
    [3, 6, 11, 14],
    [4, 5, 12, 13],
]
res = snake_path(5)
assert len(res) == 5 and all(len(r) == 5 for r in res)
assert sorted(v for row in res for v in row) == list(range(1, 26))
assert res[0][0] == 1
""",
    ),
    CodeProblem(
        id="vote-tally",
        entry_point="vote_tally",
        prompt='''def vote_tally(ballots: list[list[str]]) -> str | None:
    """Run a ranked-choice point tally. Each ballot is an ordered list of
    candidate names (most preferred first). Award points per ballot:

    - 1st choice: 3 points, 2nd choice: 2 points, 3rd choice: 1 point.
    - 4th choice and beyond: 0 points.
    - If a candidate appears more than once on a single ballot, only the FIRST
      (highest) occurrence counts; later duplicate occurrences are ignored
      entirely (they do not shift the ranks of candidates after them — ranks are
      determined by position among first-occurrences).

    Sum points across all ballots. Return the single candidate with the
    strictly highest total. If there is a tie for the highest total (or there
    are no candidates at all), return None.

    >>> vote_tally([["a", "b"], ["a", "c"]])
    'a'
    >>> vote_tally([["a"], ["b"]])
    """
''',
        tests="""assert vote_tally([]) is None
assert vote_tally([["a", "b"], ["a", "c"]]) == "a"
assert vote_tally([["a"], ["b"]]) is None
assert vote_tally([["a", "b", "c"]]) == "a"
assert vote_tally([["a", "a", "b"]]) == "a"
assert vote_tally([["a", "b", "c", "d"], ["d", "a", "b", "c"]]) == "a"
assert vote_tally([["x"]]) == "x"
assert vote_tally([["a", "b"], ["b", "a"]]) is None
""",
    ),
    CodeProblem(
        id="pulse-merge",
        entry_point="pulse_merge",
        prompt='''def pulse_merge(a: list[int], b: list[int]) -> list[int]:
    """Interleave two lists, then collapse adjacent duplicates.

    First build an interleaved list: take a[0], b[0], a[1], b[1], ... strictly
    alternating and starting with `a`. When one list runs out, append all the
    remaining elements of the other list in order.

    Then collapse runs of adjacent EQUAL values in the interleaved result down
    to a single value (keep the first of each run). Return the collapsed list.

    >>> pulse_merge([1, 4, 2], [4, 2, 5])
    [1, 4, 2, 5]
    >>> pulse_merge([1, 1], [1])
    [1]
    """
''',
        tests="""assert pulse_merge([], []) == []
assert pulse_merge([1, 4, 2], [4, 2, 5]) == [1, 4, 2, 5]
assert pulse_merge([1, 2, 3], [1, 2, 3]) == [1, 2, 3]
assert pulse_merge([1, 1], [1]) == [1]
assert pulse_merge([1], []) == [1]
assert pulse_merge([], [5, 5, 6]) == [5, 6]
assert pulse_merge([1, 2], [3, 4, 5, 6]) == [1, 3, 2, 4, 5, 6]
assert pulse_merge([7, 7, 7], [7]) == [7]
assert pulse_merge([1, 3], [2, 4]) == [1, 2, 3, 4]
""",
    ),
    CodeProblem(
        id="grade-curve",
        entry_point="grade_curve",
        prompt='''def grade_curve(scores: list[int]) -> list[str]:
    """Apply a flat curve, then assign letter grades.

    Find the highest score in the list. Add (100 - highest) to EVERY score (so
    the top score becomes exactly 100, and the gap between scores is preserved).
    Then map each adjusted score to a letter:

    - >= 90: 'A'
    - >= 80: 'B'
    - >= 70: 'C'
    - >= 60: 'D'
    - otherwise: 'F'

    Return the list of letters in the original order. An empty input returns [].

    >>> grade_curve([100, 80, 70, 60])
    ['A', 'B', 'C', 'D']
    >>> grade_curve([50])
    ['A']
    """
''',
        tests="""assert grade_curve([]) == []
assert grade_curve([100, 80, 70, 60]) == ["A", "B", "C", "D"]
assert grade_curve([90, 80, 70]) == ["A", "A", "B"]
assert grade_curve([50]) == ["A"]
assert grade_curve([100, 90, 80, 70, 60]) == ["A", "A", "B", "C", "D"]
assert grade_curve([100, 59]) == ["A", "F"]
assert grade_curve([40, 30, 20]) == ["A", "A", "B"]
assert grade_curve([85, 85]) == ["A", "A"]
assert grade_curve([100, 11, 10]) == ["A", "F", "F"]
""",
    ),
    CodeProblem(
        id="clock-angle",
        entry_point="clock_angle",
        prompt='''def clock_angle(hhmm: str) -> int:
    """Given a 24-hour time string "HH:MM", return the smaller angle in whole
    degrees between the hour hand and the minute hand of an analog clock.

    The hour hand moves continuously: it advances 30 degrees per hour PLUS 0.5
    degrees per minute. The minute hand advances 6 degrees per minute. Treat
    hours modulo 12 (so 13:00 is the same hand position as 1:00). Return the
    smaller of the two angles between the hands (i.e. <= 180), rounded to the
    nearest integer.

    >>> clock_angle("03:00")
    90
    >>> clock_angle("12:00")
    0
    """
''',
        tests="""assert clock_angle("03:00") == 90
assert clock_angle("12:00") == 0
assert clock_angle("06:00") == 180
assert clock_angle("09:00") == 90
assert clock_angle("15:00") == 90
assert clock_angle("00:00") == 0
assert clock_angle("12:30") == 165
assert clock_angle("03:15") == 8
assert clock_angle("01:00") == 30
""",
    ),
    CodeProblem(
        id="relay-race",
        entry_point="relay_race",
        prompt='''def relay_race(splits: list[list[int]]) -> int:
    """Determine the winning team index of a relay race. `splits[t]` is the list
    of leg times (positive integers) for team t.

    Compute each team's total time = sum of its leg times PLUS a penalty: for
    every leg that is SLOWER (strictly greater) than the immediately preceding
    leg of the same team, add 5 penalty seconds. (A team's first leg never
    incurs a penalty.)

    Any team that has a non-positive leg time (<= 0) is DISQUALIFIED and cannot
    win. The winner is the qualified team with the lowest total time; on a tie,
    the lower team index wins. If no team qualifies, return -1.

    >>> relay_race([[10, 10], [9, 12]])
    0
    >>> relay_race([[5, -1], [20]])
    1
    """
''',
        tests="""assert relay_race([]) == -1
assert relay_race([[10, 10], [9, 12]]) == 0
assert relay_race([[5, -1], [20]]) == 1
assert relay_race([[10], [10]]) == 0
assert relay_race([[1, 2, 3]]) == 0
assert relay_race([[3, 2, 1], [1, 2, 3]]) == 0
assert relay_race([[0]]) == -1
assert relay_race([[100], [1, 1, 1, 1]]) == 1
assert relay_race([[10, 9, 11], [10, 11, 9]]) == 0
""",
    ),
    CodeProblem(
        id="ring-rotate",
        entry_point="ring_rotate",
        prompt='''def ring_rotate(grid: list[list[int]]) -> list[list[int]]:
    """Rotate each concentric ring of a square n x n grid by one step CLOCKWISE,
    and return the new grid (do not mutate the input).

    A grid has nested rings: the outermost border is ring 0, the next border in
    is ring 1, and so on. Each ring is the sequence of cells along its border.
    "One step clockwise" means every value on a ring moves to the next cell in
    clockwise order along that ring (the value that was last wraps to the
    first). Rings rotate independently. The exact center cell of an odd-sized
    grid is a ring of one cell and is unchanged.

    >>> ring_rotate([[1, 2], [3, 4]])
    [[3, 1], [4, 2]]
    """
''',
        tests="""assert ring_rotate([[5]]) == [[5]]
assert ring_rotate([[1, 2], [3, 4]]) == [[3, 1], [4, 2]]
assert ring_rotate([[1, 2, 3], [4, 5, 6], [7, 8, 9]]) == [
    [4, 1, 2],
    [7, 5, 3],
    [8, 9, 6],
]
src = [[1, 2], [3, 4]]
ring_rotate(src)
assert src == [[1, 2], [3, 4]]
out = ring_rotate([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]])
assert out == [
    [5, 1, 2, 3],
    [9, 10, 6, 4],
    [13, 11, 7, 8],
    [14, 15, 16, 12],
]
""",
    ),
    CodeProblem(
        id="bracket-depth-sum",
        entry_point="bracket_depth_sum",
        prompt='''def bracket_depth_sum(expr: str) -> int:
    """Given a string of single digits and balanced round brackets, return the
    sum of each digit multiplied by its nesting depth.

    Depth starts at 0. Each '(' increases the current depth by 1 (the digits
    INSIDE the parentheses are deeper); each ')' decreases it by 1. A digit's
    weight is the depth in effect at the digit's position. There are no
    multi-digit numbers — every digit is weighted independently. Characters are
    only digits, '(' and ')', and the brackets are balanced.

    >>> bracket_depth_sum("1(2)3")
    2
    >>> bracket_depth_sum("(1(2))")
    5
    """
''',
        tests="""assert bracket_depth_sum("") == 0
assert bracket_depth_sum("123") == 0
assert bracket_depth_sum("1(2)3") == 2
assert bracket_depth_sum("(1(2))") == 5
assert bracket_depth_sum("(((9)))") == 27
assert bracket_depth_sum("1(2(3)4)5") == 2 + 6 + 4
assert bracket_depth_sum("()") == 0
assert bracket_depth_sum("(0)") == 0
assert bracket_depth_sum("5(5)(5)") == 0 + 5 + 5
""",
    ),
]
