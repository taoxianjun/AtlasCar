import time
import unittest
from src.actions.base_action import ShiftLeft, Advance, BackUp, CustomAction, Stop, TurnLeft, TurnRight, ShiftRight, \
    Sleep, SetServo, SpinAntiClockwise, SpinClockwise, RightOblique, LeftOblique


class TestShiftLeft(unittest.TestCase):
    def test_init(self):
        # Test with default arguments
        action = ShiftLeft()
        self.assertEqual(action.speed, -1)
        self.assertEqual(action.servo_angle, [-1, -1])
        self.assertEqual(action.update_speed, True)
        self.assertEqual(action.update_servo, True)
        self.assertEqual(action.speed_setting, [-1, 1, 1, -1])

        # Test with non-default arguments
        action = ShiftLeft(speed=30, servo=[90, 90])
        self.assertEqual(action.speed, 30)
        self.assertEqual(action.servo_angle, [90, 90])
        self.assertEqual(action.update_speed, False)
        self.assertEqual(action.update_servo, False)

    def test_fix_speed(self):
        # Test with default motor rating
        action = ShiftLeft(speed=30)
        self.assertEqual(action.speed_setting, [69, -50, -37, 37])

        # Test with custom motor rating
        action.motor_rating = [1.5, 1.2, 1, 1]
        action.fix_speed()
        self.assertEqual(action.speed_setting, [103, -60, -37, 37])

    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [speed, -speed, -speed, speed]
        result = ShiftLeft.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 90
        expected_result = [speed, -speed, -speed, speed]
        result = ShiftLeft.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestAdvance(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test that generate_speed_setting returns the correct speed setting for the Advance action
        speed = 50
        degree = 0
        expected_output = [-50, -50, 50, 50]
        self.assertEqual(Advance.generate_speed_setting(speed, degree), expected_output)


class TestBackUp(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test that generate_speed_setting returns the correct speed setting for the BackUp action
        speed = 50
        degree = 0
        expected_output = [50, 50, -50, -50]
        self.assertEqual(BackUp.generate_speed_setting(speed, degree), expected_output)


class TestCustomAction(unittest.TestCase):
    def test_init(self):
        # Test with default arguments
        action = CustomAction()
        self.assertEqual(action.speed, -1)
        self.assertEqual(action.servo_angle, [-1, -1])
        self.assertEqual(action.update_speed, False)

        # Test with non-default arguments
        action = CustomAction(speed=30, servo=[90, 90], motor_setting=[1, 2, 3, 4])
        self.assertEqual(action.speed, 30)
        self.assertEqual(action.servo_angle, [90, 90])
        self.assertEqual(action.update_speed, False)
        self.assertEqual(action.speed_setting, [1, 2, 3, 4])

    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [0, 0, 0, 0]
        result = CustomAction.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 90
        expected_result = [0, 0, 0, 0]
        result = CustomAction.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestStop(unittest.TestCase):
    def test_init(self):
        # Test with default arguments
        action = Stop()
        self.assertEqual(action.speed, 0)
        self.assertEqual(action.servo_angle, [-1, -1])
        self.assertEqual(action.update_speed, True)
        self.assertEqual(action.speed_setting, [0, 0, 0, 0])

        # Test with non-default arguments
        action = Stop(speed=30, servo=[90, 90])
        self.assertEqual(action.speed, 0)
        self.assertEqual(action.servo_angle, [90, 90])
        self.assertEqual(action.update_speed, False)
        self.assertEqual(action.update_servo, False)
        self.assertEqual(action.speed_setting, [0, 0, 0, 0])

    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [0, 0, 0, 0]
        result = Stop.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 90
        expected_result = [0, 0, 0, 0]
        result = Stop.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestTurnLeft(unittest.TestCase):
    def test_init(self):
        # Test with default arguments
        action = TurnLeft()
        self.assertEqual(action.speed, -1)
        self.assertEqual(action.servo_angle, [-1, -1])
        self.assertEqual(action.update_speed, True)
        self.assertEqual(action.update_servo, True)
        self.assertEqual(action.speed_setting, [1, 1, -1, -1])

        # Test with non-default arguments
        action = TurnLeft(speed=30, degree=0.5)
        self.assertEqual(action.speed, 30)
        self.assertEqual(action.degree, 0.5)
        self.assertEqual(action.update_speed, False)
        self.assertEqual(action.update_servo, True)

    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [-50, -50, 50, 50]
        result = TurnLeft.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 0.3
        expected_result = [-30, -30, 39, 39]
        result = TurnLeft.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestTurnRight(unittest.TestCase):
    def test_init(self):
        # Test with default arguments
        action = TurnRight()
        self.assertEqual(action.speed, -1)
        self.assertEqual(action.servo_angle, [-1, -1])
        self.assertEqual(action.update_speed, True)
        self.assertEqual(action.update_servo, True)
        self.assertEqual(action.speed_setting, [1, 1, -1, -1])

        # Test with non-default arguments
        action = TurnRight(speed=30, degree=0.5)
        self.assertEqual(action.speed, 30)
        self.assertEqual(action.degree, 0.5)
        self.assertEqual(action.update_speed, False)
        self.assertEqual(action.update_servo, True)

    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [-50, -50, 50, 50]
        result = TurnRight.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 0.3
        expected_result = [-39, -39, 30, 30]
        result = TurnRight.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestShiftRight(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [-50, 50, 50, -50]
        result = ShiftRight.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 0.3
        expected_result = [-30, 30, 30, -30]
        result = ShiftRight.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestLeftOblique(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [0, -50, 0, 50]
        result = LeftOblique.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 0.3
        expected_result = [0, -30, 0, 30]
        result = LeftOblique.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestRightOblique(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [-50, 0, 50, 0]
        result = RightOblique.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 0.3
        expected_result = [-30, 0, 30, 0]
        result = RightOblique.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestSpinClockwise(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [-50, -50, -50, -50]
        result = SpinClockwise.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 0.3
        expected_result = [-30, -30, -30, -30]
        result = SpinClockwise.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestSpinAntiClockwise(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test with default degree value
        speed = 50
        expected_result = [50, 50, 50, 50]
        result = SpinAntiClockwise.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default degree value
        speed = 30
        degree = 0.3
        expected_result = [30, 30, 30, 30]
        result = SpinAntiClockwise.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestSetServo(unittest.TestCase):
    def test_generate_speed_setting(self):
        # Test with default arguments
        speed = 50
        expected_result = [0, 0, 0, 0]
        result = SetServo.generate_speed_setting(speed)
        self.assertEqual(result, expected_result)

        # Test with non-default arguments
        speed = 30
        degree = 0.3
        expected_result = [0, 0, 0, 0]
        result = SetServo.generate_speed_setting(speed, degree)
        self.assertEqual(result, expected_result)


class TestSleep(unittest.TestCase):
    def test_init(self):
        # Test with default arguments
        action = Sleep(1)
        self.assertEqual(action.sleep_time, 1)

        # Test with non-default arguments
        action = Sleep(2.5)
        self.assertEqual(action.sleep_time, 2.5)

    def test_call(self):
        # Test that the Sleep action sleeps for the correct amount of time
        action = Sleep(1)
        start_time = time.time()
        action(None, None)
        end_time = time.time()
        self.assertAlmostEqual(end_time - start_time, 1, delta=0.1)


if __name__ == '__main__':
    unittest.main()
