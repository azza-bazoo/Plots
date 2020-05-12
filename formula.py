from collections import namedtuple
from gi.repository import Gtk, Gdk, cairo, Pango, PangoCairo
from enum import Enum

desc = Pango.font_description_from_string("Latin Modern Math 20")
DEFAULT_ASCENT = 10
DEBUG = False
dpi = PangoCairo.font_map_get_default().get_resolution()
CURSOR_WIDTH = 1

class Editor(Gtk.DrawingArea):
    def __init__ (self):
        super().__init__()
        self.cursor = Cursor()
        self.test_expr = ElementList([Paren('('), Radical([]), OperatorAtom('sin'), Atom('a'), Paren(')'), Atom('b'), Atom('c'), Expt([Atom('dasdlaksjdkl')]),
             Paren('('),
             Frac([Radical([Frac([Atom('b')], [Atom('c')]), Atom('y')], [Atom('3')])], [Atom('cab'), Radical([Atom('ab')])]),
             Paren(')')])
        self.test_expr.elements[1].handle_cursor(self.cursor, Direction.NONE)
        self.props.can_focus = True
        self.connect("key-press-event", self.on_key_press)

    def do_draw_cb(self, widget, ctx):
        scale = 2
        ctx.scale(scale, scale)
        self.test_expr.compute_metrics(ctx, MetricContext(self.cursor))
        ctx.translate(0, self.test_expr.ascent)
        self.test_expr.draw(ctx)
        self.set_size_request(self.test_expr.width*scale,
                              (self.test_expr.ascent + self.test_expr.descent)*scale)

    def on_key_press(self, widget, event):
        print(Gdk.keyval_name(event.keyval))
        char = chr(Gdk.keyval_to_unicode(event.keyval))
        if char.isalnum() or char in "+-*.":
            translation = str.maketrans("-*", "−×")
            self.cursor.insert(Atom(char.translate(translation)))
            self.queue_draw()
            return
        if char in "()[]{}":
            self.cursor.insert(Paren(char))
            self.queue_draw()
            return
        if event.keyval == Gdk.KEY_BackSpace:
            self.cursor.backspace()
            self.queue_draw()
            return
        if event.keyval == Gdk.KEY_slash:
            self.cursor.greedy_insert(Frac)
            self.queue_draw()
            return
        if char == "^":
            self.cursor.greedy_insert(Expt)
            self.queue_draw()
            return
        try:
            direction = Direction(event.keyval)
            self.cursor.handle_movement(direction)
            self.queue_draw()
        except ValueError:
            pass

class saved():
    def __init__(self, ctx):
        self.ctx = ctx

    def __enter__(self):
        self.ctx.save()

    def __exit__(self ,exc_type, exc_val, exc_tb):
        self.ctx.restore()
        return False

class MetricContext():
    def __init__(self, cursor=None):
        self.prev = None
        self.paren_stack = []
        self.cursor = cursor

class Cursor():
    def __init__(self):
        self.owner = None

    def reparent(self, new_parent):
        if self.owner:
            self.owner.lose_cursor()
        self.owner = new_parent

    def handle_movement(self, direction):
        self.owner.handle_cursor(self, direction)

    def backspace(self):
        self.owner.backspace(self)

    def insert(self, element):
        self.owner.insert(element)

    def greedy_insert(self, cls):
        self.owner.greedy_insert(cls)

def italify_string(s):
    def italify_char(c):
        if c == 'h':
            return 'ℎ'
        if c.islower():
            return chr(ord(c) - 0x61 + 0x1d44e)
        if c.isupper():
            return chr(ord(c) - 0x41 + 0x1d434)
        return c
    return "".join(italify_char(c) for c in s)

class Direction(Enum):
    UP = Gdk.KEY_Up
    DOWN = Gdk.KEY_Down
    LEFT = Gdk.KEY_Left
    RIGHT = Gdk.KEY_Right
    NONE = 0

