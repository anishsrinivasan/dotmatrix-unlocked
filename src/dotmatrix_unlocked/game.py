"""Games for the 32x32 panel. Pure logic + frames; the daemon drives tick() and feeds key().
Keys: up, down, left, right, action. A Bluetooth frame takes ~35ms, so ~15-20 fps is the ceiling.
To add a game: subclass Game (step, on_key, draw) and add it to GAMES."""
import random
import time

from . import render
IDLE_SECS = 60  # no input for this long -> game ends, display goes back to the skin


class Game:
    title, help, color, interval = "", "", (255, 255, 255), 0.2
    action = ""  # label for the action button (Space); empty = game doesn't use it

    def __init__(self, seed=None):
        self.rnd = random.Random(seed)
        self.score, self.over = 0, False
        self.last_step = self.last_input = time.monotonic()

    def key(self, k: str) -> None:
        self.last_input = time.monotonic()
        if not self.over:
            self.on_key(k)

    def tick(self) -> bool:
        """Advance if due. Returns False once the game should be dropped (idle)."""
        now = time.monotonic()
        if not self.over and now - self.last_step >= self.interval:
            self.step()
            self.last_step = now
        return now - self.last_input < IDLE_SECS

    def frame(self):
        img = render.blank()
        if self.over:
            for i, s in enumerate(("GAME", "OVER", str(self.score))):
                render.draw_text(img, (32 - render.text_width(s)) // 2, 6 + i * 7, s,
                                 render.SPOTIFY if i == 2 else (235, 60, 60))
        else:
            self.draw(img.load())
        return img

    def step(self): ...
    def on_key(self, k): ...
    def draw(self, px): ...


def _rect(px, x, y, w, h, c):
    for dx in range(w):
        for dy in range(h):
            if 0 <= x + dx < 32 and 0 <= y + dy < 32:
                px[x + dx, y + dy] = c


def _digits(px, x, y, s, c):
    for i, ch in enumerate(s):
        for r in range(5):
            for col in range(3):
                if render.FONT[ch][r * 3 + col] == "1":
                    px[x + i * 4 + col, y + r] = c


# ---- Snake: 16x16 grid of 2x2 cells, walls wrap
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class Snake(Game):
    title, help, color = "SNAKE", "Arrows steer. Walls wrap.", (60, 220, 90)
    N = 16

    def __init__(self, seed=None):
        super().__init__(seed)
        self.body = [(8, 8), (7, 8), (6, 8)]
        self.dir, self.queue = (1, 0), []  # queued turns so two quick taps both land
        self.food = self._place()

    def _place(self):
        free = [(x, y) for x in range(self.N) for y in range(self.N) if (x, y) not in self.body]
        return self.rnd.choice(free) if free else None

    @property
    def interval(self):  # speeds up as it grows
        return max(0.09, 0.22 - self.score * 0.005)

    def on_key(self, k):
        d, last = DIRS.get(k), (self.queue[-1] if self.queue else self.dir)
        if d and d != last and d != (-last[0], -last[1]) and len(self.queue) < 3:
            self.queue.append(d)

    def step(self):
        if self.queue:
            self.dir = self.queue.pop(0)
        (hx, hy), (dx, dy) = self.body[0], self.dir
        head = ((hx + dx) % self.N, (hy + dy) % self.N)
        grow = head == self.food
        body = self.body if grow else self.body[:-1]
        if head in body:
            self.over = True
            return
        self.body = [head] + body
        if grow:
            self.score += 1
            self.food = self._place()
            self.over = self.food is None  # filled the board

    def draw(self, px):
        if self.food:
            _rect(px, self.food[0] * 2, self.food[1] * 2, 2, 2, (235, 50, 50))
        for i, (x, y) in enumerate(self.body):
            _rect(px, x * 2, y * 2, 2, 2, (180, 255, 120) if i == 0 else (30, max(90, 215 - i * 6), 60))


