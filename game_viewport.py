"""Aspect-preserving Canvas coordinates, text and sprite scaling."""
import tkinter as tk
from PIL import Image, ImageTk


class GameCanvas(tk.Canvas):
    def __init__(self, master, logical_width, logical_height, **kwargs):
        super().__init__(master, **kwargs)
        self.logical_width = logical_width
        self.logical_height = logical_height
        self.scale_factor = 1.
        self.offset_x = self.offset_y = 0.
        self.view_width = logical_width
        self.view_height = logical_height
        self.scaled_images = {}
        self.bind('<Configure>', self.resize_view)

    def resize_view(self, event):
        self.view_width, self.view_height = event.width, event.height
        scale = min(event.width / self.logical_width, event.height / self.logical_height)
        if scale != self.scale_factor:
            self.scaled_images.clear()
        self.scale_factor = max(.01, scale)
        self.offset_x = (event.width - self.logical_width * self.scale_factor) / 2
        self.offset_y = (event.height - self.logical_height * self.scale_factor) / 2

    def logical_point(self, x, y):
        x = (x - self.offset_x) / self.scale_factor
        y = (y - self.offset_y) / self.scale_factor
        return (x, y) if 0 <= x <= self.logical_width and 0 <= y <= self.logical_height else None

    def _create(self, itemType, args, kw):
        coords = tk._flatten(args)
        scale = self.scale_factor
        coords = tuple(value * scale + (self.offset_x if i % 2 == 0 else self.offset_y)
                       for i, value in enumerate(coords))
        options = dict(kw)
        if 'width' in options:
            options['width'] = max(1, options['width'] * scale)
        if 'font' in options:
            family, size, *style = options['font']
            options['font'] = (family, -max(1, round(abs(size) * scale)), *style)
        if 'image' in options and abs(scale - 1) > .001:
            original = options['image']
            key = str(original)
            if key not in self.scaled_images:
                image = ImageTk.getimage(original)
                size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
                self.scaled_images[key] = ImageTk.PhotoImage(
                    image.resize(size, Image.Resampling.LANCZOS), master=self)
            options['image'] = self.scaled_images[key]
        return super()._create(itemType, coords, options)

    def finish_frame(self):
        # Cover scenery that extends beyond the logical map viewport.
        x, y = self.offset_x, self.offset_y
        w, h = self.view_width, self.view_height
        for box in ((0, 0, x, h), (w-x, 0, w, h), (0, 0, w, y), (0, h-y, w, h)):
            if box[2] > box[0] and box[3] > box[1]:
                super()._create('rectangle', box, {'fill': '#29434A', 'outline': ''})