class Element():
    """Abstract class describing an element of an equation.

    Implementations must provide ascent, descent
    and width properties, compute_metrics(ctx, metric_ctx) and draw(ctx)."""

    wants_cursor = True
    h_spacing = 2

    def __init__(self, parent):
        self.parent = parent
        self.index_in_parent = None
        self.has_cursor = False

    def font_metrics(self, ctx):
        font = PangoCairo.font_map_get_default().load_font(PangoCairo.create_context(ctx), desc)
        FontMetrics = namedtuple('FontMetrics', ['ascent', 'descent', 'width'])
        m = font.get_metrics()
        sf = (dpi/72.0) / Pango.SCALE
        return FontMetrics(m.get_ascent()*sf, m.get_descent()*sf, m.get_approximate_digit_width()*sf)

    def compute_metrics(self, ctx, metric_ctx):
        """To be run at the end of overriding methods, if they
        wish to have parens scale around them"""
        stack = metric_ctx.paren_stack
        if stack:
            stack[-1].ascent = max(self.ascent, stack[-1].ascent)
            stack[-1].descent = max(self.descent, stack[-1].descent)

    def draw(self, ctx):
        if DEBUG:
            ctx.set_line_width(0.5)
            ctx.set_source_rgba(1, 0, 1 if self.has_cursor else 0, 0.6)
            ctx.rectangle(0, -self.ascent, self.width, self.ascent + self.descent)
            ctx.stroke()
            ctx.set_source_rgba(0,0,0)
        ctx.move_to(0,0)

    def lose_cursor(self):
        self.has_cursor = False

    def handle_cursor(self, cursor, direction, giver=None):
        if self.wants_cursor and (direction is Direction.NONE or not self.has_cursor):
            cursor.reparent(self)
            self.has_cursor = True
        elif self.parent:
            self.parent.handle_cursor(cursor, direction, self)

    def parent_handle_cursor(self, cursor, direction):
        if self.parent:
            self.parent.handle_cursor(cursor, direction, self)

