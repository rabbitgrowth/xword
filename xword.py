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

#         xpos     ypos    shape
SHAPES = {'head': {'head': 'topleft',
                   'body': 'left',
                   'tail': 'bottomleft'},
          'body': {'head': 'top',
                   'body': 'middle',
                   'tail': 'bottom'},
          'tail': {'head': 'topright',
                   'body': 'right',
                   'tail': 'bottomright'}}

#           shape          boldness
VERTICES = {'topleft':     {'normal':      '┌',
                            'topleft':     '┏'},
            'top':         {'normal':      '┬',
                            'topleft':     '┲',
                            'topright':    '┱',
                            'horizontal':  '┯'},
            'topright':    {'normal':      '┐',
                            'topright':    '┓'},
            'left':        {'normal':      '├',
                            'topleft':     '┢',
                            'bottomleft':  '┡',
                            'vertical':    '┠'},
            'middle':      {'normal':      '┼',
                            'topleft':     '╆',
                            'topright':    '╅',
                            'bottomleft':  '╄',
                            'bottomright': '╃',
                            'horizontal':  '┿',
                            'vertical':    '╂'},
            'right':       {'normal':      '┤',
                            'topright':    '┪',
                            'bottomright': '┩',
                            'vertical':    '┨'},
            'bottomleft':  {'normal':      '└',
                            'bottomleft':  '┗'},
            'bottom':      {'normal':      '┴',
                            'bottomleft':  '┺',
                            'bottomright': '┹',
                            'horizontal':  '┷'},
            'bottomright': {'normal':      '┘',
                            'bottomright': '┛'}}

#        direction     bold?
EDGES = {'horizontal': '─━',
         'vertical':   '│┃'}

SHADE = '░'

