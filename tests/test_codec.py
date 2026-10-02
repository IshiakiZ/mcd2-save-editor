import unittest

from dungeons2_editor import codec

from .helpers import HERO_TEXT, SETTINGS_TEXT, hero_save_text, shift_encode


class ShiftTests(unittest.TestCase):
    def test_shift_is_reversible_for_every_byte(self):
        every_byte = bytes(range(256))
        self.assertEqual(codec.encode_bytes(codec.decode_bytes(every_byte)), every_byte)
        self.assertEqual(codec.decode_bytes(codec.encode_bytes(every_byte)), every_byte)

    def test_decodes_the_bytes_seen_in_real_saves(self):
        self.assertEqual(codec.decode_bytes(b"z!aknar!"), b'{"blobs"')


class RoundTripTests(unittest.TestCase):
    def test_unedited_blob_encodes_back_to_the_same_bytes(self):
        raw = shift_encode(SETTINGS_TEXT)
        decoded = codec.decode_blob(raw)
        self.assertTrue(decoded.exact)
        self.assertEqual(codec.encode_blob(decoded.document, decoded.style), raw)

    def test_non_ascii_text_round_trips(self):
        raw = shift_encode(HERO_TEXT)
        decoded = codec.decode_blob(raw)
        self.assertEqual(decoded.document["blobs"][0]["heroName"], "Zoë")
        self.assertFalse(decoded.style.ensure_ascii)
        self.assertEqual(codec.encode_blob(decoded.document, decoded.style), raw)

    def test_hero_saves_are_plain_json_with_shortest_numbers(self):
        raw = hero_save_text().encode("utf-8")
        decoded = codec.decode_blob(raw)
        self.assertFalse(decoded.style.shifted)
        self.assertEqual(decoded.style.numbers, "shortest")
        self.assertTrue(decoded.exact)
        self.assertEqual(codec.encode_blob(decoded.document, decoded.style), raw)
        self.assertEqual(codec.dumps({"x": 900.0, "y": 0.218016}, decoded.style), '{"x":900,"y":0.218016}')

    def test_settings_saves_stay_shifted_with_17_digit_numbers(self):
        decoded = codec.decode_blob(shift_encode(SETTINGS_TEXT))
        self.assertTrue(decoded.style.shifted)
        self.assertEqual(decoded.style.numbers, "g17")

    def test_edit_changes_only_that_value(self):
        decoded = codec.decode_blob(shift_encode(SETTINGS_TEXT))
        decoded.document["blobs"][0]["masterVolume"] = 85
        text = codec.decode_bytes(codec.encode_blob(decoded.document, decoded.style)).decode()
        self.assertEqual(text, SETTINGS_TEXT.replace('"masterVolume":60', '"masterVolume":85'))


class FormattingTests(unittest.TestCase):
    def test_numbers_are_printed_like_the_game(self):
        self.assertEqual(codec.dumps(0.35), "0.34999999999999998")
        self.assertEqual(codec.dumps(2.130000114440918), "2.130000114440918")
        self.assertEqual(codec.dumps(60), "60")
        self.assertEqual(codec.dumps(60.0), "60")
        self.assertEqual(codec.dumps(-0.5), "-0.5")

    def test_rejects_values_json_cannot_hold(self):
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                codec.dumps({"x": bad})
        with self.assertRaises(TypeError):
            codec.dumps({"x": {1, 2}})

    def test_top_level_colon_style_is_detected_and_used_only_at_top_level(self):
        style = codec.detect_style('{"blobs" :[]}')
        self.assertEqual(style.top_level_colon, " :")
        self.assertEqual(codec.dumps({"a": {"b": 1}}, style), '{"a" :{"b":1}}')
        self.assertEqual(codec.detect_style('{"a":1}').top_level_colon, ":")

    def test_new_non_ascii_text_is_escaped_in_ascii_files(self):
        style = codec.detect_style('{"a":"b"}')
        self.assertEqual(codec.dumps({"a": "é"}, style), '{"a":"\\u00e9"}')


class DetectionTests(unittest.TestCase):
    def test_encrypted_or_binary_blobs_are_not_documents(self):
        dpapi_like = bytes.fromhex("01000000d08c9ddf0115d1118c7a00c04fc297eb") + bytes(range(200))
        for raw in (dpapi_like, bytes(range(256)), b"", shift_encode("not json")):
            with self.assertRaises(codec.NotASaveDocument):
                codec.decode_blob(raw)


if __name__ == "__main__":
    unittest.main()


class NumberLiteralTests(unittest.TestCase):
    """Numbers are written back as read, unless they were changed."""

    TEXT = '{"Z":4100.0001169648413,"X":15850,"Y":0.218016,"List":[1.5,2.25]}'

    def test_unusual_number_text_survives_a_round_trip(self):
        decoded = codec.decode_blob(self.TEXT.encode())
        self.assertTrue(decoded.exact)
        self.assertEqual(codec.encode_blob(decoded.document, decoded.style).decode(), self.TEXT)

    def test_it_survives_a_deep_copy(self):
        import copy

        decoded = codec.decode_blob(self.TEXT.encode())
        clone = copy.deepcopy(decoded.document)
        self.assertEqual(clone, decoded.document)
        self.assertEqual(codec.encode_blob(clone, decoded.style).decode(), self.TEXT)

    def test_a_changed_number_is_written_in_the_usual_form(self):
        decoded = codec.decode_blob(self.TEXT.encode())
        decoded.document["Z"] = 4100.0001169648413 + 1
        decoded.document["List"][0] = 2.5
        out = codec.encode_blob(decoded.document, decoded.style).decode()
        self.assertEqual(out, '{"Z":4101.000116964841,"X":15850,"Y":0.218016,"List":[2.5,2.25]}')