class ElementList(Element):
    def __init__(self, elements=None, parent=None):
        super().__init__(parent)
        self.elements = elements or []
        self.cursor_pos = 0
        for e in self.elements:
            e.parent = self

    def compute_metrics(self, ctx, metric_ctx):
        self.ascent = self.descent = self.width = 0
        metric_ctx = MetricContext(metric_ctx.cursor)
        metric_ctx.prev = self.font_metrics(ctx)
        for i, e in enumerate(self.elements):
            e.index_in_parent = i
            e.compute_metrics(ctx, metric_ctx)
            self.ascent = max(self.ascent, e.ascent)
            self.descent = max(self.descent, e.descent)
            self.width += e.width + 2*e.h_spacing
            metric_ctx.prev = e
        if not self.elements:
            self.ascent = self.font_metrics(ctx).ascent
            self.descent = self.font_metrics(ctx).descent
            self.width = self.font_metrics(ctx).width

    def draw_cursor(self, ctx, ascent, descent):
        if self.has_cursor:
            ctx.set_source_rgb(0, 0, 0)
            ctx.set_line_width(max(ctx.device_to_user_distance(CURSOR_WIDTH, CURSOR_WIDTH)))
            ctx.move_to(0, descent-2)
            ctx.line_to(0, -ascent+2)
            ctx.move_to(0, 0)
            ctx.stroke()

    def draw(self, ctx):
        super().draw(ctx)
        with saved(ctx):
            ctx.move_to(0,0)
            for i, e in enumerate(self.elements):
                if i == self.cursor_pos:
                    ascent, descent = e.ascent, e.descent
                    if self.cursor_pos > 0:
                        ascent = max(ascent, self.elements[i-1].ascent)
                        descent = max(descent, self.elements[i-1].descent)
                    self.draw_cursor(ctx, ascent, descent)
                ctx.move_to(0, 0)
                ctx.translate(e.h_spacing, 0)
                with saved(ctx):
                    e.draw(ctx)
                ctx.translate(e.width + e.h_spacing, 0)
            if self.cursor_pos == len(self.elements) > 0:
                self.draw_cursor(ctx, self.elements[-1].ascent, self.elements[-1].descent)
            elif not self.elements:
                self.draw_cursor(ctx, self.ascent, self.descent)

    def move_cursor_to(self, cursor, index):
        cursor.reparent(self)
        self.has_cursor = True
        self.cursor_pos = index

    def handle_cursor(self, cursor, direction, giver=None):
        if (direction is Direction.UP or direction is Direction.DOWN) and self.parent and giver:
            self.parent.handle_cursor(cursor, direction, giver=self)
        elif giver:
            if direction is Direction.LEFT:
                self.move_cursor_to(cursor, giver.index_in_parent)
            elif direction is Direction.RIGHT:
                self.move_cursor_to(cursor, giver.index_in_parent+1)
        elif self.has_cursor:
            i = self.cursor_pos
            if direction is Direction.LEFT and i > 0:
                if self.elements[i - 1].wants_cursor:
                    self.elements[i - 1].handle_cursor(cursor, direction)
                else:
                    self.move_cursor_to(cursor, i - 1)
            elif direction is Direction.RIGHT and i < len(self.elements):
                if self.elements[i].wants_cursor:
                    self.elements[i].handle_cursor(cursor, direction)
                else:
                    self.move_cursor_to(cursor, i+1)
            else:
                self.parent_handle_cursor(cursor, direction)
        elif direction is Direction.LEFT:
            self.move_cursor_to(cursor, len(self.elements))
        else:
            self.move_cursor_to(cursor, 0)

    def backspace(self, cursor, caller=None):
        if self.cursor_pos > 0:
            target = self.elements[self.cursor_pos-1]
            if target.wants_cursor:
                target.handle_cursor(cursor, Direction.LEFT, self)
                target.backspace(cursor, self)
            else:
                self.cursor_pos -= 1
                del self.elements[self.cursor_pos]
        elif self.parent:
            self.parent.backspace(cursor, self)

    def replace(self, old, new):
        if old.parent is self:
            if isinstance(new, ElementList):
                self.elements[old.index_in_parent:old.index_in_parent+1] = new.elements
                for e in new.elements:
                    e.parent = self
            else:
                self.elements[old.index_in_parent] = new
                new.parent = self

    def insert(self, element):
        self.elements.insert(self.cursor_pos, element)
        self.cursor_pos += 1
        element.parent = self

    def greedy_insert(self, cls):
        if self.cursor_pos > 0 and cls.greedy_insert_left:
            paren_level = 0
            for n, e in enumerate(self.elements[self.cursor_pos-1::-1]):
                if isinstance(e, Paren):
                    if e.left:
                        paren_level -= 1
                    else:
                        paren_level += 1
                if paren_level <= 0:
                    break
            n += 1
            left = self.elements[self.cursor_pos - n:self.cursor_pos]
            del self.elements[self.cursor_pos - n:self.cursor_pos]
            self.cursor_pos -= n
        else:
            left = []
        if self.cursor_pos < len(self.elements) and cls.greedy_insert_right:
            paren_level = 0
            for n, e in enumerate(self.elements[self.cursor_pos:]):
                if isinstance(e, Paren):
                    if e.left:
                        paren_level += 1
                    else:
                        paren_level -= 1
                if paren_level <= 0:
                    break
            n += 1
            right = self.elements[self.cursor_pos:self.cursor_pos + n]
            del self.elements[self.cursor_pos:self.cursor_pos + n]
        else:
            right = []
        self.insert(cls.make_greedily(left, right))

class BaseAtom(Element):
    wants_cursor = False
    h_spacing = 0

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name

    def compute_metrics(self, ctx, metric_ctx):
        self.layout = PangoCairo.create_layout(ctx)
        self.layout.set_text(self.name)
        self.layout.set_font_description(desc)
        self.width, self.height = self.layout.get_pixel_size()
        self.baseline = self.layout.get_baseline()//Pango.SCALE
        self.ascent = self.baseline
        self.descent = self.height - self.baseline
        super().compute_metrics(ctx, metric_ctx)

    def draw(self, ctx):
        super().draw(ctx)
        ctx.move_to(0, -self.baseline)
        PangoCairo.show_layout(ctx, self.layout)

class Atom(BaseAtom):
    def __init__(self, name, parent=None):
        super().__init__(italify_string(name), parent=parent)

class OperatorAtom(BaseAtom):
    h_spacing = 2

