import curses
import os
import struct
import sys
from collections import defaultdict
from itertools   import groupby
from string      import ascii_lowercase

ENCODING = 'iso-8859-1' # used by the .puz format

BLACK = '.'
EMPTY = '-'

LETTERS = set(ascii_lowercase)

DIRECTIONS = ('across', 'down')

class Puzzle:
    def __init__(self,
                 answers, buffer, cluelist,
                 title, author, copyright, notes):
        # Puzzle information
        self.answers   = answers
        self.buffer    = buffer
        self.cluelist  = cluelist
        self.title     = title
        self.author    = author
        self.copyright = copyright
        self.notes     = notes

        self.assign()

        # Initial cursor position
        self.x         = 0
        self.y         = 0
        self.direction = 'across'
        self.mode      = 'normal'

    def assign(self):
        self.starts = {direction: {}                for direction in DIRECTIONS}
        self.spans  = {direction: defaultdict(list) for direction in DIRECTIONS}
        starts      = {direction: set()             for direction in DIRECTIONS}

        for y, row in enumerate(self.buffer):
            for is_white, x_squares in groupby(enumerate(row),
                                               key=lambda x_square: x_square[1] != BLACK):
                if is_white:
                    x_squares = list(x_squares)
                    first_x   = x_squares[0][0]
                    starts['across'].add((first_x, y))
                    for x, square in x_squares:
                        self.starts['across'][(x, y)] = (first_x, y)
                        self.spans['across'][(first_x, y)].append((x, y))

        for x, column in enumerate(zip(*self.buffer)):
            for is_white, y_squares in groupby(enumerate(column),
                                               key=lambda y_square: y_square[1] != BLACK):
                if is_white:
                    y_squares = list(y_squares)
                    first_y   = y_squares[0][0]
                    starts['down'].add((x, first_y))
                    for y, square in y_squares:
                        self.starts['down'][(x, y)] = (x, first_y)
                        self.spans['down'][(x, first_y)].append((x, y))

        self.clues   = defaultdict(dict)
        self.numbers = {}
        cluelist     = iter(self.cluelist)
        number       = 1

        for y in range(self.height):
            for x in range(self.width):
                numbered = False
                for direction in DIRECTIONS:
                    if (x, y) in starts[direction]:
                        self.clues[direction][number] = next(cluelist)
                        numbered = True
                if numbered:
                    self.numbers[(x, y)] = number
                    number += 1

    @property
    def width(self):
        return len(self.buffer[0])

    @property
    def height(self):
        return len(self.buffer)

    def run(self):
        # Prevent escape key delay
        os.environ.setdefault('ESCDELAY', '0')

        def main(stdscr):
            # Make cursor invisible
            curses.curs_set(0)
            # As a bit of an ugly hack, add an extra line at the bottom
            # to get around the curses quirk of not allowing writing at
            # the bottom right corner
            self.maingrid = curses.newwin(self.height * 2 + 2, # nlines (with one extra)
                                          self.width  * 4 + 1, # ncols
                                          0,                   # begin_y
                                          0)                   # begin_x
            self.modeline = curses.newwin(1,
                                          self.width  * 4 + 1,
                                          self.height * 2 + 2,
                                          0)
            while True:
                self.maingrid.addstr(0, 0, ''.join(self.render()))
                self.maingrid.refresh()
                key = self.maingrid.getkey()
                self.handle(key)

        curses.wrapper(main)

    def handle(self, key):
        if self.mode == 'normal':
            if key == 'k':
                self.move(0, -1)
            elif key == 'j':
                self.move(0, 1)
            elif key == 'h':
                self.move(-1, 0)
            elif key == 'l':
                self.move(1, 0)
            elif key == 'x':
                self.delete()
            elif key == 'i':
                self.insert()
            elif key == ' ':
                self.toggle()
            elif key == 'q':
                sys.exit(0)
        elif self.mode == 'insert':
            if key in LETTERS:
                self.type(key)
            elif key == '\x7f':
                self.backspace()
            elif key == '\x1b':
                self.escape()

    def get(self, x, y):
        if x < 0 or y < 0:
            return None
        try:
            return self.buffer[y][x]
        except IndexError:
            return None

    def set(self, x, y, letter):
        self.buffer[y][x] = letter

    def move(self, dx, dy):
        x = self.x
        y = self.y
        x += dx
        y += dy
        while self.get(x, y) == BLACK:
            x += dx
            y += dy
        if self.get(x, y) is not None:
            self.x = x
            self.y = y

    def insert(self):
        self.mode = 'insert'
        self.modeline.addstr('-- INSERT --')
        self.modeline.refresh()

    def escape(self):
        self.mode = 'normal'
        self.modeline.erase()
        self.modeline.refresh()

    def toggle(self):
        self.direction = 'down' if self.direction == 'across' else 'across'

    def type(self, key):
        self.set(self.x, self.y, key.upper())
        if self.direction == 'across':
            self.move(1, 0)
        else:
            self.move(0, 1)

    def backspace(self):
        # If the cursor is on a letter, delete that letter,
        # otherwise delete the previous letter. This ensures
        # that the last letter on a line is deletable.
        if self.get(self.x, self.y) == EMPTY:
            if self.direction == 'across':
                self.move(-1, 0)
            else:
                self.move(0, -1)
        self.delete()

    def delete(self):
        self.set(self.x, self.y, EMPTY)

    def render(self):
        start = self.starts[self.direction][(self.x, self.y)]
        span  = set(self.spans[self.direction][start])

        for y, row in enumerate(self.buffer):
            squares = list(enumerate(row))
            for x, square in squares:
                number = self.numbers.get((x, y))
                vertex = '.' if y == 0 else ('.' if x == 0 else '+')
                edge   = '---' if number is None else f'{number:-<3}'
                yield vertex
                yield edge
            yield '.'
            for x, square in squares:
                if square == BLACK:
                    fill = '///'
                else:
                    if (x, y) == (self.x, self.y):
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

def parse(filename):
    with open(filename, 'rb') as f:
        f.seek(0x2c) # skip stuff like checksums and file magic for now
        width, height, nclues = struct.unpack('<BBH', f.read(4))
        f.seek(4, 1) # skip unknown bitmask and scrambled tag
        answers, buffer = ([list(f.read(width).decode(ENCODING)) for _ in range(height)]
                           for _ in range(2))
        strings = f.read().decode(ENCODING).removesuffix('\0').split('\0')
        title, author, copyright, *cluelist, notes = strings
        assert len(cluelist) == nclues, f'Expected {nclues} clues, got {len(cluelist)}'
        return Puzzle(answers, buffer, cluelist,
                      title, author, copyright, notes)

if __name__ == '__main__':
    puzzle = parse(sys.argv[1])
    puzzle.run()
