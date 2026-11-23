import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import locate_label


class LocateLabelTests(unittest.TestCase):
    def test_uses_a_loaded_holo_and_only_the_image_and_label(self):
        status = {"running": [{"model": "holo", "state": "ready"}]}
        answer = {"choices": [{"message": {"content": '{"found":true,"x":517,"y":876}'}}]}
        with patch.object(locate_label, "request_json", side_effect=[status, answer]) as request:
            self.assertEqual(locate_label.locate("data:image/jpeg;base64,AAA", "Confirm"), (517, 876))
        self.assertEqual(request.call_args_list[0].args, ("/running", 2))
        self.assertEqual(request.call_args.args[:2], ("/v1/chat/completions", 15))
        payload = request.call_args.args[2]
        self.assertEqual(payload["model"], "holo")
        self.assertFalse(payload["chat_template_kwargs"]["enable_thinking"])
        self.assertEqual(len(payload["messages"]), 1)
        self.assertIn(json.dumps("Confirm"), payload["messages"][0]["content"][1]["text"])

    def test_does_not_load_another_model_or_accept_an_invalid_point(self):
        status = {"running": [{"model": "nex25", "state": "ready"}]}
        with patch.object(locate_label, "request_json", return_value=status) as request:
            with self.assertRaises(ValueError):
                locate_label.locate("image", "Confirm")
            request.assert_called_once_with("/running", 2)
        status["running"][0]["model"] = "holo"
        for point in ([], {"found": False, "x": 0, "y": 0}, {"found": True, "x": 1001, "y": 0},
                      {"found": True, "x": True, "y": 0}):
            with self.subTest(point=point):
                answer = {"choices": [{"message": {"content": json.dumps(point)}}]}
                with patch.object(locate_label, "request_json", side_effect=[status, answer]):
                    with self.assertRaises(ValueError):
                        locate_label.locate("image", "Confirm")

    def test_rejects_outside_paths_symlinks_and_stale_snapshots_before_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            shots = Path(directory)
            image = shots / "0001.png"
            image.write_bytes(b"image")
            past = time.time() - 181
            os.utime(image, (past, past))
            (shots / "0002.png").symlink_to(image)
            with patch.object(locate_label, "SHOTS_DIR", shots), patch.object(locate_label, "data_url") as encode:
                for token in ("../private", "0001", "0002"):
                    with self.subTest(token=token), self.assertRaises((OSError, ValueError)):
                        locate_label.shot_data(token)
                encode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