class Expt(Element):
    greedy_insert_right = True
    greedy_insert_left = False

    def __init__(self, exponent=None, parent=None):
        super().__init__(parent)
        self.exponent = ElementList(exponent, self)
        self.exponent_scale = 0.8

    def compute_metrics(self, ctx, metric_ctx):
        self.exponent.compute_metrics(ctx, metric_ctx)
        self.child_shift = -self.exponent.descent*self.exponent_scale - metric_ctx.prev.ascent//2 # -ve y is up
        self.width = self.exponent.width*self.exponent_scale
        self.ascent = self.exponent.ascent*self.exponent_scale - self.child_shift
        self.descent = max(0, metric_ctx.prev.descent,
                           self.exponent.descent*self.exponent_scale + self.child_shift)
        super().compute_metrics(ctx, metric_ctx)

    def draw(self, ctx):
        super().draw(ctx)
        with saved(ctx):
            ctx.translate(0, self.child_shift)
            ctx.scale(self.exponent_scale, self.exponent_scale)
            self.exponent.draw(ctx)

    def handle_cursor(self, cursor, direction, giver=None):
        if giver is self.exponent:
            self.parent.handle_cursor(cursor, direction, self)
        else:
            self.exponent.handle_cursor(cursor, direction)

    def backspace(self, cursor, caller):
        if self.parent and caller is self.exponent:
            self.parent.replace(self, self.exponent)
            self.parent_handle_cursor(cursor, Direction.LEFT)
        elif caller is self.parent is not None:
            self.exponent.backspace(cursor, self)

    @classmethod
    def make_greedily(cls, left, right):
        return cls(exponent=right)
