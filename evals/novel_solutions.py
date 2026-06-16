"""Reference solutions for the novel (uncontaminated) code benchmark.

Kept separate from ``novel_problems.py`` so prompts never leak the algorithm.
Each entry is a self-contained implementation that passes its problem's tests
when run as ``python3 -c "<solution>\n\n<tests>"``. These exist purely so the
benchmark's correctness is auditable and re-verifiable.
"""

REFERENCE: dict[str, str] = {
    "glyph-checksum": """
def glyph_checksum(code: str) -> int:
    vowels = set("aeiou")
    total = 0
    for i, ch in enumerate(code):
        if not ch.isalpha():
            continue
        base = ord(ch.lower()) - ord("a") + 1
        if ch.lower() in vowels:
            base *= 2
        if i % 2 == 1:
            base += 3
        if ch.isupper():
            base = base * base
        total += base
    return total % 1000
""",
    "tide-windows": """
def tide_windows(levels: list[int], threshold: int) -> list[tuple[int, int]]:
    windows = []
    start = None
    for i, lv in enumerate(levels):
        if lv >= threshold:
            if start is None:
                start = i
        else:
            if start is not None:
                if i - start >= 2:
                    windows.append((start, i - 1))
                start = None
    if start is not None and len(levels) - start >= 2:
        windows.append((start, len(levels) - 1))
    return windows
""",
    "lumen-id": """
def lumen_id(code: str) -> bool:
    if len(code) != 9:
        return False
    if code[2] != "-":
        return False
    letters = code[:2]
    digits = code[3:8]
    check = code[8]
    if not (letters.isalpha() and letters.isupper()):
        return False
    if not digits.isdigit():
        return False
    if not check.isupper() or not check.isalpha():
        return False
    s = sum(int(d) for d in digits)
    s += (ord(letters[0]) - ord("A") + 1)
    s += (ord(letters[1]) - ord("A") + 1)
    expected = chr(ord("A") + (s % 26))
    return check == expected
""",
    "spiral-fold": """
def spiral_fold(text: str, width: int) -> list[str]:
    rows = [text[i:i + width] for i in range(0, len(text), width)]
    out = []
    for r, row in enumerate(rows):
        if r % 2 == 1:
            row = row[::-1]
        out.append(row)
    return out
""",
    "festival-seats": """
def festival_seats(requests: list[tuple[int, int]], capacity: int) -> int:
    seats = [0] * capacity
    seated = 0
    for size, vip in sorted(requests, key=lambda r: (-r[1], r[0])):
        run = 0
        placed = False
        for i in range(capacity):
            if seats[i] == 0:
                run += 1
                if run == size:
                    for j in range(i - size + 1, i + 1):
                        seats[j] = 1
                    seated += size
                    placed = True
                    break
            else:
                run = 0
        if not placed and vip == 1:
            return -1
    return seated
""",
    "rune-decay": """
def rune_decay(runes: str) -> str:
    result = list(runes)
    changed = True
    while changed:
        changed = False
        i = 0
        new = []
        while i < len(result):
            if i + 1 < len(result) and result[i] == result[i + 1]:
                i += 2
                changed = True
            else:
                new.append(result[i])
                i += 1
        result = new
    return "".join(result)
""",
    "ledger-balance": """
def ledger_balance(entries: list[str]) -> int:
    balance = 0
    streak = 0
    for entry in entries:
        sign = entry[0]
        amount = int(entry[1:])
        if sign == "+":
            balance += amount
            streak = 0
        else:
            if streak >= 2:
                amount *= 2
            balance -= amount
            streak += 1
    return balance
""",
    "ring-rotate": """
def ring_rotate(grid: list[list[int]]) -> list[list[int]]:
    n = len(grid)
    out = [row[:] for row in grid]
    for r in range((n + 1) // 2):
        top, left = r, r
        bottom, right = n - 1 - r, n - 1 - r
        if top == bottom and left == right:
            continue
        coords = []
        for j in range(left, right + 1):
            coords.append((top, j))
        for i in range(top + 1, bottom + 1):
            coords.append((i, right))
        for j in range(right - 1, left - 1, -1):
            coords.append((bottom, j))
        for i in range(bottom - 1, top, -1):
            coords.append((i, left))
        values = [grid[i][j] for i, j in coords]
        rotated = [values[-1]] + values[:-1]
        for (i, j), v in zip(coords, rotated):
            out[i][j] = v
    return out
""",
    "echo-compress": """
def echo_compress(s: str) -> str:
    if not s:
        return ""
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        count = 1
        while i + count < n and s[i + count] == ch:
            count += 1
        if count == 1:
            out.append(ch)
        elif count <= 3:
            out.append(ch * count)
        else:
            out.append(f"{ch}{count}")
        i += count
    return "".join(out)
""",
    "warden-patrol": """
def warden_patrol(moves: str) -> tuple[int, int]:
    x, y = 0, 0
    dirs = [(0, 1), (1, 0), (0, -1), (-1, 0)]
    facing = 0
    for m in moves:
        if m == "F":
            dx, dy = dirs[facing]
            x += dx
            y += dy
        elif m == "R":
            facing = (facing + 1) % 4
        elif m == "L":
            facing = (facing - 1) % 4
        elif m == "J":
            dx, dy = dirs[facing]
            x += 2 * dx
            y += 2 * dy
    return (x, y)
""",
    "token-bucket": """
def token_bucket(events: list[tuple[int, int]], capacity: int, refill: int) -> list[bool]:
    tokens = capacity
    last_time = 0
    result = []
    for time, cost in events:
        elapsed = time - last_time
        tokens = min(capacity, tokens + elapsed * refill)
        last_time = time
        if tokens >= cost:
            tokens -= cost
            result.append(True)
        else:
            result.append(False)
    return result
""",
    "harvest-yield": """
def harvest_yield(plots: list[int]) -> int:
    n = len(plots)
    if n == 0:
        return 0
    take = plots[0]
    skip = 0
    for i in range(1, n):
        new_take = skip + plots[i]
        new_skip = max(take, skip)
        take, skip = new_take, new_skip
    return max(take, skip)
""",
    "cipher-shift": """
def cipher_shift(text: str, key: str) -> str:
    out = []
    ki = 0
    for ch in text:
        if ch.isalpha():
            shift = ord(key[ki % len(key)].lower()) - ord("a")
            base = ord("A") if ch.isupper() else ord("a")
            out.append(chr((ord(ch) - base + shift) % 26 + base))
            ki += 1
        else:
            out.append(ch)
    return "".join(out)
""",
    "bracket-depth-sum": """
def bracket_depth_sum(expr: str) -> int:
    total = 0
    depth = 0
    for ch in expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch.isdigit():
            total += int(ch) * depth
    return total
""",
    "snake-path": """
def snake_path(n: int) -> list[list[int]]:
    grid = [[0] * n for _ in range(n)]
    val = 1
    for col in range(n):
        if col % 2 == 0:
            for row in range(n):
                grid[row][col] = val
                val += 1
        else:
            for row in range(n - 1, -1, -1):
                grid[row][col] = val
                val += 1
    return grid
""",
    "vote-tally": """
def vote_tally(ballots: list[list[str]]) -> str | None:
    counts = {}
    for ballot in ballots:
        seen = set()
        for rank, candidate in enumerate(ballot):
            if candidate in seen:
                continue
            seen.add(candidate)
            counts[candidate] = counts.get(candidate, 0) + (3 - rank if rank < 3 else 0)
    if not counts:
        return None
    best = max(counts.values())
    winners = sorted(c for c, v in counts.items() if v == best)
    if len(winners) > 1:
        return None
    return winners[0]
""",
    "pulse-merge": """
def pulse_merge(a: list[int], b: list[int]) -> list[int]:
    out = []
    i = j = 0
    take_a = True
    while i < len(a) or j < len(b):
        if take_a and i < len(a):
            out.append(a[i])
            i += 1
        elif not take_a and j < len(b):
            out.append(b[j])
            j += 1
        elif i < len(a):
            out.append(a[i])
            i += 1
        else:
            out.append(b[j])
            j += 1
        take_a = not take_a
    merged = []
    for v in out:
        if not merged or merged[-1] != v:
            merged.append(v)
    return merged
""",
    "grade-curve": """
def grade_curve(scores: list[int]) -> list[str]:
    if not scores:
        return []
    top = max(scores)
    result = []
    for s in scores:
        adjusted = s + (100 - top)
        if adjusted >= 90:
            result.append("A")
        elif adjusted >= 80:
            result.append("B")
        elif adjusted >= 70:
            result.append("C")
        elif adjusted >= 60:
            result.append("D")
        else:
            result.append("F")
    return result
""",
    "clock-angle": """
def clock_angle(hhmm: str) -> int:
    h, m = hhmm.split(":")
    h = int(h) % 12
    m = int(m)
    hour_angle = h * 30 + m * 0.5
    minute_angle = m * 6
    diff = abs(hour_angle - minute_angle)
    diff = min(diff, 360 - diff)
    return round(diff)
""",
    "relay-race": """
def relay_race(splits: list[list[int]]) -> int:
    n_teams = len(splits)
    if n_teams == 0:
        return -1
    totals = []
    for t, legs in enumerate(splits):
        if any(leg <= 0 for leg in legs):
            continue
        penalty = 0
        for i in range(1, len(legs)):
            if legs[i] > legs[i - 1]:
                penalty += 5
        totals.append((sum(legs) + penalty, t))
    if not totals:
        return -1
    totals.sort()
    return totals[0][1]
""",
}