class Puzzle:
    def __init__(self, answer, buffer, cluelist, title, author, copyright, notes):
        self.squares = [[Square(x, y, a, b)
                         for x, (a, b) in enumerate(zip(answer_row, buffer_row))]
                        for y, (answer_row, buffer_row) in enumerate(zip(answer, buffer))]

        self.width  = len(self.squares[0])
        self.height = len(self.squares)

        self.title     = title
        self.author    = author
        self.copyright = copyright
        self.notes     = notes

        # Map squares that start clues to the squares the clues span
        spans = {direction: {} for direction in DIRECTIONS}

        for direction, grid in zip(DIRECTIONS, (self.squares, zip(*self.squares))):
            for row in grid: # or column
                for is_black, squares in groupby(row, key=lambda square: square.is_black()):
                    if not is_black: # contiguous sequence of white squares
                        squares = list(squares)
                        spans[direction][squares[0]] = squares

        # Assign clue numbers
        number     = 1
        cluelist   = iter(cluelist)
        self.clues = {direction: [] for direction in DIRECTIONS}

        for row in self.squares:
            for square in row:
                numbered = False
                for direction in DIRECTIONS:
                    span = spans[direction].get(square)
                    if span is not None:
                        text = next(cluelist)
                        clue = Clue(number, span, text)
                        self.clues[direction].append(clue)
                        square.number = number
                        for other_square in span:
                            other_square.clues[direction] = clue
                        numbered = True
                if numbered:
                    number += 1

        # Doubly-link clues
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
            # Hide cursor
            curses.curs_set(0)
            # Compute size of puzzle grid
            nrows = self.height * 2 + 1 # or, in curses lingo, `nlines`
            ncols = self.width  * 4 + 1
            # Draw static stuff
            stdscr.addstr(0, 0, self.title, curses.A_BOLD)
            stdscr.addstr(1, 0, self.author)
            stdscr.addstr(3, ncols + 2,  'Across', curses.A_BOLD)
            stdscr.addstr(3, ncols + 36, 'Down',   curses.A_BOLD)
            stdscr.refresh()
            # As a bit of an ugly hack to get around the curses quirk of not
            # allowing writing at the bottom right corner, add an extra line
            # at the bottom of windows that can be filled to the brim
            self.main_grid   = curses.newwin(nrows + 1, ncols, 3, 0)
            self.status_line = curses.newwin(1, ncols, nrows + 4, 0)
            self.clue_grids  = {'across': curses.newwin(nrows, 33, 4, ncols + 2),
                                'down':   curses.newwin(nrows, 33, 4, ncols + 36)}
            while True:
                self.render_main_grid()
                self.render_clue_grids()
                self.handle(stdscr.getkey())

        curses.wrapper(main)

    def render_main_grid(self):
        self.main_grid.erase()

        span       = self.current_clue.span
        boldnesses = {}
        if self.direction == 'across':
            x, y = span[0]
            boldnesses[(x, y    )] = 'topleft'
            boldnesses[(x, y + 1)] = 'bottomleft'
            for x, y in span[1:]:
                boldnesses[(x, y    )] = 'horizontal'
                boldnesses[(x, y + 1)] = 'horizontal'
            x, y = span[-1]
            boldnesses[(x + 1, y    )] = 'topright'
            boldnesses[(x + 1, y + 1)] = 'bottomright'
        else:
            x, y = span[0]
            boldnesses[(x,     y)] = 'topleft'
            boldnesses[(x + 1, y)] = 'topright'
            for x, y in span[1:]:
                boldnesses[(x,     y)] = 'vertical'
                boldnesses[(x + 1, y)] = 'vertical'
            x, y = span[-1]
            boldnesses[(x,     y + 1)] = 'bottomleft'
            boldnesses[(x + 1, y + 1)] = 'bottomright'

        vertices = []
        for y in range(self.height + 1):
            row = []
            for x in range(self.width + 1):
                xpos     = {0: 'head', self.width:  'tail'}.get(x, 'body')
                ypos     = {0: 'head', self.height: 'tail'}.get(y, 'body')
                shape    = SHAPES[xpos][ypos]
                boldness = boldnesses.get((x, y), 'normal')
                vertex   = VERTICES[shape][boldness]
                row.append(vertex)
            vertices.append(row)

        for y in range(self.height):
            for x in range(self.width):
                vertex = vertices[y][x]
                self.main_grid.addstr(vertex)

                square    = self.get(x, y)
                number    = square.number
                attribute = curses.A_BOLD if number == self.current_clue.number else curses.A_NORMAL
                number    = '' if number is None else str(number)
                self.main_grid.addstr(number, attribute)

                bold = boldnesses.get((x, y)) in ('topleft', 'bottomleft', 'horizontal')
                edge = EDGES['horizontal'][bold] * (3 - len(number))
                self.main_grid.addstr(edge)

            self.main_grid.addstr(vertices[y][x + 1])

            for x in range(self.width):
                bold = boldnesses.get((x, y)) in ('topleft', 'topright', 'vertical')
                edge = EDGES['vertical'][bold]
                self.main_grid.addstr(edge)

                square = self.get(x, y)
                if square.is_black():
                    self.main_grid.addstr(SHADE * 3)
                else:
                    cursor = '>' if (x, y) == (self.x, self.y) else ' '
                    self.main_grid.addstr(cursor, curses.A_BOLD)

                    letter = ' ' if square.buffer == EMPTY else square.buffer
                    status = ' ' # hard-code to be blank for now
                    self.main_grid.addstr(letter + status)

            bold = boldnesses.get((x + 1, y)) in ('topright', 'vertical')
            edge = EDGES['vertical'][bold]
            self.main_grid.addstr(edge)

        y = self.height
        for x in range(self.width):
            vertex = vertices[y][x]
            bold   = boldnesses.get((x, y)) in ('bottomleft', 'horizontal')
            edge   = EDGES['horizontal'][bold]
            self.main_grid.addstr(vertex + edge * 3)

        vertex = vertices[y][x + 1]
        self.main_grid.addstr(vertex)

        self.main_grid.refresh()

    def render_clue_grids(self):
        nrows = self.height * 2

        for direction, clue_grid in self.clue_grids.items():
            clue_grid.erase()

            lines   = []
            heights = []

            active_clue = self.current_square.clues[direction]

            for index, clue in enumerate(self.clues[direction]):
                active    = clue is active_clue
                render    = clue.render(active)
                attribute = curses.A_BOLD if clue is self.current_clue else curses.A_NORMAL
                lines.extend((line, attribute) for line in render)
                heights.append(len(render))
                if active:
                    active_index = index

            if sum(heights[active_index:]) > nrows: # >= also works
                start   = sum(heights[:active_index])
                section = slice(start, start + nrows)
            else:
                section = slice(-nrows, None)

            for line, attribute in lines[section]:
                clue_grid.addstr(line + '\n', attribute)

            clue_grid.refresh()

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
                elif key == '}':
                    self.skip()
                elif key == '{':
                    self.skip(forward=False)
                elif key == 'r':
                    self.replace()
                elif key == 'x':
                    self.delete()
                elif key == ' ':
                    self.toggle()
                elif key in ('i', 'a'):
                    self.insert()
                elif key == ':':
                    self.type_command()
            # Keys specific to insert mode
            else:
                if key == '\x1b':
                    self.escape()
                elif key == 'j':
                    next_key = self.main_grid.getkey()
                    if next_key == 'k':
                        self.escape()
                    else:
                        self.type('j')
                        self.advance()
                        self.handle(next_key)
                elif key == '\x7f':
                    self.backspace()
                else:
                    self.type(key)
                    self.advance()

    @property
    def current_square(self):
        return self.get(self.x, self.y)

    @property
    def next_square(self):
        if self.direction == 'across':
            return self.get(self.x + 1, self.y)
        return self.get(self.x, self.y + 1)

    @property
    def prev_square(self):
        if self.direction == 'across':
            return self.get(self.x - 1, self.y)
        return self.get(self.x, self.y - 1)

    @property
    def current_clue(self):
        return self.current_square.clues[self.direction]

    def in_range(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x, y):
        if not self.in_range(x, y):
            return None
        return self.squares[y][x]

    def jump(self, square):
        self.x, self.y = square

    def move(self, dx, dy):
        x, y = self.current_square
        x += dx
        y += dy
        while True:
            next_square = self.get(x, y)
            if next_square is None:
                break
            if next_square.is_black():
                x += dx
                y += dy
            else:
                self.jump(next_square)
                break

    def start(self):
        self.jump(self.current_clue.span[0])

    def end(self):
        self.jump(self.current_clue.span[-1])

    def next(self):
        next_clue = self.current_clue.next
        if next_clue is not None:
            self.jump(next_clue.span[0])
        else:
            self.jump(self.clues[self.other_direction][0].span[0])
            self.toggle()

    def prev(self):
        prev_clue = self.current_clue.prev
        if prev_clue is not None:
            self.jump(prev_clue.span[0])
        else:
            self.jump(self.clues[self.other_direction][-1].span[0])
            self.toggle()

    def skip(self, forward=True):
        while True:
            if forward:
                self.advance()
            else:
                self.retreat()
            if (self.current_square.is_empty()
                    and (self.prev_square is None or not self.prev_square.is_empty())):
                break

    def replace(self):
        key = self.main_grid.getkey()
        self.type(key)

    def type(self, key):
        self.current_square.set(key)

    def delete(self):
        self.type(EMPTY)

    @property
    def other_direction(self):
        return 'down' if self.direction == 'across' else 'across'

    def toggle(self):
        self.direction = self.other_direction

    def insert(self):
        self.mode = 'insert'
        self.show_message('-- INSERT --')

    def escape(self):
        self.mode = 'normal'
        self.show_message('')

    def reveal(self):
        self.current_square.reveal()
        self.advance()

    def backspace(self):
        self.retreat()
        self.delete()

    def advance(self):
        next_square = self.next_square
        if next_square is None or next_square.is_black():
            self.next()
            # self.next() already jumps to the start,
            # so there's no need to write self.start() here
            # (compare with retreat() below)
        else:
            self.jump(next_square)

    def retreat(self):
        prev_square = self.prev_square
        if prev_square is None or prev_square.is_black():
            self.prev()
            self.end()
        else:
            self.jump(prev_square)

    def type_command(self):
        curses.echo()      # show characters typed
        curses.curs_set(1) # show cursor

        self.status_line.erase()
        self.status_line.addstr(':')
        command = self.status_line.getstr(0, 1)
        self.execute_command(command)

        curses.noecho()
        curses.curs_set(0)

    def execute_command(self, command):
        command = command.strip().decode()

        if command in ('q', 'quit'):
            self.quit()
        elif command in ('c', 'check'):
            self.check()
        elif command: # not entirely whitespace
            self.show_message(f'Unknown command "{command}"')

    def show_message(self, message):
        self.status_line.erase()
        self.status_line.addstr(message)
        self.status_line.refresh()

    def check(self):
        empty = set()
        wrong = set()

        for row in self.squares:
            for square in row:
                if square.is_black():
                    continue
                empty.add(square.is_empty())
                wrong.add(not (square.is_empty() or square.is_correct()))

        if all(empty):
            self.show_message("There's nothing to check.")
        elif any(wrong):
            self.show_message("At least one square's amiss.")
        elif any(empty):
            self.show_message("You're doing fine.")
        else:
            self.show_message("Congrats! You've finished the puzzle.")

    def quit(self):
        sys.exit()