# ---- Tetris: 10x16 board of 2x2 cells on the left, next piece + score on the right
SHAPES = {
    "I": ([(0, 1), (1, 1), (2, 1), (3, 1)], (0, 220, 230)), "O": ([(1, 0), (2, 0), (1, 1), (2, 1)], (240, 220, 0)),
    "T": ([(1, 0), (0, 1), (1, 1), (2, 1)], (190, 60, 230)), "S": ([(1, 0), (2, 0), (0, 1), (1, 1)], (40, 220, 60)),
    "Z": ([(0, 0), (1, 0), (1, 1), (2, 1)], (240, 50, 50)), "J": ([(0, 0), (0, 1), (1, 1), (2, 1)], (50, 90, 255)),
    "L": ([(2, 0), (0, 1), (1, 1), (2, 1)], (255, 140, 0)),
}


class Tetris(Game):
    title, help, color, action = "TETRIS", "Left/right move, up rotates, down drops faster.", (190, 60, 230), "Drop"
    W, H = 10, 16

    def __init__(self, seed=None):
        super().__init__(seed)
        self.board, self.lines = {}, 0
        self.next = self.rnd.choice(list(SHAPES))
        self._spawn()

    @property
    def interval(self):
        return max(0.1, 0.5 - self.lines * 0.02)

    def _spawn(self):
        self.kind, self.next = self.next, self.rnd.choice(list(SHAPES))
        self.cells, self.px, self.py = SHAPES[self.kind][0], 3, 0
        self.over = not self._fits(self.cells, self.px, self.py)

    def _fits(self, cells, px, py):
        return all(0 <= px + x < self.W and py + y < self.H and (px + x, py + y) not in self.board for x, y in cells)

    def _move(self, dx, dy, cells=None):
        cells = cells or self.cells
        if self._fits(cells, self.px + dx, self.py + dy):
            self.cells, self.px, self.py = cells, self.px + dx, self.py + dy
            return True
        return False

    def on_key(self, k):
        if k in ("left", "right"):
            self._move(-1 if k == "left" else 1, 0)
        elif k == "down":
            self.step()
        elif k == "up" and self.kind != "O":
            n = 4 if self.kind == "I" else 3
            rot = [(n - 1 - y, x) for x, y in self.cells]
            any(self._move(dx, 0, rot) for dx in (0, -1, 1, -2, 2))  # wall kicks
        elif k == "action":
            while self._move(0, 1):
                pass
            self.step()

    def step(self):
        if self._move(0, 1):
            return
        color = SHAPES[self.kind][1]
        for x, y in self.cells:
            self.board[(self.px + x, self.py + y)] = color
        full = [y for y in range(self.H) if all((x, y) in self.board for x in range(self.W))]
        for y in full:  # rows are cleared top-down, so shifting by one per cleared row stays correct
            self.board = {(bx, by + (1 if by < y else 0)): c for (bx, by), c in self.board.items() if by != y}
        self.lines += len(full)
        self.score += (0, 1, 3, 5, 8)[len(full)]
        self._spawn()

    def draw(self, px):
        _rect(px, 20, 0, 1, 32, (45, 45, 60))
        for (x, y), c in self.board.items():
            _rect(px, x * 2, y * 2, 2, 2, c)
        for x, y in self.cells:
            _rect(px, (self.px + x) * 2, (self.py + y) * 2, 2, 2, SHAPES[self.kind][1])
        cells, c = SHAPES[self.next]
        for x, y in cells:
            _rect(px, 22 + x * 2, 2 + y * 2, 2, 2, c)
        for i, ch in enumerate(str(self.score)[-3:]):  # score stacked bottom right, one digit per row
            _digits(px, 24, 13 + i * 6, ch, (200, 200, 210))


# ---- 2048: 4x4 tiles of 7x7, the number shown as its power of two (1=2, 2=4 ... 11=2048)
TILE = [(60, 60, 70), (238, 228, 218), (237, 224, 200), (242, 177, 121), (245, 149, 99), (246, 124, 95),
        (246, 94, 59), (237, 207, 114), (237, 204, 97), (237, 200, 80), (237, 197, 63), (237, 194, 46)]


