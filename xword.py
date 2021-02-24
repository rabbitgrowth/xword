import curses
import os
import struct
import sys
from collections import defaultdict
from itertools   import groupby
from string      import ascii_lowercase
from textwrap    import TextWrapper

ENCODING = 'iso-8859-1' # used by the .puz format

BLACK = '.'
EMPTY = '-'

DIRECTIONS = ('across', 'down')

LETTERS = set(ascii_lowercase)

WRAPPER = TextWrapper(width             = 32,
                      initial_indent    = ' '*4,
                      subsequent_indent = ' '*4)

class Puzzle:
    def __init__(self, answers, buffer, cluelist):
        self.answers = answers
        self.buffer  = buffer

        self.width  = len(answers[0])
        self.height = len(answers)

        # Map coords that start clues (across or down)
        # to lists of coords the clues span
        starts = {direction: {} for direction in DIRECTIONS}

        def key(pair):
            index, square = pair
            return square != BLACK

        for y, row in enumerate(self.buffer):
            for white, pairs in groupby(enumerate(row), key=key):
                if white:
                    xs = [x for x, _ in pairs]
                    starts['across'][(xs[0], y)] = [(x, y) for x in xs]

        for x, col in enumerate(zip(*self.buffer)):
            for white, pairs in groupby(enumerate(col), key=key):
                if white:
                    ys = [y for y, _ in pairs]
                    starts['down'][(x, ys[0])] = [(x, y) for y in ys]

        self.clues   = {direction: [] for direction in DIRECTIONS}
        self.numbers = {}
        cluelist     = iter(cluelist)
        number       = 1

        self.clue_by_coords = {direction: {} for direction in DIRECTIONS}
        self.clue_by_number = {direction: {} for direction in DIRECTIONS}

        for y in range(self.height):
            for x in range(self.width):
                numbered = False
                for direction in DIRECTIONS:
                    if (x, y) in starts[direction]:
                        span = starts[direction][(x, y)]
                        text = next(cluelist)
                        clue = Clue(number, span, text)
                        self.clues[direction].append(clue)
                        for coords in span:
                            self.clue_by_coords[direction][coords] = clue
                        self.clue_by_number[direction][number] = clue
                        numbered = True
                if numbered:
                    self.numbers[(x, y)] = number
                    number += 1

        for direction in DIRECTIONS:
            prev_clue = None
            for clue in self.clues[direction]:
                if prev_clue is not None:
                    clue.prev = prev_clue
                    prev_clue.next = clue
                prev_clue = clue

        self.mode      = 'normal'
        self.direction = 'across'

        # Initialize the cursor position to the first square of the
        # first across clue, which is not necessarily (0, 0), since
        # there could be black squares in the top left-hand corner.
        self.x, self.y = self.clues[self.direction][0].span[0]

    def run(self):
        # Prevent escape key delay
        os.environ.setdefault('ESCDELAY', '0')

        def main(stdscr):
            # Make cursor invisible
            curses.curs_set(0)
            # As a bit of an ugly hack, add an extra line at the bottom
            # to get around the curses quirk of not allowing writing at
            # the bottom right corner
            nrows = self.height * 2 + 1 # called `nlines` in curses
            ncols = self.width  * 4 + 1
            self.main_grid = curses.newwin(nrows + 1, ncols, 0, 0)
            self.mode_line = curses.newwin(1, ncols, nrows + 1, 0)
            stdscr.addstr(0, ncols + 2,  'Across')
            stdscr.addstr(0, ncols + 36, 'Down')
            stdscr.refresh()
            self.clue_grids = {'across': curses.newwin(nrows, 33, 1, ncols + 2),
                               'down':   curses.newwin(nrows, 33, 1, ncols + 36)}
            while True:
                self.main_grid.addstr(0, 0, ''.join(self.render()))
                self.main_grid.refresh()
                for direction, clue_grid in self.clue_grids.items():
                    clue_grid.erase()
                    clue_grid.addstr(0, 0, '\n'.join(self.render_clues(direction, nrows - 1)))
                    clue_grid.refresh()
                key = self.main_grid.getkey()
                self.handle(key)

        curses.wrapper(main)

    def render(self):
        span = set(self.current_clue.span)

        for y, row in enumerate(self.buffer):
            pairs = list(enumerate(row))
            for x, square in pairs:
                number = self.numbers.get((x, y))
                vertex = '.' if y == 0 else ('.' if x == 0 else '+')
                edge   = '---' if number is None else f'{number:-<3}'
                yield vertex
                yield edge
            yield '.'
            for x, square in pairs:
                if square == BLACK:
                    fill = '///'
                else:
                    if (x, y) == self.current_coords:
                        left, right = '><'
                    elif (x, y) in span:
                        left, right = '..'
                    else:
                        left, right = '  '
                    middle = ' ' if square == EMPTY else square
                    fill = left + middle + right
                yield '|'
                yield fill
            yield '|'
        yield "'---" * self.width
        yield "'"

    def render_clues(self, direction, nrows):
        lines   = []
        heights = []
        for index, clue in enumerate(self.clues[direction]):
            active = self.clue_by_coords[direction][self.current_coords] is clue
            render = clue.render(active)
            lines.extend(render)
            heights.append(len(render))
            if active:
                active_index = index
        if sum(heights[active_index:]) > nrows: # >= also works
            start   = sum(heights[:active_index])
            section = slice(start, start + nrows)
        else:
            section = slice(-nrows, None)
        return lines[section]

    def handle(self, key):
        # Keys that work in all modes
        if key == '\t':
            self.next()
        elif key == '?':
            self.reveal()
        else:
            # Keys specific to normal mode
            if self.mode == 'normal':
                if key == 'k':
                    self.move(0, -1)
                elif key == 'j':
                    self.move(0, 1)
                elif key == 'h':
                    self.move(-1, 0)
                elif key == 'l':
                    self.move(1, 0)
                elif key == '0':
                    self.start()
                elif key == '$':
                    self.end()
                elif key == 'w':
                    self.next()
                elif key == 'b':
                    self.prev()
                elif key == 'x':
                    self.delete()
                elif key == ' ':
                    self.toggle()
                elif key in ('i', 'a'):
                    self.insert()
                elif key == 'q':
                    sys.exit(0)
            # Keys specific to insert mode
            else:
                if key == 'j':
                    next_key = self.main_grid.getkey()
                    if next_key == 'k':
                        self.escape()
                    else:
                        self.type('j')
                        self.handle(next_key)
                elif key in LETTERS:
                    self.type(key)
                elif key == '\x7f':
                    self.backspace()
                else:
                    self.escape()

    @property
    def current_coords(self):
        return (self.x, self.y)

    @property
    def current_clue(self):
        return self.clue_by_coords[self.direction][self.current_coords]

    def in_range(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def is_white(self, x, y):
        return self.get(x, y) not in (BLACK, None)

    def get(self, x=None, y=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y

        if not self.in_range(x, y):
            return None
        return self.buffer[y][x]

    def set(self, letter, x=None, y=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y

        if not self.in_range(x, y):
            raise IndexError(f'Trying to assign to out-of-range square ({x}, {y})')
        self.buffer[y][x] = letter

    def jump(self, x, y):
        self.x = x
        self.y = y

    def move(self, dx, dy):
        x = self.x
        y = self.y
        x += dx
        y += dy
        while self.get(x, y) == BLACK:
            x += dx
            y += dy
        if self.get(x, y) is not None:
            self.jump(x, y)

    def start(self):
        self.jump(*self.current_clue.span[0])

    def end(self):
        self.jump(*self.current_clue.span[-1])

    def next(self):
        next_clue = self.current_clue.next
        if next_clue is not None:
            self.jump(*next_clue.span[0])
        else:
            self.jump(*self.clues[self.other_direction(self.direction)][0].span[0])
            self.toggle()

    def prev(self):
        prev_clue = self.current_clue.prev
        if prev_clue is not None:
            self.jump(*prev_clue.span[0])
        else:
            self.jump(*self.clues[self.other_direction(self.direction)][-1].span[0])
            self.toggle()

    def delete(self, x=None, y=None):
        if x is None:
            x = self.x
        if y is None:
            y = self.y

        self.set(EMPTY, x, y)

    @staticmethod
    def other_direction(direction):
        return 'down' if direction == 'across' else 'across'

    def toggle(self):
        self.direction = self.other_direction(self.direction)

    def insert(self):
        self.mode = 'insert'
        self.mode_line.addstr('-- INSERT --')
        self.mode_line.refresh()

    def escape(self):
        self.mode = 'normal'
        self.mode_line.erase()
        self.mode_line.refresh()

    def type(self, letter):
        self.set(letter.upper())
        self.advance()

    def reveal(self):
        self.set(self.answers[self.y][self.x])
        self.advance()

    def backspace(self):
        self.retreat()
        self.delete()

    def advance(self):
        if self.direction == 'across':
            next_coords = (self.x + 1, self.y)
        else:
            next_coords = (self.x, self.y + 1)
        if not self.is_white(*next_coords):
            self.next()
            # self.next() already jumps to the start,
            # so there's no need to write self.start() here
            # (compare with retreat() below)
        else:
            self.jump(*next_coords)

    def retreat(self):
        if self.direction == 'across':
            prev_coords = (self.x - 1, self.y)
        else:
            prev_coords = (self.x, self.y - 1)
        if not self.is_white(*prev_coords):
            self.prev()
            self.end()
        else:
            self.jump(*prev_coords)

class Clue:
    def __init__(self, number, span, text):
        self.number = number
        self.span   = span
        self.text   = text
        self.prev   = None
        self.next   = None

    def render(self, active):
        lines    = WRAPPER.wrap(self.text)
        star     = '*' if active else ' '
        lines[0] = f'{star}{self.number:>2} ' + lines[0][4:]
        return lines

def parse(filename):
    with open(filename, 'rb') as f:
        f.seek(0x2c) # skip checksums, file magic, etc. for now
        width, height, nclues = struct.unpack('<BBH', f.read(4))
        f.seek(4, 1) # skip unknown bitmask and scrambled tag
        answers, buffer = ([list(f.read(width).decode(ENCODING)) for _ in range(height)]
                           for _ in range(2))
        strings = f.read().decode(ENCODING).removesuffix('\0').split('\0')
        cluelist = strings[3:-1]
        assert len(cluelist) == nclues, f'Expected {nclues} clues, got {len(cluelist)}'
        return Puzzle(answers, buffer, cluelist)

if __name__ == '__main__':
    puzzle = parse(sys.argv[1])
    puzzle.run()
