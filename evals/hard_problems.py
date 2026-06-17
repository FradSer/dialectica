"""Hard, uncontaminated code-generation benchmark.

A harder companion to ``novel_problems.py``. Every problem is an original
invented specification, calibrated above HumanEval/medium: each needs a
genuine multi-step algorithm or several interacting rules (a non-obvious DP
state, a graph traversal with a twist, careful simulation with ordering
rules, interval scheduling, intricate parsing, or a number/bit trick with
edge cases). They are solvable by a careful mid-level engineer with standard
techniques in 20-45 minutes -- no novel algorithms, proofs, or
micro-optimization -- but a fast model frequently slips on an edge case, a
missed rule interaction, or a wrong base case, so the set leaves real
pass@1 headroom for a best-of-N / repair engine to recover.

Nothing here is copied from HumanEval / LeetCode / MBPP / competitive-
programming archives; the scenarios and rule sets are invented so the answer
must be reasoned from the spec rather than recalled.

Tests are assert-based and self-contained: they reference only the target
function and run in a subprocess via ``python -c "<code>\n\n<tests>"`` (see
``evals/code_eval.py``). Reference solutions live in ``hard_solutions.py``.
"""

from evals.code_problems import CodeProblem

HARD_PROBLEMS = [
    CodeProblem(
        id="tile-fit",
        entry_point="tile_fit",
        prompt='''def tile_fit(n: int) -> int:
    """Count the ways to exactly cover a 1xn strip using tiles of length 1, 2,
    and 3, subject to one rule: no two length-1 tiles may be placed directly
    next to each other (a length-1 tile may never be immediately followed by
    another length-1 tile). Tiles of length 2 and 3 have no such restriction.
    Two tilings are different if the ordered sequence of tile lengths differs.

    An empty strip (n == 0) has exactly one tiling (place nothing). Return the
    count for the given n (n >= 0).

    >>> tile_fit(0)
    1
    >>> tile_fit(3)
    3
    """
''',
        tests="""assert tile_fit(0) == 1
assert tile_fit(1) == 1
assert tile_fit(2) == 1
assert tile_fit(3) == 3
assert tile_fit(4) == 4
assert tile_fit(5) == 6
assert tile_fit(6) == 11
assert tile_fit(10) == 72
""",
    ),
    CodeProblem(
        id="shelf-stack",
        entry_point="shelf_stack",
        prompt='''def shelf_stack(ops: list[tuple[str, int]]) -> list[int]:
    """Simulate a quirky shelf that holds labeled crates. Process `ops` in
    order; each op is (kind, value):

    - ("push", v): place crate v on top of the shelf.
    - ("pop", 0): remove the top crate (ignore if the shelf is empty).
    - ("sink", v): every crate currently on the shelf with label EXACTLY v
      drops to the very bottom of the shelf, preserving their relative order
      among themselves; all other crates keep their relative order and sit on
      top of the sunk ones. If no crate has label v, nothing happens.

    The shelf is represented bottom-to-top as a list. Return the final shelf
    (bottom first).

    >>> shelf_stack([("push", 1), ("push", 2), ("push", 1), ("sink", 1)])
    [1, 1, 2]
    >>> shelf_stack([("push", 5), ("pop", 0)])
    []
    """
''',
        tests="""assert shelf_stack([]) == []
assert shelf_stack([('push', 1), ('push', 2), ('push', 1), ('sink', 1)]) == [1, 1, 2]
assert shelf_stack([('push', 5), ('pop', 0)]) == []
assert shelf_stack([('pop', 0)]) == []
assert shelf_stack([('push', 3), ('push', 3), ('push', 4), ('sink', 9)]) == [3, 3, 4]
assert shelf_stack([('push', 1), ('push', 2), ('push', 3), ('sink', 2), ('pop', 0)]) == [2, 1]
assert shelf_stack([('push', 2), ('push', 1), ('push', 2), ('push', 1), ('sink', 2)]) == [2, 2, 1, 1]
""",
    ),
    CodeProblem(
        id="relay-tokens",
        entry_point="relay_tokens",
        prompt='''def relay_tokens(n: int, links: list[tuple[int, int, int]]) -> int:
    """Stations 0..n-1 are joined by bidirectional links. Each link is
    (a, b, cost). A courier starts at station 0 carrying a packet and must
    deliver it to station n-1, minimizing total cost.

    Travelling along a link costs its `cost`. In addition, EACH time the courier
    arrives at a station whose number is odd, a handling fee equal to that
    station's number is charged (arriving at an even station is free). The
    starting station 0 never incurs a fee even though the courier "is" there.
    Re-visiting an odd station charges the fee again each time.

    Return the minimum total cost (link costs + handling fees) to get from 0 to
    n-1, or -1 if n-1 is unreachable. There are no self-loops; there may be
    multiple links between the same pair.

    >>> relay_tokens(2, [(0, 1, 5)])
    6
    >>> relay_tokens(3, [(0, 2, 4)])
    4
    """
''',
        tests="""assert relay_tokens(2, [(0, 1, 5)]) == 6
assert relay_tokens(3, [(0, 2, 4)]) == 4
assert relay_tokens(2, []) == -1
assert relay_tokens(4, [(0, 1, 1), (1, 3, 1), (0, 2, 1), (2, 3, 1)]) == 5
assert relay_tokens(5, [(0, 1, 2), (1, 4, 2), (0, 2, 1), (2, 3, 1), (3, 4, 1)]) == 5
assert relay_tokens(3, [(0, 1, 1), (1, 2, 1)]) == 3
assert relay_tokens(6, [(0, 5, 100), (0, 2, 1), (2, 4, 1), (4, 5, 1)]) == 8
""",
    ),
    CodeProblem(
        id="ridge-water",
        entry_point="ridge_water",
        prompt='''def ridge_water(heights: list[int], max_span: int) -> int:
    """A row of vertical walls has integer `heights`. Rain fills the valleys
    between walls, but with a constraint: a contiguous valley (a maximal run of
    cells each strictly lower than some wall on its left AND some wall on its
    right) only holds water if the NUMBER of cells in that valley is at most
    `max_span`. Wider valleys drain completely and hold nothing.

    Concretely: for each cell i, let L = max height to its left (inclusive of i)
    and R = max height to its right (inclusive of i). The potential water at i
    is min(L, R) - heights[i] (>= 0). Group consecutive cells with positive
    potential water into valleys; a valley contributes its total potential water
    only if it spans at most `max_span` cells, otherwise it contributes 0.

    Return total water held.

    >>> ridge_water([3, 0, 3], 5)
    3
    >>> ridge_water([3, 0, 0, 0, 3], 2)
    0
    """
''',
        tests="""assert ridge_water([], 5) == 0
assert ridge_water([3, 0, 3], 5) == 3
assert ridge_water([3, 0, 0, 0, 3], 2) == 0
assert ridge_water([3, 0, 0, 0, 3], 3) == 9
assert ridge_water([5, 1, 2, 1, 5], 3) == 11
assert ridge_water([5, 1, 2, 1, 5], 2) == 0
assert ridge_water([2, 0, 2, 0, 2], 1) == 4
assert ridge_water([4, 2, 0, 3, 2, 5], 10) == 9
assert ridge_water([1, 2, 3, 4], 10) == 0
""",
    ),
    CodeProblem(
        id="cargo-pairs",
        entry_point="cargo_pairs",
        prompt='''def cargo_pairs(items: list[tuple[int, int]], limit: int) -> int:
    """You ship items in boxes. Each item is (weight, fragile) with fragile in
    {0, 1}. A box holds at most two items and the combined weight must be <=
    limit. Additional rule: a fragile item (fragile == 1) must travel ALONE in
    its box -- it can never share with any other item. Non-fragile items may
    pair with another non-fragile item if their weights fit.

    Every item's weight is <= limit. Return the minimum number of boxes needed
    to ship all items.

    >>> cargo_pairs([(3, 0), (4, 0)], 7)
    1
    >>> cargo_pairs([(3, 1), (4, 0)], 7)
    2
    """
''',
        tests="""assert cargo_pairs([], 7) == 0
assert cargo_pairs([(3, 0), (4, 0)], 7) == 1
assert cargo_pairs([(3, 1), (4, 0)], 7) == 2
assert cargo_pairs([(1, 0), (2, 0), (3, 0)], 3) == 2
assert cargo_pairs([(5, 1), (5, 1)], 10) == 2
assert cargo_pairs([(4, 0), (4, 0), (4, 0)], 7) == 3
assert cargo_pairs([(1, 0), (2, 0), (3, 1), (6, 0), (5, 0)], 6) == 4
assert cargo_pairs([(7, 0)], 7) == 1
""",
    ),
    CodeProblem(
        id="orchard-pick",
        entry_point="orchard_pick",
        prompt='''def orchard_pick(grid: list[list[int]]) -> int:
    """Walk from the top-left cell to the bottom-right cell of a grid of
    non-negative integers, moving only right or down one cell at a time,
    collecting the value of every cell you stand on (including the start and
    end). Twist: you may never step onto a cell whose value equals the value of
    the cell you are currently standing on -- consecutive cells on your path
    must have different values. If from some cell BOTH the right and down moves
    are blocked (or off-grid) before reaching the end, that path is dead.

    Return the maximum total you can collect over all valid paths, or -1 if no
    valid path reaches the bottom-right cell. The grid has at least one row and
    one column.

    >>> orchard_pick([[1, 2], [2, 3]])
    6
    >>> orchard_pick([[5, 5], [5, 5]])
    -1
    """
''',
        tests="""assert orchard_pick([[1, 2], [2, 3]]) == 6
assert orchard_pick([[5, 5], [5, 5]]) == -1
assert orchard_pick([[7]]) == 7
assert orchard_pick([[1, 2, 3]]) == 6
assert orchard_pick([[1], [1], [2]]) == -1
assert orchard_pick([[1, 2, 1], [2, 1, 2], [1, 2, 9]]) == 15
assert orchard_pick([[1, 1], [2, 3]]) == 6
assert orchard_pick([[3, 1, 4], [1, 5, 9], [2, 6, 5]]) == 23
""",
    ),
    CodeProblem(
        id="typo-stream",
        entry_point="typo_stream",
        prompt='''def typo_stream(s: str) -> str:
    """Reconstruct text from a keystroke stream containing two control markers,
    processed left to right:

    - '#' is a backspace: it deletes the most recent surviving output character
      (does nothing if the output is currently empty).
    - '^' arms a one-shot skip: the NEXT ordinary character (any character that
      is not '#' or '^') is swallowed and does not reach the output. Each '^'
      arms exactly one skip; two '^' in a row swallow the next two ordinary
      characters. An armed skip never affects '#' or '^' themselves -- markers
      are always processed as markers.

    Return the final reconstructed string.

    >>> typo_stream("abc#")
    'ab'
    >>> typo_stream("a^bc")
    'ac'
    """
''',
        tests="""assert typo_stream('') == ''
assert typo_stream('abc#') == 'ab'
assert typo_stream('a^bc') == 'ac'
assert typo_stream('###') == ''
assert typo_stream('ab##c') == 'c'
assert typo_stream('^^abc') == 'c'
assert typo_stream('a^#b') == ''
assert typo_stream('x^^yz#w') == 'w'
assert typo_stream('^#a') == ''
""",
    ),
    CodeProblem(
        id="lock-combo",
        entry_point="lock_combo",
        prompt='''def lock_combo(length: int) -> int:
    """Count the codes of exactly `length` digits that can be typed on this 3x3
    keypad by a token that moves like a chess ROOK between consecutive presses.
    The keypad layout (digit at row, col) is:

        1 2 3
        4 5 6
        7 8 9

    Rules:
    - The first digit may be any of 1..9.
    - Each subsequent digit must be reachable from the previous one by a single
      rook move: it must share the SAME ROW or SAME COLUMN as the previous
      digit, and must be a DIFFERENT key (you cannot stay on the same key).

    Return the number of distinct codes of the given length (length >= 1).

    >>> lock_combo(1)
    9
    >>> lock_combo(2)
    36
    """
''',
        tests="""assert lock_combo(1) == 9
assert lock_combo(2) == 36
assert lock_combo(3) == 144
assert lock_combo(4) == 576
""",
    ),
    CodeProblem(
        id="task-packer",
        entry_point="task_packer",
        prompt='''def task_packer(tasks: list[tuple[int, int, int]]) -> int:
    """Schedule jobs on a single machine to maximize collected reward. Each task
    is (start, end, reward) and occupies the half-open time interval
    [start, end); two tasks conflict if their half-open intervals overlap (a
    task ending exactly when another starts does NOT conflict). You may run any
    subset of mutually non-conflicting tasks.

    Return the maximum total reward of a non-conflicting subset. Rewards are
    non-negative. An empty list yields 0.

    >>> task_packer([(0, 2, 5), (2, 4, 6)])
    11
    >>> task_packer([(0, 4, 10), (1, 2, 4), (2, 3, 4)])
    10
    """
''',
        tests="""assert task_packer([]) == 0
assert task_packer([(0, 2, 5), (2, 4, 6)]) == 11
assert task_packer([(0, 3, 5), (1, 2, 4), (2, 5, 6)]) == 10
assert task_packer([(0, 10, 1), (1, 2, 5), (3, 4, 5), (5, 6, 5)]) == 15
assert task_packer([(0, 1, 100)]) == 100
assert task_packer([(0, 2, 3), (1, 3, 3), (2, 4, 3)]) == 6
assert task_packer([(1, 3, 20), (2, 5, 20), (4, 6, 20), (6, 7, 20)]) == 60
assert task_packer([(0, 5, 0), (0, 1, 1)]) == 1
""",
    ),
    CodeProblem(
        id="current-cost",
        entry_point="current_cost",
        prompt='''def current_cost(grid: list[list[int]]) -> int:
    """Find the minimum-cost path from the top-left cell to the bottom-right
    cell of a grid of positive integers, moving up/down/left/right (4-way).
    The cost model is unusual: stepping ONTO a cell normally costs that cell's
    value, EXCEPT when you move between two orthogonally adjacent cells that
    hold the EQUAL value -- such a step is free (costs 0). The starting cell's
    own value is always paid once at the beginning.

    Return the minimum total cost to reach the bottom-right cell. The grid has
    at least one row and one column; all cells are reachable.

    >>> current_cost([[1, 9], [1, 1]])
    1
    >>> current_cost([[5]])
    5
    """
''',
        tests="""assert current_cost([[5]]) == 5
assert current_cost([[1, 9], [1, 1]]) == 1
assert current_cost([[1, 2], [3, 4]]) == 7
assert current_cost([[1, 1, 1], [9, 9, 1], [9, 9, 1]]) == 1
assert current_cost([[2, 2, 2], [2, 9, 2], [2, 2, 2]]) == 2
assert current_cost([[1, 100], [100, 1]]) == 102
assert current_cost([[3, 3, 3, 3]]) == 3
assert current_cost([[1], [2], [3]]) == 6
""",
    ),
    CodeProblem(
        id="bit-runs",
        entry_point="bit_runs",
        prompt='''def bit_runs(n: int) -> int:
    """Given a non-negative integer n, look at its binary representation
    (without leading zeros; the binary of 0 is the single digit "0"). Find the
    length of the LONGEST run of consecutive 1-bits, then find the length of the
    longest run of consecutive 0-bits that appears strictly BETWEEN two 1-bits
    (leading/trailing zero runs do not count; for the number 0 there are no
    such interior zero runs).

    Return the product of those two lengths. If there are no interior zero runs,
    the second length is 0, so the product is 0.

    >>> bit_runs(0)
    0
    >>> bit_runs(9)
    2
    """
''',
        tests="""assert bit_runs(0) == 0
assert bit_runs(9) == 2
assert bit_runs(1) == 0
assert bit_runs(7) == 0
assert bit_runs(0b1001001) == 2
assert bit_runs(0b111000111) == 9
assert bit_runs(0b10000001) == 6
assert bit_runs(0b1011101) == 3
assert bit_runs(8) == 0
""",
    ),
    CodeProblem(
        id="queue-merge",
        entry_point="queue_merge",
        prompt='''def queue_merge(arrivals: list[tuple[int, str]]) -> list[str]:
    """Two service queues, "fast" and "slow", share one counter. Each arrival is
    (time, name) and names are processed by these rules:

    - A name is assigned to the "fast" queue if its length (number of
      characters) is <= 4, otherwise to the "slow" queue.
    - The counter serves all currently-waiting FAST customers before serving any
      SLOW customer. Within a queue, customers are served in order of arrival
      time; if two customers in the SAME queue share the same arrival time, the
      one whose name is lexicographically smaller is served first.
    - Service is instantaneous, but the queue assignment and ordering above
      fully determine the output order: list every fast customer (sorted by
      (time, name)) first, then every slow customer (sorted by (time, name)).

    Return the list of names in the order they are served.

    >>> queue_merge([(1, "Ann"), (2, "Theodore")])
    ['Ann', 'Theodore']
    >>> queue_merge([(5, "Bob"), (1, "Alexander")])
    ['Bob', 'Alexander']
    """
''',
        tests="""assert queue_merge([]) == []
assert queue_merge([(1, 'Ann'), (2, 'Theodore')]) == ['Ann', 'Theodore']
assert queue_merge([(5, 'Bob'), (1, 'Alexander')]) == ['Bob', 'Alexander']
assert queue_merge([(1, 'Bea'), (1, 'Ada'), (1, 'Cy')]) == ['Ada', 'Bea', 'Cy']
assert queue_merge([(2, 'Zoe'), (1, 'Max'), (1, 'Eve')]) == ['Eve', 'Max', 'Zoe']
assert queue_merge([(1, 'Jonathan'), (1, 'Benjamin')]) == ['Benjamin', 'Jonathan']
assert queue_merge([(3, 'Lee'), (3, 'Lee')]) == ['Lee', 'Lee']
assert queue_merge([(1, 'Anna'), (1, 'Annabelle'), (2, 'Bo')]) == ['Anna', 'Bo', 'Annabelle']
""",
    ),
    CodeProblem(
        id="word-bridge",
        entry_point="word_bridge",
        prompt='''def word_bridge(words: list[str]) -> int:
    """You are given a list of non-empty lowercase words. A "bridge" is a
    subsequence of the list (keeping the original left-to-right order) in which
    each word after the first begins with the SAME letter that the previous word
    in the bridge ended with. For example "cat" can be followed by "tap"
    because "cat" ends in 't' and "tap" starts with 't'.

    Return the length of the longest such bridge. A single word is a bridge of
    length 1, so the answer is at least 1 for a non-empty list (and 0 for an
    empty list).

    >>> word_bridge(["cat", "tap", "pin"])
    3
    >>> word_bridge(["cat", "dog", "go"])
    2
    """
''',
        tests="""assert word_bridge([]) == 0
assert word_bridge(['cat', 'tap', 'pin']) == 3
assert word_bridge(['cat', 'dog', 'go']) == 2
assert word_bridge(['a']) == 1
assert word_bridge(['ab', 'ba', 'ab', 'ba']) == 4
assert word_bridge(['xy', 'yz', 'za', 'ab', 'qq']) == 4
assert word_bridge(['ax', 'xb', 'bc', 'xy', 'yc']) == 3
assert word_bridge(['aa', 'aa', 'aa']) == 3
""",
    ),
    CodeProblem(
        id="digit-fold",
        entry_point="digit_fold",
        prompt='''def digit_fold(n: int) -> int:
    """Repeatedly "fold" a non-negative integer until a single digit remains,
    then return that digit. One fold works on the decimal digits as follows:

    - Pair up digits from the OUTSIDE IN: first with last, second with
      second-to-last, and so on. Replace each pair by the units digit of the
      SUM of the two paired digits (i.e. (a + b) mod 10). If the number has an
      odd count of digits, the middle digit is carried through unchanged.
    - The new number is formed by reading the resulting values from the OUTSIDE
      pairs inward: that is, the first pair's result is the most significant
      new digit, then the second pair's result, ..., then (if present) the
      middle digit last. Leading zeros in the new number are dropped naturally
      by treating it as an integer.

    Keep folding until the value is a single digit (0-9), and return it.

    >>> digit_fold(7)
    7
    >>> digit_fold(19)
    0
    """
''',
        tests="""assert digit_fold(7) == 7
assert digit_fold(19) == 0
assert digit_fold(123) == 6
assert digit_fold(12345) == 5
assert digit_fold(1000) == 1
assert digit_fold(99) == 8
assert digit_fold(5) == 5
assert digit_fold(91) == 0
assert digit_fold(246) == 2
""",
    ),
    CodeProblem(
        id="paint-layers",
        entry_point="paint_layers",
        prompt='''def paint_layers(strokes: list[tuple[int, int, int]]) -> int:
    """A 1-D canvas of integer cells is painted by a sequence of strokes. Each
    stroke is (left, right, color) and paints every cell in the half-open range
    [left, right) with `color`, OVERWRITING whatever was there. Strokes are
    applied in the given order (later strokes cover earlier ones). `color` is a
    positive integer; an unpainted cell has color 0.

    After all strokes, count the number of distinct maximal runs of EQUAL
    non-zero color (each maximal contiguous block of cells sharing the same
    positive color counts as one painted region; bare color-0 gaps separate
    regions and are not counted). Return that count.

    >>> paint_layers([(0, 3, 1)])
    1
    >>> paint_layers([(0, 3, 1), (1, 2, 2)])
    3
    """
''',
        tests="""assert paint_layers([]) == 0
assert paint_layers([(0, 3, 1)]) == 1
assert paint_layers([(0, 3, 1), (1, 2, 2)]) == 3
assert paint_layers([(0, 2, 1), (2, 4, 1)]) == 1
assert paint_layers([(0, 2, 1), (3, 5, 1)]) == 2
assert paint_layers([(0, 5, 1), (1, 4, 2), (2, 3, 1)]) == 5
assert paint_layers([(0, 4, 3), (0, 4, 3)]) == 1
assert paint_layers([(0, 1, 1), (1, 2, 2), (2, 3, 1)]) == 3
""",
    ),
    CodeProblem(
        id="stack-eval",
        entry_point="stack_eval",
        prompt='''def stack_eval(tokens: list[str]) -> int:
    """Run a tiny stack machine over a list of string tokens, left to right:

    - A token that is an integer literal (optionally negative, e.g. "5", "-3")
      is pushed onto the stack.
    - "+" pops the top two values (a on top, b below) and pushes b + a.
    - "-" pops two and pushes b - a.
    - "*" pops two and pushes b * a.
    - "dup" duplicates the top value (push a copy of the current top).
    - "swap" exchanges the top two values.
    - "drop" removes the top value.

    All operators are guaranteed to have enough operands when they run. After
    processing every token, return the value left on top of the stack; if the
    stack is empty at the end, return 0.

    >>> stack_eval(["2", "3", "+"])
    5
    >>> stack_eval(["5", "dup", "*"])
    25
    """
''',
        tests="""assert stack_eval([]) == 0
assert stack_eval(['2', '3', '+']) == 5
assert stack_eval(['5', 'dup', '*']) == 25
assert stack_eval(['10', '3', '-']) == 7
assert stack_eval(['1', '2', 'swap', '-']) == 1
assert stack_eval(['7', '8', 'drop']) == 7
assert stack_eval(['-3', '4', '*']) == -12
assert stack_eval(['2', '3', '4', '+', '*']) == 14
assert stack_eval(['9', 'drop']) == 0
""",
    ),
    CodeProblem(
        id="nest-check",
        entry_point="nest_check",
        prompt='''def nest_check(s: str) -> bool:
    """Validate a string of "tags". The string consists only of the characters
    '<', '>', '/', and lowercase letters. A tag is one of:

    - an OPEN tag "<x>" where x is a single lowercase letter, or
    - a CLOSE tag "</x>" where x is a single lowercase letter.

    The whole string must be a concatenation of well-formed tags that nest
    correctly, like brackets: every open tag must be closed by a matching close
    tag (same letter), in last-opened-first-closed order, with no leftover open
    tags at the end and no close tag without a matching open tag.

    Additional rule: a tag may NOT contain another tag of the SAME letter
    directly or indirectly nested inside it (e.g. "<a><a></a></a>" is invalid
    because an 'a' is nested inside an 'a'). Different letters may nest freely.

    Return True only if the entire string parses as such a valid, properly
    nested tag sequence with the no-same-letter-nesting rule; otherwise False.
    The empty string is valid (it is zero tags).

    >>> nest_check("<a></a>")
    True
    >>> nest_check("<a><a></a></a>")
    False
    """
''',
        tests="""assert nest_check('') is True
assert nest_check('<a></a>') is True
assert nest_check('<a><a></a></a>') is False
assert nest_check('<a><b></b></a>') is True
assert nest_check('<a></b>') is False
assert nest_check('<a>') is False
assert nest_check('</a>') is False
assert nest_check('<a></a><a></a>') is True
assert nest_check('<a><b></a></b>') is False
assert nest_check('<ab></ab>') is False
assert nest_check('<a><b><a></a></b></a>') is False
""",
    ),
    CodeProblem(
        id="spell-charge",
        entry_point="spell_charge",
        prompt='''def spell_charge(runes: list[int], target: int) -> int:
    """You charge a spell to EXACTLY `target` energy by combining runes. Each
    rune in `runes` provides a positive integer amount of energy and may be used
    any number of times (unlimited supply of each). You want to reach the target
    using as FEW runes as possible (counting repeats).

    Return the minimum number of runes whose energies sum to exactly `target`,
    or -1 if the target cannot be reached. `target` is non-negative; reaching a
    target of 0 needs 0 runes.

    >>> spell_charge([1, 3, 4], 6)
    2
    >>> spell_charge([2], 3)
    -1
    """
''',
        tests="""assert spell_charge([1, 3, 4], 6) == 2
assert spell_charge([2], 3) == -1
assert spell_charge([1, 3, 4], 0) == 0
assert spell_charge([5, 7], 1) == -1
assert spell_charge([1], 5) == 5
assert spell_charge([3, 5], 11) == 3
assert spell_charge([2, 4], 7) == -1
assert spell_charge([7, 3, 2], 12) == 3
assert spell_charge([9], 9) == 1
""",
    ),
    CodeProblem(
        id="gravity-grid",
        entry_point="gravity_grid",
        prompt='''def gravity_grid(grid: list[list[str]]) -> list[list[str]]:
    """Apply gravity to a rectangular grid of single-character cells. Each cell
    is one of:

    - '#': a solid block that never moves.
    - 'o': a falling stone.
    - '.': empty space.

    Stones fall straight DOWN within their column: in each column, every 'o'
    settles as far down as it can, resting either on the floor (bottom row), on
    a '#', or on another stone that has already settled. '#' blocks stay exactly
    where they are and partition the column (stones cannot pass through them).
    The relative vertical order of stones within a column is preserved.

    Return the resulting grid (same dimensions). Do not mutate the input.

    >>> gravity_grid([["o"], ["."], ["."]])
    [['.'], ['.'], ['o']]
    >>> gravity_grid([["o"], ["#"], ["."]])
    [['o'], ['#'], ['.']]
    """
''',
        tests="""assert gravity_grid([['o'], ['.'], ['.']]) == [['.'], ['.'], ['o']]
assert gravity_grid([['o'], ['#'], ['.']]) == [['o'], ['#'], ['.']]
assert gravity_grid([['.'], ['o'], ['o']]) == [['.'], ['o'], ['o']]
assert gravity_grid([['o', '.'], ['.', 'o'], ['#', '.']]) == [['.', '.'], ['o', '.'], ['#', 'o']]
assert gravity_grid([['o', 'o'], ['o', '#'], ['.', 'o']]) == [['.', 'o'], ['o', '#'], ['o', 'o']]
assert gravity_grid([['.', '.'], ['.', '.']]) == [['.', '.'], ['.', '.']]
assert gravity_grid([['o'], ['o'], ['#'], ['.'], ['o']]) == [['o'], ['o'], ['#'], ['.'], ['o']]
""",
    ),
    CodeProblem(
        id="badge-valid",
        entry_point="badge_valid",
        prompt='''def badge_valid(code: str) -> bool:
    """Validate a badge code. A valid code has the exact form "GG-NNNN-K" where:

    - It is exactly 9 characters long.
    - Characters 0-1 ("GG") are two uppercase letters A-Z.
    - Character 2 is a hyphen '-'.
    - Characters 3-6 ("NNNN") are four digits 0-9.
    - Character 7 is a hyphen '-'.
    - Character 8 ("K") is a single digit check character.

    The check digit is computed from the four data digits d0 d1 d2 d3 (left to
    right) and the two letters. Let P(letter) be 1 for 'A', 2 for 'B', ..., 26
    for 'Z'. Compute:

        S = 1*d0 + 2*d1 + 3*d2 + 4*d3 + P(G1) + P(G2)

    The check digit K must equal S mod 10. Return True only if EVERY rule holds,
    otherwise False.

    >>> badge_valid("AA-0000-2")
    True
    >>> badge_valid("AA-0000-3")
    False
    """
''',
        tests="""assert badge_valid('AA-0000-2') is True
assert badge_valid('AA-0000-3') is False
assert badge_valid('AB-0000-3') is True
assert badge_valid('aa-0000-2') is False
assert badge_valid('AA-000-2') is False
assert badge_valid('AA-0000-2 ') is False
assert badge_valid('AA00002') is False
assert badge_valid('ZZ-1111-2') is True
assert badge_valid('AA-1234-K') is False
assert badge_valid('BC-0000-5') is True
""",
    ),
]