class Twenty48(Game):
    title, help, color = "2048", "Arrows slide. Tiles show the power of two: 11 = 2048.", (237, 194, 46)
    interval = 3600  # turn-based: nothing happens between moves

    def __init__(self, seed=None):
        super().__init__(seed)
        self.g = [[0] * 4 for _ in range(4)]  # exponents, 0 = empty
        self._add(); self._add()

    def _add(self):
        free = [(x, y) for y in range(4) for x in range(4) if not self.g[y][x]]
        if free:
            x, y = self.rnd.choice(free)
            self.g[y][x] = 2 if self.rnd.random() < 0.1 else 1

    def _slide(self, row):
        vals, out, i = [v for v in row if v], [], 0
        while i < len(vals):
            if i + 1 < len(vals) and vals[i] == vals[i + 1]:
                out.append(vals[i] + 1)
                self.score += 2 ** (vals[i] + 1)
                i += 2
            else:
                out.append(vals[i])
                i += 1
        return out + [0] * (4 - len(out))

    def on_key(self, k):
        if k not in DIRS:
            return
        cols = k in ("up", "down")
        g = [list(c) for c in zip(*self.g)] if cols else self.g
        g = [self._slide(r[::-1])[::-1] if k in ("right", "down") else self._slide(r) for r in g]
        g = [list(c) for c in zip(*g)] if cols else g
        if g != self.g:
            self.g = g
            self._add()
        self.over = not (any(not v for r in self.g for v in r) or any(
            self.g[y][x] == self.g[y][x + 1] or self.g[x][y] == self.g[x + 1][y] for y in range(4) for x in range(3)))

    def draw(self, px):
        for y in range(4):
            for x in range(4):
                v = self.g[y][x]
                _rect(px, x * 8, y * 8, 7, 7, TILE[min(v, 11)])
                if v:
                    s = str(v)
                    _digits(px, x * 8 + (7 - render.text_width(s)) // 2, y * 8 + 1, s,
                            (90, 80, 70) if v < 3 else (255, 255, 255))


