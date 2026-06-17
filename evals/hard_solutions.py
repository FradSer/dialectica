"""Reference solutions for the hard benchmark (``hard_problems.py``).

Kept out of the problems file so the harness can verify each problem's
tests against a known-good implementation. Each entry is a complete,
self-contained definition of the problem's ``entry_point`` function.
"""

REFERENCE: dict[str, str] = {
    "tile-fit": """
def tile_fit(n: int) -> int:
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def f(rem, prev_one):
        if rem == 0:
            return 1
        total = 0
        if not prev_one:
            total += f(rem - 1, True)
        if rem >= 2:
            total += f(rem - 2, False)
        if rem >= 3:
            total += f(rem - 3, False)
        return total

    if n < 0:
        return 0
    return f(n, False)
""",
    "shelf-stack": """
def shelf_stack(ops: list[tuple[str, int]]) -> list[int]:
    shelf = []
    for kind, v in ops:
        if kind == "push":
            shelf.append(v)
        elif kind == "pop":
            if shelf:
                shelf.pop()
        elif kind == "sink":
            sunk = [x for x in shelf if x == v]
            rest = [x for x in shelf if x != v]
            shelf = sunk + rest
    return shelf
""",
    "relay-tokens": """
def relay_tokens(n: int, links: list[tuple[int, int, int]]) -> int:
    import heapq
    INF = float("inf")
    adj = [[] for _ in range(n)]
    for a, b, c in links:
        adj[a].append((b, c))
        adj[b].append((a, c))
    dist = [INF] * n
    dist[0] = 0
    pq = [(0, 0)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, c in adj[u]:
            fee = v if (v % 2 == 1) else 0
            nd = d + c + fee
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return dist[n - 1] if dist[n - 1] != INF else -1
""",
    "ridge-water": """
def ridge_water(heights: list[int], max_span: int) -> int:
    n = len(heights)
    if n == 0:
        return 0
    left = [0] * n
    right = [0] * n
    left[0] = heights[0]
    for i in range(1, n):
        left[i] = max(left[i - 1], heights[i])
    right[n - 1] = heights[n - 1]
    for i in range(n - 2, -1, -1):
        right[i] = max(right[i + 1], heights[i])
    pot = [min(left[i], right[i]) - heights[i] for i in range(n)]
    total = 0
    i = 0
    while i < n:
        if pot[i] > 0:
            j = i
            s = 0
            while j < n and pot[j] > 0:
                s += pot[j]
                j += 1
            span = j - i
            if span <= max_span:
                total += s
            i = j
        else:
            i += 1
    return total
""",
    "cargo-pairs": """
def cargo_pairs(items: list[tuple[int, int]], limit: int) -> int:
    fragile = sum(1 for w, f in items if f == 1)
    normal = sorted(w for w, f in items if f == 0)
    boxes = fragile
    i, j = 0, len(normal) - 1
    while i <= j:
        if i == j:
            boxes += 1
            break
        if normal[i] + normal[j] <= limit:
            i += 1
            j -= 1
        else:
            j -= 1
        boxes += 1
    return boxes
""",
    "orchard-pick": """
def orchard_pick(grid: list[list[int]]) -> int:
    from functools import lru_cache
    R = len(grid)
    C = len(grid[0])
    NEG = float("-inf")

    @lru_cache(maxsize=None)
    def best(r, c):
        cur = grid[r][c]
        if r == R - 1 and c == C - 1:
            return cur
        opt = NEG
        if r + 1 < R and grid[r + 1][c] != cur:
            opt = max(opt, best(r + 1, c))
        if c + 1 < C and grid[r][c + 1] != cur:
            opt = max(opt, best(r, c + 1))
        if opt == NEG:
            return NEG
        return cur + opt

    res = best(0, 0)
    return -1 if res == NEG else int(res)
""",
    "typo-stream": """
def typo_stream(s: str) -> str:
    out = []
    skip = 0
    for ch in s:
        if ch == "#":
            if out:
                out.pop()
        elif ch == "^":
            skip += 1
        else:
            if skip > 0:
                skip -= 1
            else:
                out.append(ch)
    return "".join(out)
""",
    "lock-combo": """
def lock_combo(length: int) -> int:
    keys = list(range(1, 10))
    pos = {k: ((k - 1) // 3, (k - 1) % 3) for k in keys}

    def reachable(a, b):
        if a == b:
            return False
        ra, ca = pos[a]
        rb, cb = pos[b]
        return ra == rb or ca == cb

    if length < 1:
        return 0
    dp = {k: 1 for k in keys}
    for _ in range(length - 1):
        nxt = {k: 0 for k in keys}
        for k in keys:
            for j in keys:
                if reachable(k, j):
                    nxt[j] += dp[k]
        dp = nxt
    return sum(dp.values())
""",
    "task-packer": """
def task_packer(tasks: list[tuple[int, int, int]]) -> int:
    import bisect
    if not tasks:
        return 0
    ts = sorted(tasks, key=lambda t: t[1])
    ends = [t[1] for t in ts]
    n = len(ts)
    dp = [0] * (n + 1)
    for i in range(1, n + 1):
        s, e, r = ts[i - 1]
        # last task whose end <= s
        idx = bisect.bisect_right(ends, s, 0, i - 1)
        take = dp[idx] + r
        skip = dp[i - 1]
        dp[i] = max(take, skip)
    return dp[n]
""",
    "current-cost": """
def current_cost(grid: list[list[int]]) -> int:
    import heapq
    R = len(grid)
    C = len(grid[0])
    INF = float("inf")
    dist = [[INF] * C for _ in range(R)]
    dist[0][0] = grid[0][0]
    pq = [(grid[0][0], 0, 0)]
    while pq:
        d, r, c = heapq.heappop(pq)
        if d > dist[r][c]:
            continue
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < R and 0 <= nc < C:
                step = 0 if grid[nr][nc] == grid[r][c] else grid[nr][nc]
                nd = d + step
                if nd < dist[nr][nc]:
                    dist[nr][nc] = nd
                    heapq.heappush(pq, (nd, nr, nc))
    return dist[R - 1][C - 1]
""",
    "bit-runs": """
def bit_runs(n: int) -> int:
    b = bin(n)[2:]
    # longest run of 1s
    best_ones = 0
    cur = 0
    for ch in b:
        if ch == "1":
            cur += 1
            best_ones = max(best_ones, cur)
        else:
            cur = 0
    # longest interior run of 0s (between two 1s)
    first_one = b.find("1")
    last_one = b.rfind("1")
    best_zeros = 0
    if first_one != -1 and last_one > first_one:
        interior = b[first_one:last_one + 1]
        cur = 0
        for ch in interior:
            if ch == "0":
                cur += 1
                best_zeros = max(best_zeros, cur)
            else:
                cur = 0
    return best_ones * best_zeros
""",
    "queue-merge": """
def queue_merge(arrivals: list[tuple[int, str]]) -> list[str]:
    fast = [(t, name) for t, name in arrivals if len(name) <= 4]
    slow = [(t, name) for t, name in arrivals if len(name) > 4]
    fast.sort(key=lambda x: (x[0], x[1]))
    slow.sort(key=lambda x: (x[0], x[1]))
    return [name for _, name in fast] + [name for _, name in slow]
""",
    "word-bridge": """
def word_bridge(words: list[str]) -> int:
    n = len(words)
    if n == 0:
        return 0
    dp = [1] * n
    best = 1
    for i in range(n):
        for j in range(i):
            if words[j][-1] == words[i][0]:
                if dp[j] + 1 > dp[i]:
                    dp[i] = dp[j] + 1
        best = max(best, dp[i])
    return best
""",
    "digit-fold": """
def digit_fold(n: int) -> int:
    while n >= 10:
        ds = list(str(n))
        i, j = 0, len(ds) - 1
        out = []
        while i < j:
            out.append((int(ds[i]) + int(ds[j])) % 10)
            i += 1
            j -= 1
        if i == j:
            out.append(int(ds[i]))
        # out currently lists outer pair first .. middle last, which is the
        # most-significant-first order we want
        n = int("".join(str(d) for d in out))
    return n
""",
    "paint-layers": """
def paint_layers(strokes: list[tuple[int, int, int]]) -> int:
    if not strokes:
        return 0
    lo = min(l for l, r, c in strokes)
    hi = max(r for l, r, c in strokes)
    if hi <= lo:
        return 0
    canvas = [0] * (hi - lo)
    for l, r, c in strokes:
        for x in range(l, r):
            canvas[x - lo] = c
    regions = 0
    prev = 0
    for v in canvas:
        if v != 0 and v != prev:
            regions += 1
        prev = v
    return regions
""",
    "stack-eval": """
def stack_eval(tokens: list[str]) -> int:
    st = []
    for t in tokens:
        if t == "+":
            a = st.pop()
            b = st.pop()
            st.append(b + a)
        elif t == "-":
            a = st.pop()
            b = st.pop()
            st.append(b - a)
        elif t == "*":
            a = st.pop()
            b = st.pop()
            st.append(b * a)
        elif t == "dup":
            st.append(st[-1])
        elif t == "swap":
            st[-1], st[-2] = st[-2], st[-1]
        elif t == "drop":
            st.pop()
        else:
            st.append(int(t))
    return st[-1] if st else 0
""",
    "nest-check": """
def nest_check(s: str) -> bool:
    i = 0
    n = len(s)
    stack = []
    open_letters = set()
    while i < n:
        if s[i] != "<":
            return False
        # close tag?
        if i + 1 < n and s[i + 1] == "/":
            # expect </x>
            if i + 3 >= n:
                return False
            letter = s[i + 2]
            if not letter.islower() or not letter.isalpha():
                return False
            if s[i + 3] != ">":
                return False
            if not stack or stack[-1] != letter:
                return False
            stack.pop()
            open_letters.discard(letter)
            i += 4
        else:
            # expect <x>
            if i + 2 >= n:
                return False
            letter = s[i + 1]
            if not letter.islower() or not letter.isalpha():
                return False
            if s[i + 2] != ">":
                return False
            if letter in open_letters:
                return False
            stack.append(letter)
            open_letters.add(letter)
            i += 3
    return not stack
""",
    "spell-charge": """
def spell_charge(runes: list[int], target: int) -> int:
    INF = float("inf")
    dp = [INF] * (target + 1)
    dp[0] = 0
    for t in range(1, target + 1):
        for r in runes:
            if r <= t and dp[t - r] + 1 < dp[t]:
                dp[t] = dp[t - r] + 1
    return dp[target] if dp[target] != INF else -1
""",
    "gravity-grid": """
def gravity_grid(grid: list[list[str]]) -> list[list[str]]:
    R = len(grid)
    if R == 0:
        return []
    C = len(grid[0])
    out = [["."] * C for _ in range(R)]
    for c in range(C):
        # process segments separated by '#'
        write = R - 1
        seg_bottom = R - 1
        # iterate from bottom to top
        r = R - 1
        stones = 0
        # We'll handle per-segment. Walk upward; '#' fixes position and flushes.
        r = R - 1
        # collect by scanning bottom-up, settling stones per gap segment
        bottom = R - 1
        rr = R - 1
        # Simpler: for each column, split into segments delimited by '#'
        col = [grid[r][c] for r in range(R)]
        # find segment boundaries
        start = 0
        for i in range(R + 1):
            if i == R or col[i] == "#":
                # segment is col[start:i]
                seg = col[start:i]
                cnt = sum(1 for ch in seg if ch == "o")
                length = i - start
                # place empties then stones at bottom of this segment
                for k in range(length):
                    pos = start + k
                    if k >= length - cnt:
                        out[pos][c] = "o"
                    else:
                        out[pos][c] = "."
                if i < R:
                    out[i][c] = "#"
                start = i + 1
    return out
""",
    "badge-valid": """
def badge_valid(code: str) -> bool:
    if len(code) != 9:
        return False
    g1, g2 = code[0], code[1]
    if not (g1.isalpha() and g1.isupper() and g2.isalpha() and g2.isupper()):
        return False
    if code[2] != "-" or code[7] != "-":
        return False
    digits = code[3:7]
    if not digits.isdigit():
        return False
    k = code[8]
    if not k.isdigit():
        return False
    ds = [int(ch) for ch in digits]
    s = sum((i + 1) * ds[i] for i in range(4))
    s += (ord(g1) - ord("A") + 1) + (ord(g2) - ord("A") + 1)
    return (s % 10) == int(k)
""",
}
