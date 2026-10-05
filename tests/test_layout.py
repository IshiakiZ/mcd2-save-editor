import unittest

from dungeons2_editor import layout


class Display:
    """All the sizing helpers ask of a window: how big its screen is, and how far Windows scales it up."""

    def __init__(self, width, height, percent=100):
        self.size = (width, height)
        self.percent = percent

    def winfo_fpixels(self, _distance):
        return 96 * self.percent / 100  # pixels to the inch

    def winfo_screenwidth(self):
        return self.size[0]

    def winfo_screenheight(self):
        return self.size[1]


class WindowSizeTests(unittest.TestCase):
    def test_a_size_grows_with_the_displays_scaling(self):
        # Text and buttons are half as big again at 150%, so a window sized for 100% would cut them off.
        self.assertEqual(layout.scaled_size(Display(1920, 1080), 1280, 880), (1280, 880))
        self.assertEqual(layout.scaled_size(Display(2560, 1440, 125), 1280, 880), (1600, 1100))
        self.assertEqual(layout.scaled_size(Display(3840, 2160, 150), 1280, 880), (1920, 1320))
        self.assertEqual(layout.scaled_size(Display(3840, 2160, 200), 960, 640), (1920, 1280))
        self.assertEqual(layout.display_scale(Display(1920, 1080, 75)), 1.0)  # never made smaller

    def test_a_window_is_never_bigger_than_the_screen_has_room_for(self):
        self.assertEqual(layout.screen_room(Display(1920, 1080)), (1880, 1000))
        self.assertEqual(layout.screen_room(Display(1920, 1080, 150)), (1860, 960))  # the taskbar and title bar grow too
        self.assertEqual(layout.scaled_size(Display(1920, 1080, 150), 1280, 880), (1860, 960))
        self.assertEqual(layout.scaled_size(Display(1366, 768), 1280, 880), (1280, 688))  # a small laptop screen at 100%


if __name__ == "__main__":
    unittest.main()