# ---- Breakout: paddle at the bottom, 4 rows of bricks, 3 lives
class Breakout(Game):
    title, help, color = "BREAKOUT", "Left/right move the paddle. 3 lives.", (240, 120, 40)
    interval = 0.06
    ROWS = [(240, 50, 50), (255, 140, 0), (240, 220, 0), (40, 220, 60)]

    def __init__(self, seed=None):
        super().__init__(seed)
        self.paddle, self.lives = 13, 3
        self._bricks()
        self._serve()

    def _bricks(self):
        self.bricks = {(bx, by) for bx in range(8) for by in range(4)}  # 3x1 px each, rows at y=3,5,7,9

    def _serve(self):
        self.x, self.y = self.paddle + 3.0, 28.0
        self.vx, self.vy = self.rnd.choice((-0.7, 0.7)), -0.8

    def on_key(self, k):
        if k in ("left", "right"):
            self.paddle = max(0, min(26, self.paddle + (-3 if k == "left" else 3)))

    def step(self):
        x, y = self.x + self.vx, self.y + self.vy
        if not 0 <= x < 32:
            self.vx, x = -self.vx, min(31.9, max(0.0, x))
        if y < 0:
            self.vy, y = -self.vy, 0.0
        b = (int(x) // 4, (int(y) - 3) // 2)
        if 3 <= y < 11 and b in self.bricks:
            self.bricks.discard(b)
            self.score += 1
            self.vy = -self.vy
            if not self.bricks:
                self._bricks()
                self.vy *= 1.1  # next level, a bit faster
        if self.vy > 0 and 29 <= y < 31 and self.paddle - 1 <= x < self.paddle + 7:
            off = (x - self.paddle - 3) / 3.5  # -1..1: angle from where it hit
            self.vx, self.vy, y = off, -abs(self.vy), 29.0
        self.x, self.y = x, y
        if y >= 32:
            self.lives -= 1
            self.over = self.lives == 0
            self._serve()

    def draw(self, px):
        for bx, by in self.bricks:
            _rect(px, bx * 4, 3 + by * 2, 3, 1, self.ROWS[by])
        for i in range(self.lives):
            px[31 - i * 2, 0] = (235, 50, 50)
        _rect(px, self.paddle, 30, 6, 1, (200, 200, 210))
        px[int(self.x), int(self.y)] = (255, 255, 255)


# ---- Flappy: any key flaps
class Flappy(Game):
    title, help, color, action = "FLAPPY", "Any key flaps.", (240, 220, 0), "Flap"
    interval = 0.07
    GAP = 11

    def __init__(self, seed=None):
        super().__init__(seed)
        self.y, self.vy = 14.0, 0.0
        self.pipes = [[34, 10], [52, 14]]  # x, gap top

    def on_key(self, k):
        self.vy = -1.5

    def step(self):
        self.vy = min(2.0, self.vy + 0.3)
        self.y += self.vy
        for p in self.pipes:
            p[0] -= 1
            if p[0] == 6:  # pipe passed the bird
                self.score += 1
        if self.pipes[0][0] < -3:
            self.pipes.pop(0)
            self.pipes.append([self.pipes[-1][0] + 18, self.rnd.randint(3, 32 - self.GAP - 3)])
        by = int(self.y)
        hit = any(p[0] <= 9 and p[0] + 3 > 8 and not p[1] <= by < p[1] + self.GAP - 1 for p in self.pipes)
        self.over = hit or not 0 <= self.y < 31

    def draw(self, px):
        _rect(px, 0, 31, 32, 1, (90, 60, 30))
        for x, top in self.pipes:
            _rect(px, x, 0, 3, top, (40, 200, 60))
            _rect(px, x, top + self.GAP, 3, 31 - top - self.GAP, (40, 200, 60))
        _rect(px, 8, int(self.y), 2, 2, (250, 220, 0))


GAMES = {"snake": Snake, "tetris": Tetris, "breakout": Breakout, "2048": Twenty48, "flappy": Flappy}


def attract(name: str):
    """Title screen for the Games skin: the starting board, dimmed, with the name on top."""
    cls = GAMES[name]
    img = cls(seed=0).frame().point(lambda v: v // 4)
    render.draw_text(img, (32 - render.text_width(cls.title)) // 2, 13, cls.title, cls.color)
    return img


if __name__ == "__main__":
    g = Snake(seed=1)
    g.food = (9, 8)
    g.step()
    assert g.score == 1 and len(g.body) == 4 and g.body[0] == (9, 8)
    g.key("left")  # reversing into yourself is ignored
    assert g.queue == []
    g.key("up"); g.key("left")
    g.step(); g.step()
    assert g.body[0] == (8, 7) and not g.over
    g.body, g.dir, g.food = [(5, 5), (6, 5), (6, 6), (5, 6), (4, 6), (4, 5)], (-1, 0), (0, 0)
    g.key("down"); g.step()  # into its own body
    assert g.over and g.frame().getbbox()
    w = Snake(seed=2); w.body = [(15, 0), (14, 0), (13, 0)]; w.food = (5, 5); w.step()
    assert w.body[0] == (0, 0)  # wraps

    t = Tetris(seed=3)
    t.board = {(x, 15): (1, 1, 1) for x in range(10) if x not in (3, 4, 5, 6)}
    t.kind, t.cells, t.px, t.py = "I", SHAPES["I"][0], 3, 0  # horizontal I fills the gap
    t.key("action")
    assert t.lines == 1 and t.score == 1 and not any(y == 15 for _, y in t.board)
    t.key("up")
    assert len(t.cells) == 4

    z = Twenty48(seed=4)
    z.g = [[1, 1, 2, 0], [0] * 4, [0] * 4, [0] * 4]
    z.key("left")
    assert z.g[0][:2] == [2, 2] and z.score == 4
    z.g = [[1, 2, 1, 2], [2, 1, 2, 1], [1, 2, 1, 2], [2, 1, 2, 3]]
    z.key("left")
    assert z.over

    b = Breakout(seed=5)
    b.x, b.y, b.vx, b.vy = 1.5, 4.5, 0.0, -1.0
    b.step()
    assert b.score == 1 and (0, 0) not in b.bricks
    b.x, b.y, b.vx, b.vy = 10.0, 31.5, 0.0, 1.0
    b.paddle = 20
    b.step()
    assert b.lives == 2

    f = Flappy(seed=6)
    for _ in range(40):
        f.step()
    assert f.over  # never flapped -> fell
    for name in GAMES:
        assert GAMES[name](seed=0).frame().getbbox() and attract(name).getbbox(), name
    print("ok")
