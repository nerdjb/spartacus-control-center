"""Undo stack and daemon-parity curve math tests."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "gui"))

from core.lcd.model import LcdLayout, TextElement
from core.lcd.undo import UndoStack
from core.hardware.curves import (
    PUMP_DUTY_FLOOR,
    apply_pump_floor,
    evaluate_curve,
    sanitize_points,
)


class TestUndoStack(unittest.TestCase):
    def test_undo_redo_roundtrip(self):
        layout = LcdLayout(name="v1")
        stack = UndoStack()
        stack.push(layout.to_dict())
        layout.name = "v2"
        restored = stack.undo(layout.to_dict())
        self.assertIsNotNone(restored)
        self.assertEqual(restored["name"], "v1")
        redone = stack.redo(restored)
        self.assertIsNotNone(redone)
        self.assertEqual(redone["name"], "v2")

    def test_empty_stack_returns_none(self):
        stack = UndoStack()
        self.assertIsNone(stack.undo({"a": 1}))
        self.assertIsNone(stack.redo({"a": 1}))

    def test_push_clears_redo_branch(self):
        stack = UndoStack()
        stack.push({"n": 0})
        state = {"n": 1}
        state = stack.undo(state)
        state = {"n": 2}          # diverge after undo
        stack.push(state)
        self.assertFalse(stack.can_redo)

    def test_limit_enforced(self):
        stack = UndoStack(limit=3)
        for i in range(10):
            stack.push({"i": i})
        self.assertEqual(len(stack._undo), 3)
        self.assertEqual(stack._undo[0]["i"], 7)

    def test_layout_element_undo(self):
        layout = LcdLayout()
        el = TextElement(id="t1", name="cpu", x=10, y=10, text="{cpu_temp}")
        layout.add(el)
        stack = UndoStack()
        before = layout.to_dict()
        stack.push(before)
        layout.elements[0].x = 200
        restored = stack.undo(layout.to_dict())
        back = LcdLayout.from_dict(restored)
        self.assertEqual(back.elements[0].x, 10)


class TestCurveMath(unittest.TestCase):
    def test_interpolation_matches_daemon_semantics(self):
        pts = [(30, 30), (50, 60), (70, 100)]
        self.assertEqual(evaluate_curve(pts, 30), 30.0)
        self.assertEqual(evaluate_curve(pts, 50), 60.0)
        self.assertEqual(evaluate_curve(pts, 40), 45.0)
        self.assertEqual(evaluate_curve(pts, 20), 30.0)   # below range → first duty
        self.assertEqual(evaluate_curve(pts, 90), 100.0)  # above range → last duty

    def test_unsorted_input_sorted(self):
        self.assertEqual(evaluate_curve([(70, 100), (30, 30)], 50), 65.0)

    def test_sanitize_sorts_clamps_and_dedupes(self):
        out = sanitize_points([(70, 150), (30, -5), (30, 40)])
        temps = [t for t, _ in out]
        self.assertEqual(temps, sorted(set(temps)))
        for _, d in out:
            self.assertTrue(0 <= d <= 100)

    def test_sanitize_minimum_two_points(self):
        out = sanitize_points([(40, 50)])
        self.assertEqual(len(out), 2)

    def test_pump_floor(self):
        raised = apply_pump_floor([(30, 10), (70, 80)])
        self.assertEqual(raised[0][1], PUMP_DUTY_FLOOR)
        self.assertEqual(raised[1][1], 80)


if __name__ == "__main__":
    unittest.main()
