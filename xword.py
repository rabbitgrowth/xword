import curses
import os
import struct
import sys
from string import ascii_lowercase

ENCODING = 'iso-8859-1' # used by the .puz format

BLACK = '.'
EMPTY = '-'

LETTERS = set(ascii_lowercase)

class Puzzle:
    def __init__(self,
                 answers, buffer, numbers, acrosses, downs,
                 title, author, copyright, notes):
        # Puzzle information
        self.answers   = answers
        self.buffer    = buffer
        self.numbers   = numbers
        self.acrosses  = acrosses
        self.downs     = downs
        self.title     = title
        self.author    = author
        self.copyright = copyright
        self.notes     = notes

        # Initial cursor position
        self.x         = 0
        self.y         = 0
        self.direction = 'across'
        self.mode      = 'normal'

    def get(self, x, y):
        if x < 0 or y < 0:
            return None
        try:
            return self.buffer[y][x]
        except IndexError:
            return None

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

    def insert(self):
        self.mode = 'insert'

    def escape(self):
        self.mode = 'normal'

    def toggle(self):
        self.direction = 'down' if self.direction == 'across' else 'across'

    def type(self, key):
        self.buffer[self.y][self.x] = key.upper()
        if self.direction == 'across':
            self.move(1, 0)
        else:
            self.move(0, 1)

    def backspace(self):
        if self.direction == 'across':
            self.move(-1, 0)
        else:
            self.move(0, -1)
        self.buffer[self.y][self.x] = EMPTY

    def render(self):
        chunks = []
        for y, (number_row, buffer_row) in enumerate(zip(self.numbers, self.buffer)):
            for x, number in enumerate(number_row):
                vertex = '.' if y == 0 else ('.' if x == 0 else '+')
                edge   = '---' if number is None else f'{number:-<3}'
                chunks.append(vertex + edge)
            chunks.append('.\n')
            for x, square in enumerate(buffer_row):
                if square == BLACK:
                    fill = '///'
                else:
                    left, right = '><' if (x, y) == (self.x, self.y) else '  '
                    middle = ' ' if square == EMPTY else square
                    fill = left + middle + right
                chunks.append('|' + fill)
            chunks.append('|\n')
        width = len(self.numbers[0])
        chunks.append("'---" * width + "'\n")
        return ''.join(chunks)

def parse(filename):
    with open(filename, 'rb') as f:
        f.seek(0x2c) # skip stuff like checksums and file magic for now
        width, height, nclues = struct.unpack('<BBH', f.read(4))
        f.seek(4, 1) # skip unknown bitmask and scrambled tag
        answers, buffer = ([list(f.read(width).decode(ENCODING)) for _ in range(height)]
                           for _ in range(2))
        strings = f.read().decode(ENCODING).removesuffix('\0').split('\0')
        title, author, copyright, *clues, notes = strings
        assert len(clues) == nclues, f'Expected {nclues} clues, got {len(clues)}'
        # Assign numbers to the squares and clues.
        # Only the positions of black squares matter,
        # so `buffer` instead of `answers` should also work.
        acrosses, downs, numbers = assign(answers, clues)
        return Puzzle(answers, buffer, numbers, acrosses, downs,
                      title, author, copyright, notes)

def assign(grid, clues):
    clues    = iter(clues)
    acrosses = []
    downs    = []
    number   = 1
    numbers  = []

    for y, row in enumerate(grid):
        number_row = []
        for x, square in enumerate(row):
            if square == BLACK:
                number_row.append(None)
                continue
            numbered = False
            if x == 0 or grid[y][x - 1] == BLACK: # across numbered
                acrosses.append((number, next(clues)))
                numbered = True
            if y == 0 or grid[y - 1][x] == BLACK: # down numbered
                downs.append((number, next(clues)))
                numbered = True
            if numbered:
                number_row.append(number)
                number += 1
            else:
                number_row.append(None)
        numbers.append(number_row)

    return acrosses, downs, numbers

if __name__ == '__main__':
    # Prevent escape key delay
    os.environ.setdefault('ESCDELAY', '0')

    def main(stdscr):
        curses.curs_set(0) # invisible cursor
        puzzle = parse(sys.argv[1])
        while True:
            stdscr.addstr(0, 0, puzzle.render())
            stdscr.refresh()
            key = stdscr.getkey()
            puzzle.handle(key)

    curses.wrapper(main)