class Clue:
    def __init__(self, number, span, text):
        self.number = number
        self.span   = span
        self.text   = text
        self.prev   = None
        self.next   = None

    def render(self, active):
        lines    = WRAPPER.wrap(self.text)
        cursor   = '>' if active else ' '
        lines[0] = f'{cursor}{self.number:>2} ' + lines[0][4:]
        return lines

class Square:
    def __init__(self, x, y, answer, buffer):
        self.x      = x
        self.y      = y
        self.answer = answer
        self.buffer = buffer
        self.number = None
        self.clues  = {direction: None for direction in DIRECTIONS}

    def __iter__(self):
        yield self.x
        yield self.y

    def is_black(self):
        return self.answer == BLACK

    def is_empty(self):
        return self.buffer == EMPTY

    def is_correct(self):
        return self.buffer == self.answer

    def set(self, key):
        if key in LETTERS:
            self.buffer = key.upper()
        elif key == EMPTY:
            self.buffer = EMPTY

    def reveal(self):
        self.buffer = self.answer

def parse(filename):
    with open(filename, 'rb') as f:
        f.seek(0x2c) # skip checksums, file magic, etc. for now
        width, height, nclues = struct.unpack('<BBH', f.read(4))
        f.seek(4, 1) # skip unknown bitmask and scrambled tag
        answer, buffer = ([list(f.read(width).decode(ENCODING)) for _ in range(height)]
                          for _ in range(2))
        strings = f.read().decode(ENCODING).removesuffix('\0').split('\0')
        title     = strings[0]
        author    = strings[1]
        copyright = strings[2]
        cluelist  = strings[3:3+nclues]
        notes     = strings[3+nclues:]
        assert len(cluelist) == nclues, f'Expected {nclues} clues, got {len(cluelist)}'
        return Puzzle(answer, buffer, cluelist, title, author, copyright, notes)

if __name__ == '__main__':
    puzzle = parse(sys.argv[1])
    puzzle.run()