class Frac(Element):
    vertical_separation = 4
    greedy_insert_right = greedy_insert_left = True

    def __init__(self, numerator=None, denominator=None, parent=None):
        super().__init__(parent)
        self.numerator = ElementList(numerator, self)
        self.denominator = ElementList(denominator, self)

    def compute_metrics(self, ctx, metric_ctx):
        self.numerator.compute_metrics(ctx, metric_ctx)
        self.denominator.compute_metrics(ctx, metric_ctx)
        self.width = max(self.numerator.width, self.denominator.width)

        font_ascent = self.font_metrics(ctx).ascent
        self.bar_height = font_ascent * 0.3
        self.ascent = self.numerator.ascent + self.numerator.descent + \
            self.bar_height + self.vertical_separation//2
        self.descent = self.denominator.ascent + self.denominator.descent + \
            self.vertical_separation//2 - self.bar_height
        super().compute_metrics(ctx, metric_ctx)

    def draw(self, ctx):
        super().draw(ctx)
        with saved(ctx):
            ctx.translate(0, -self.bar_height)
            ctx.move_to(0,0)
            ctx.set_line_width(1)
            ctx.line_to(self.width, 0)
            ctx.stroke()
            ctx.move_to(0,0)
            with saved(ctx):
                ctx.translate(self.width//2 - self.numerator.width//2,
                              -self.vertical_separation//2 - self.numerator.descent)
                self.numerator.draw(ctx)
            with saved(ctx):
                ctx.translate(self.width//2 - self.denominator.width//2,
                              self.vertical_separation//2 + self.denominator.ascent)
                self.denominator.draw(ctx)


    def handle_cursor(self, cursor, direction, giver=None):
        if giver is self.numerator and direction is Direction.DOWN:
            self.denominator.handle_cursor(cursor, direction)
        elif giver is self.denominator and direction is Direction.UP:
            self.numerator.handle_cursor(cursor, direction)
        elif giver is self.numerator or giver is self.denominator:
            self.parent.handle_cursor(cursor, direction, self)
        else:
            if direction is Direction.UP:
                self.denominator.handle_cursor(cursor, direction)
            else:
                self.numerator.handle_cursor(cursor, direction)

    def backspace(self, cursor, caller):
        if self.parent and (caller is self.numerator or caller is self.denominator):
            temp = ElementList()
            temp.elements = self.numerator.elements + self.denominator.elements
            self.parent.replace(self, temp)
            #self.denominator.elements[0].handle_cursor(cursor, Direction.LEFT)
            self.parent_handle_cursor(cursor, Direction.LEFT)
        elif caller is self.parent is not None:
            self.numerator.backspace(cursor, self)

    @classmethod
    def make_greedily(cls, left, right):
        return cls(numerator=left, denominator=right)

class Radical(Element):
    def __init__(self, radicand, index=None, parent=None):
        super().__init__(parent)
        self.radicand = ElementList(radicand, self)
        self.index = ElementList(index, self)
        self.overline_space = 4

    def compute_metrics(self, ctx, metric_ctx):
        self.radicand.compute_metrics(ctx, metric_ctx)
        self.index.compute_metrics(ctx, metric_ctx)
        self.symbol = PangoCairo.create_layout(ctx)
        self.symbol.set_text("√")
        self.symbol.set_font_description(desc)
        self.width = self.radicand.width + self.symbol.get_pixel_size().width
        self.ascent = max(self.symbol.get_baseline()//Pango.SCALE,
                          self.radicand.ascent + self.overline_space)
        self.descent = self.radicand.descent
        super().compute_metrics(ctx, metric_ctx)

    def draw(self, ctx):
        super().draw(ctx)
        extents = self.symbol.get_pixel_extents()
        symbol_size = extents.ink_rect.height
        scale_factor = max(1, (self.ascent + self.descent)/symbol_size)
        with saved(ctx):
            ctx.translate(0, -self.ascent)
            ctx.scale(1, scale_factor)
            ctx.translate(0, -extents.ink_rect.y)
            ctx.move_to(0, 0)
            PangoCairo.show_layout(ctx, self.symbol)

        ctx.translate(self.symbol.get_pixel_size().width, 0)
        ctx.set_source_rgb(0,0,0)
        ctx.set_line_width(1)
        ctx.move_to(0, -self.ascent + ctx.get_line_width())
        ctx.rel_line_to(self.radicand.width, 0)
        ctx.stroke()
        ctx.move_to(0,0)
        self.radicand.draw(ctx)

    def handle_cursor(self, cursor, direction, giver=None):
        if giver is self.radicand:
            self.parent_handle_cursor(cursor, direction)
        else:
            self.radicand.handle_cursor(cursor, direction)

    def backspace(self, cursor, caller):
        if caller is self.radicand and self.parent:
            self.parent.replace(self, self.radicand)
            self.parent_handle_cursor(cursor, Direction.LEFT)
        elif caller is self.parent is not None:
            self.radicand.backspace(cursor, self)

class Paren(Element):
    wants_cursor = False
    h_spacing = 0

    def __init__(self, char, parent=None):
        super().__init__(parent)
        if len(char) != 1:
            raise ValueError("{!r} is not a valid paren".format(char))
        if char in "({[":
            self.left = True
        elif char in "]})":
            self.left = False
        else:
            raise ValueError("{!r} is not a valid paren".format(char))
        self.char = char

    def compute_metrics(self, ctx, metric_ctx):
        self.layout = PangoCairo.create_layout(ctx)
        self.layout.set_text(self.char)
        self.layout.set_font_description(desc)
        self.width, self.height = self.layout.get_pixel_size()
        self.baseline = self.layout.get_baseline()//Pango.SCALE
        self.ascent = self.baseline
        self.descent = self.height - self.baseline

        if self.left:
            metric_ctx.paren_stack.append(self)
        else:
            if metric_ctx.paren_stack:
                match = metric_ctx.paren_stack.pop()
            else:
                match = metric_ctx.prev
            self.ascent = match.ascent
            self.descent = match.descent
            super().compute_metrics(ctx, metric_ctx)

    def draw(self, ctx):
        super().draw(ctx)
        extents = self.layout.get_pixel_extents()
        symbol_size = extents.ink_rect.height
        scale_factor = max(1, (self.ascent + self.descent)/symbol_size)
        with saved(ctx):
            ctx.scale(1, scale_factor)
            ctx.translate(0, -self.ascent/scale_factor-extents.ink_rect.y)
            ctx.move_to(0, 0)
            PangoCairo.show_layout(ctx, self.layout)

test_frac = ElementList([Atom('a'), Frac([Atom('b')], [Atom('c')])])