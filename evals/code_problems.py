"""HumanEval-style code problems with ground-truth unit tests.

Each problem is a Python function specification; verification executes the
candidate implementation against the asserts, so scoring needs no LLM judge.
Problems are adapted from the OpenAI HumanEval benchmark (MIT license).
"""

from pydantic import BaseModel, Field


class CodeProblem(BaseModel):
    """One code-generation problem with executable acceptance tests."""

    id: str = Field(..., description="Short slug identifying the problem.")
    prompt: str = Field(..., description="Function stub with docstring.")
    entry_point: str = Field(..., description="Name of the required function.")
    tests: str = Field(..., description="Assert-based acceptance tests.")


SWE_PROBLEMS = [
    CodeProblem(
        id="has-close-elements",
        entry_point="has_close_elements",
        prompt='''def has_close_elements(numbers: list[float], threshold: float) -> bool:
    """Check if in given list of numbers, are any two numbers closer to each
    other than the given threshold.
    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)
    False
    >>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)
    True
    """
''',
        tests="""assert has_close_elements([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.3) is True
assert has_close_elements([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.05) is False
assert has_close_elements([1.0, 2.0, 5.9, 4.0, 5.0], 0.95) is True
assert has_close_elements([1.0, 2.0, 5.9, 4.0, 5.0], 0.8) is False
assert has_close_elements([1.0], 1.0) is False
assert has_close_elements([], 1.0) is False
""",
    ),
    CodeProblem(
        id="separate-paren-groups",
        entry_point="separate_paren_groups",
        prompt='''def separate_paren_groups(paren_string: str) -> list[str]:
    """Input to this function is a string containing multiple groups of nested
    parentheses. Your goal is to separate those groups into separate strings
    and return the list of those. Separate groups are balanced (each open
    brace is properly closed) and not nested within each other. Ignore any
    spaces in the input string.
    >>> separate_paren_groups('( ) (( )) (( )( ))')
    ['()', '(())', '(()())']
    """
''',
        tests="""assert separate_paren_groups('(()()) ((())) () ((())()())') == ['(()())', '((()))', '()', '((())()())']
assert separate_paren_groups('() (()) ((())) (((())))') == ['()', '(())', '((()))', '(((())))']
assert separate_paren_groups('(()(())((())))') == ['(()(())((())))']
assert separate_paren_groups('( ) (( )) (( )( ))') == ['()', '(())', '(()())']
""",
    ),
    CodeProblem(
        id="below-zero",
        entry_point="below_zero",
        prompt='''def below_zero(operations: list[int]) -> bool:
    """You're given a list of deposit and withdrawal operations on a bank
    account that starts with zero balance. Your task is to detect if at any
    point the balance of account falls below zero, and at that point function
    should return True. Otherwise it should return False.
    >>> below_zero([1, 2, 3])
    False
    >>> below_zero([1, 2, -4, 5])
    True
    """
''',
        tests="""assert below_zero([]) is False
assert below_zero([1, 2, -3, 1, 2, -3]) is False
assert below_zero([1, 2, -4, 5, 6]) is True
assert below_zero([1, -1, 2, -2, 5, -5, 4, -4]) is False
assert below_zero([1, -1, 2, -2, 5, -5, 4, -5]) is True
""",
    ),
    CodeProblem(
        id="make-palindrome",
        entry_point="make_palindrome",
        prompt='''def make_palindrome(string: str) -> str:
    """Find the shortest palindrome that begins with a supplied string.
    Algorithm idea is simple:
    - Find the longest postfix of supplied string that is a palindrome.
    - Append to the end of the string reverse of a string prefix that comes
      before the palindromic suffix.
    >>> make_palindrome('')
    ''
    >>> make_palindrome('cat')
    'catac'
    >>> make_palindrome('cata')
    'catac'
    """
''',
        tests="""assert make_palindrome('') == ''
assert make_palindrome('x') == 'x'
assert make_palindrome('xyz') == 'xyzyx'
assert make_palindrome('xyx') == 'xyx'
assert make_palindrome('jerry') == 'jerryrrej'
""",
    ),
    CodeProblem(
        id="remove-duplicates",
        entry_point="remove_duplicates",
        prompt='''def remove_duplicates(numbers: list[int]) -> list[int]:
    """From a list of integers, remove all elements that occur more than once.
    Keep order of elements left the same as in the input.
    >>> remove_duplicates([1, 2, 3, 2, 4])
    [1, 3, 4]
    """
''',
        tests="""assert remove_duplicates([]) == []
assert remove_duplicates([1, 2, 3, 4]) == [1, 2, 3, 4]
assert remove_duplicates([1, 2, 3, 2, 4, 3, 5]) == [1, 4, 5]
assert remove_duplicates([1, 1, 1]) == []
""",
    ),
    CodeProblem(
        id="is-prime",
        entry_point="is_prime",
        prompt='''def is_prime(n: int) -> bool:
    """Return true if a given number is prime, and false otherwise.
    >>> is_prime(6)
    False
    >>> is_prime(101)
    True
    >>> is_prime(11)
    True
    >>> is_prime(1)
    False
    """
''',
        tests="""assert is_prime(6) is False
assert is_prime(101) is True
assert is_prime(11) is True
assert is_prime(13441) is True
assert is_prime(61) is True
assert is_prime(4) is False
assert is_prime(1) is False
assert is_prime(0) is False
assert is_prime(-7) is False
""",
    ),
    CodeProblem(
        id="prime-fib",
        entry_point="prime_fib",
        prompt='''def prime_fib(n: int) -> int:
    """prime_fib returns the n-th number that is a Fibonacci number and it's
    also prime.
    >>> prime_fib(1)
    2
    >>> prime_fib(2)
    3
    >>> prime_fib(3)
    5
    >>> prime_fib(4)
    13
    >>> prime_fib(5)
    89
    """
''',
        tests="""assert prime_fib(1) == 2
assert prime_fib(2) == 3
assert prime_fib(3) == 5
assert prime_fib(4) == 13
assert prime_fib(5) == 89
assert prime_fib(6) == 233
assert prime_fib(7) == 1597
""",
    ),
    CodeProblem(
        id="longest",
        entry_point="longest",
        prompt='''def longest(strings: list[str]) -> str | None:
    """Out of list of strings, return the longest one. Return the first one in
    case of multiple strings of the same length. Return None in case the input
    list is empty.
    >>> longest([])

    >>> longest(['a', 'b', 'c'])
    'a'
    >>> longest(['a', 'bb', 'ccc'])
    'ccc'
    """
''',
        tests="""assert longest([]) is None
assert longest(['x', 'y', 'z']) == 'x'
assert longest(['x', 'yyy', 'zzzz', 'www', 'kkkk', 'abc']) == 'zzzz'
""",
    ),
    CodeProblem(
        id="find-zero",
        entry_point="find_zero",
        prompt='''def find_zero(xs: list[float]) -> float:
    """xs are coefficients of a polynomial:
    xs[0] + xs[1] * x + xs[2] * x^2 + ...
    find_zero finds x such that the polynomial evaluates to zero.
    find_zero returns only one zero point, even if there are many.
    Moreover, find_zero only takes list xs having an even number of
    coefficients and the largest non-zero coefficient, as it guarantees a
    solution.
    >>> round(find_zero([1, 2]), 2)  # f(x) = 1 + 2x
    -0.5
    >>> round(find_zero([-6, 11, -6, 1]), 2)  # (x - 1) * (x - 2) * (x - 3)
    1.0
    """
''',
        tests="""def _poly(xs, x):
    return sum(c * x**i for i, c in enumerate(xs))

assert abs(_poly([-6, 1], find_zero([-6, 1]))) < 1e-3
assert abs(_poly([1, 2], find_zero([1, 2]))) < 1e-3
assert abs(_poly([-6, 11, -6, 1], find_zero([-6, 11, -6, 1]))) < 1e-3
assert abs(_poly([-24, 26, -9, 1], find_zero([-24, 26, -9, 1]))) < 1e-3
""",
    ),
    CodeProblem(
        id="min-path",
        entry_point="minPath",
        prompt='''def minPath(grid: list[list[int]], k: int) -> list[int]:
    """Given a grid with N rows and N columns (N >= 2) and a positive integer
    k, each cell of the grid contains a value. Every integer in the range
    [1, N * N] inclusive appears exactly once on the cells of the grid.

    You have to find the minimum path of length k in the grid. You can start
    from any cell, and in each step you can move to any of the neighbor cells
    sharing an edge with the current cell. You CAN go through cells you have
    visited before. A path A (of length k) is considered less than a path B
    (of length k) if, after listing the values on the cells that A and B go
    through, the lexicographically smaller list wins. The answer is unique.

    Return an ordered list of the values on the cells that the minimum path
    goes through.
    >>> minPath([[1, 2, 3], [4, 5, 6], [7, 8, 9]], 3)
    [1, 2, 1]
    >>> minPath([[5, 9, 3], [4, 1, 6], [7, 8, 2]], 1)
    [1]
    """
''',
        tests="""assert minPath([[1, 2, 3], [4, 5, 6], [7, 8, 9]], 3) == [1, 2, 1]
assert minPath([[5, 9, 3], [4, 1, 6], [7, 8, 2]], 1) == [1]
assert minPath([[2, 1], [3, 4]], 4) == [1, 2, 1, 2]
assert minPath([[6, 4, 13, 10], [5, 7, 12, 1], [3, 16, 11, 15], [8, 14, 9, 2]], 5) == [1, 10, 1, 10, 1]
""",
    ),
    CodeProblem(
        id="do-algebra",
        entry_point="do_algebra",
        prompt='''def do_algebra(operator: list[str], operand: list[int]) -> int:
    """Given two lists operator and operand. The first list has basic algebra
    operations, and the second list is a list of integers. Use the two given
    lists to build the algebraic expression and return its evaluation.

    The basic algebra operations: Addition ( + ), Subtraction ( - ),
    Multiplication ( * ), Floor division ( // ), Exponentiation ( ** ).

    Example:
    operator = ['+', '*', '-'], operand = [2, 3, 4, 5]
    => expression = 2 + 3 * 4 - 5 => result = 9

    Note: the length of operator list is equal to the length of operand list
    minus one. Operands are non-negative integers; operator list has at least
    one operator. Standard precedence applies.
    """
''',
        tests="""assert do_algebra(['+', '*', '-'], [2, 3, 4, 5]) == 9
assert do_algebra(['//', '*'], [7, 3, 4]) == 8
assert do_algebra(['**', '*', '+'], [2, 3, 4, 5]) == 37
assert do_algebra(['+', '*', '-', '//'], [2, 3, 4, 5, 2]) == 12
""",
    ),
    CodeProblem(
        id="match-parens",
        entry_point="match_parens",
        prompt='''def match_parens(lst: list[str]) -> str:
    """You are given a list of two strings, both strings consist of open
    parentheses '(' or close parentheses ')' only. Your job is to check if it
    is possible to concatenate the two strings in some order, that the
    resulting string will be good. A string S is considered to be good if and
    only if all parentheses in S are balanced.

    Return 'Yes' if there's a way to make a good string, and return 'No'
    otherwise.

    Examples:
    match_parens(['()(', ')']) == 'Yes'
    match_parens([')', ')']) == 'No'
    """
''',
        tests="""assert match_parens(['()(', ')']) == 'Yes'
assert match_parens([')', ')']) == 'No'
assert match_parens(['(', ')']) == 'Yes'
assert match_parens([')(', '()']) == 'No'
assert match_parens(['(', '(']) == 'No'
assert match_parens(['(())', '()']) == 'Yes'
""",
    ),
    CodeProblem(
        id="order-by-points",
        entry_point="order_by_points",
        prompt='''def order_by_points(nums: list[int]) -> list[int]:
    """Sort the given list of integers in ascending order according to the
    sum of their digits. For a negative number, its first digit is negative
    (e.g. for -123 the digits sum is (-1) + 2 + 3 = 4). If there are several
    items with a similar sum of digits, order them based on their index in
    the original list (stable).

    For example:
    >>> order_by_points([1, 11, -1, -11, -12])
    [-1, -11, 1, -12, 11]
    >>> order_by_points([])
    []
    """
''',
        tests="""assert order_by_points([1, 11, -1, -11, -12]) == [-1, -11, 1, -12, 11]
assert order_by_points([]) == []
assert order_by_points([0, 6, 3, -2, 5]) == [-2, 0, 3, 5, 6]
assert order_by_points([-21, -12, 10]) == [-21, -12, 10]
assert order_by_points([100, 9]) == [100, 9]
""",
    ),
    CodeProblem(
        id="decode-cyclic",
        entry_point="decode_cyclic",
        prompt='''def encode_cyclic(s: str) -> str:
    """Returns encoded string by cycling groups of three characters."""
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(group[1:] + group[0]) if len(group) == 3 else group for group in groups]
    return "".join(groups)


def decode_cyclic(s: str) -> str:
    """Takes as input string encoded with encode_cyclic function. Returns the
    decoded string.
    """
''',
        tests="""def _encode(s):
    groups = [s[(3 * i):min((3 * i + 3), len(s))] for i in range((len(s) + 2) // 3)]
    groups = [(g[1:] + g[0]) if len(g) == 3 else g for g in groups]
    return "".join(groups)

assert decode_cyclic(_encode('abc')) == 'abc'
assert decode_cyclic(_encode('abcdefgh')) == 'abcdefgh'
assert decode_cyclic(_encode('a')) == 'a'
assert decode_cyclic(_encode('hello world from dialectica')) == 'hello world from dialectica'
assert decode_cyclic(_encode('')) == ''
""",
    ),
    CodeProblem(
        id="count-nums",
        entry_point="count_nums",
        prompt='''def count_nums(arr: list[int]) -> int:
    """Write a function count_nums which takes an array of integers and
    returns the number of elements which has a sum of digits > 0. If a number
    is negative, then its first signed digit will be negative: e.g. -123 has
    signed digits -1, 2, and 3.
    >>> count_nums([]) == 0
    >>> count_nums([-1, 11, -11]) == 1
    >>> count_nums([1, 1, 2]) == 3
    """
''',
        tests="""assert count_nums([]) == 0
assert count_nums([-1, 11, -11]) == 1
assert count_nums([1, 1, 2]) == 3
assert count_nums([-123]) == 1
assert count_nums([-12, -33, 0]) == 1
""",
    ),
    CodeProblem(
        id="is-nested",
        entry_point="is_nested",
        prompt='''def is_nested(string: str) -> bool:
    """Create a function that takes a string as input which contains only
    square brackets. The function should return True if and only if there is
    a valid subsequence of brackets where at least one bracket in the
    subsequence is nested.

    is_nested('[[]]') -> True
    is_nested('[]]]]]]][[[[[]') -> False
    is_nested('[][]') -> False
    is_nested('[]') -> False
    is_nested('[[][]]') -> True
    is_nested('[[]][[') -> True
    """
''',
        tests="""assert is_nested('[[]]') is True
assert is_nested('[]]]]]]][[[[[]') is False
assert is_nested('[][]') is False
assert is_nested('[]') is False
assert is_nested('[[][]]') is True
assert is_nested('[[]][[') is True
assert is_nested('[[][[]]]') is True
assert is_nested('') is False
""",
    ),
    CodeProblem(
        id="compare-one",
        entry_point="compare_one",
        prompt='''def compare_one(a, b):
    """Create a function that takes integers, floats, or strings representing
    real numbers, and returns the larger variable in its given variable type.
    Return None if the values are equal.
    Note: If a real number is represented as a string, the floating point
    might be . or ,

    compare_one(1, 2.5) -> 2.5
    compare_one(1, "2,3") -> "2,3"
    compare_one("5,1", "6") -> "6"
    compare_one("1", 1) -> None
    """
''',
        tests="""assert compare_one(1, 2.5) == 2.5
assert compare_one(1, "2,3") == "2,3"
assert compare_one("5,1", "6") == "6"
assert compare_one("1", 1) is None
assert compare_one(1, 2) == 2
assert compare_one("2,0", "2.0") is None
""",
    ),
    CodeProblem(
        id="max-fill",
        entry_point="max_fill",
        prompt='''def max_fill(grid: list[list[int]], capacity: int) -> int:
    """You are given a rectangular grid of wells. Each row represents a single
    well, and each 1 in a row represents a single unit of water. Each well has
    a corresponding bucket that can be used to extract water from it, and all
    buckets have the same capacity. Your task is to use the buckets to empty
    the wells. Output the number of times you need to lower the buckets.

    Example 1:
        grid = [[0,0,1,0], [0,1,0,0], [1,1,1,1]], capacity = 1
        => 6
    Example 2:
        grid = [[0,0,1,1], [0,0,0,0], [1,1,1,1], [0,1,1,1]], capacity = 2
        => 5
    Example 3:
        grid = [[0,0,0], [0,0,0]], capacity = 5
        => 0
    """
''',
        tests="""assert max_fill([[0, 0, 1, 0], [0, 1, 0, 0], [1, 1, 1, 1]], 1) == 6
assert max_fill([[0, 0, 1, 1], [0, 0, 0, 0], [1, 1, 1, 1], [0, 1, 1, 1]], 2) == 5
assert max_fill([[0, 0, 0], [0, 0, 0]], 5) == 0
assert max_fill([[1, 1, 1, 1], [1, 1, 1, 1]], 2) == 4
assert max_fill([[1, 1, 1, 1], [1, 1, 1, 1]], 9) == 2
""",
    ),
]
