import unittest
import cv2
import torch
import numpy as np
from src.utils.cv_utils import preprocess_image_yolov5,letterbox,clip_coords,scale_coords,non_max_suppression,xyxy2xywh,xywh2xyxy

class TestLetterbox(unittest.TestCase):
    def setUp(self):
        self.image = cv2.imread('test_image.jpg')

    def tearDown(self):
        del self.image

    def test_resize(self):
        # Test that the image is resized correctly
        img, _, _ = letterbox(self.image, new_shape=(640, 640))
        self.assertEqual(img.shape[:2], (640, 640))

    def test_padding(self):
        # Test that the image is padded correctly
        img, _, pad_size = letterbox(self.image, new_shape=(640, 640))
        self.assertEqual(img.shape[:2], (640, 640))
        self.assertEqual(pad_size, (64, 64))

    def test_color(self):
        # Test that the padding color is correct
        img, _, _ = letterbox(self.image, new_shape=(640, 640), color=(255, 0, 0))
        self.assertTrue(np.allclose(img[0, 0], [255, 0, 0]))

    def test_scaleup(self):
        # Test that the image is not scaled up when scaleup=False
        img, _, _ = letterbox(self.image, new_shape=(1280, 1280), scaleup=False)
        self.assertEqual(img.shape[:2], (853, 1280))

    def test_scalefill(self):
        # Test that the image is stretched when scaleFill=True
        img, _, _ = letterbox(self.image, new_shape=(1280, 1280), scaleFill=True)
        self.assertEqual(img.shape[:2], (1280, 1280))


class TestPreprocessImageYolov5(unittest.TestCase):
    def setUp(self):
        self.image = np.random.randint(0, 255, size=(480, 640, 3), dtype=np.uint8)
        self.cfg = {'input_shape': (640, 640)}

    def tearDown(self):
        del self.image
        del self.cfg

    def test_letterbox(self):
        # Test that letterbox resizes the image correctly
        img, scale_ratio, pad_size = letterbox(self.image, new_shape=self.cfg['input_shape'])
        self.assertEqual(img.shape[:2], self.cfg['input_shape'])
        # self.assertGreater(scale_ratio, 0)
        # self.assertGreaterEqual(pad_size, 0)

    def test_bgr2rgb(self):
        # Test that bgr2rgb converts the image from BGR to RGB correctly
        img, scale_ratio, pad_size = letterbox(self.image, new_shape=self.cfg['input_shape'])
        img_rgb, _, _ = preprocess_image_yolov5(self.image, self.cfg, bgr2rgb=True)
        self.assertTrue(np.array_equal(img, img_rgb))

    def test_transpose(self):
        # Test that transpose converts the image from HWC to CHW correctly
        img, scale_ratio, pad_size = letterbox(self.image, new_shape=self.cfg['input_shape'])
        img_chw, _, _ = preprocess_image_yolov5(self.image, self.cfg, bgr2rgb=True)
        self.assertEqual(img_chw.shape, (3, self.cfg['input_shape'][0], self.cfg['input_shape'][1]))

    def test_ascontiguousarray(self):
        # Test that ascontiguousarray converts the image to a contiguous array correctly
        img, scale_ratio, pad_size = letterbox(self.image, new_shape=self.cfg['input_shape'])
        img_contig, _, _ = preprocess_image_yolov5(self.image, self.cfg, bgr2rgb=True)
        self.assertTrue(np.allclose(img, img_contig))

    def test_normalize(self):
        # Test that normalize scales the image correctly
        img, scale_ratio, pad_size = letterbox(self.image, new_shape=self.cfg['input_shape'])
        img_norm, _, _ = preprocess_image_yolov5(self.image, self.cfg, bgr2rgb=True)
        self.assertTrue(np.allclose(img_norm, img / 255.0))

class TestXyxy2Xywh(unittest.TestCase):
    def setUp(self):
        self.boxes = np.array([[100, 200, 300, 400], [50, 100, 150, 200]])
        self.expected_output = np.array([[200, 300, 200, 200], [100, 150, 100, 100]])

    def tearDown(self):
        del self.boxes
        del self.expected_output

    def test_numpy_input(self):
        # Test that the function works with numpy input
        output = xyxy2xywh(self.boxes)
        self.assertTrue(np.allclose(output, self.expected_output))

    def test_tensor_input(self):
        # Test that the function works with tensor input
        boxes_tensor = torch.from_numpy(self.boxes)
        output = xyxy2xywh(boxes_tensor)
        self.assertTrue(torch.allclose(output, torch.from_numpy(self.expected_output)))

class TestNonMaxSuppression(unittest.TestCase):
    def setUp(self):
        self.prediction = torch.tensor([
            [
                [100, 200, 300, 400, 0.9, 0.1, 0.0],
                [50, 100, 150, 200, 0.8, 0.2, 1.0],
                [200, 300, 400, 500, 0.7, 0.3, 2.0],
            ],
            [
                [10, 20, 30, 40, 0.6, 0.4, 0.0],
                [20, 30, 40, 50, 0.5, 0.5, 1.0],
                [30, 40, 50, 60, 0.4, 0.6, 2.0],
            ]
        ])
        self.expected_output = [
            torch.tensor([
                [100, 200, 300, 400, 0.9, 0.1, 0.0],
                [50, 100, 150, 200, 0.8, 0.2, 1.0],
                [200, 300, 400, 500, 0.7, 0.3, 2.0],
            ]),
            torch.tensor([
                [20, 30, 40, 50, 0.5, 0.5, 1.0],
                [30, 40, 50, 60, 0.4, 0.6, 2.0],
            ])
        ]

    def tearDown(self):
        del self.prediction
        del self.expected_output

    def test_basic_functionality(self):
        # Test that the function works with basic inputs
        output = non_max_suppression(self.prediction)
        self.assertEqual(len(output), len(self.expected_output))
        for i in range(len(output)):
            self.assertTrue(torch.allclose(output[i], self.expected_output[i]))

    def test_conf_threshold(self):
        # Test that the function filters out boxes with confidence below the threshold
        output = non_max_suppression(self.prediction, conf_thres=0.8)
        self.assertEqual(len(output), len(self.expected_output))
        for i in range(len(output)):
            self.assertTrue(torch.allclose(output[i], self.expected_output[i][:1]))

    def test_iou_threshold(self):
        # Test that the function filters out overlapping boxes with IoU above the threshold
        output = non_max_suppression(self.prediction, iou_thres=0.5)
        self.assertEqual(len(output), len(self.expected_output))
        for i in range(len(output)):
            self.assertTrue(torch.allclose(output[i], self.expected_output[i][1:]))

    def test_classes(self):
        # Test that the function filters out boxes with classes not in the specified list
        output = non_max_suppression(self.prediction, classes=[1])
        self.assertEqual(len(output), len(self.expected_output))
        for i in range(len(output)):
            self.assertTrue(torch.allclose(output[i], self.expected_output[i][1:2]))

class TestXywh2Xyxy(unittest.TestCase):
    def setUp(self):
        self.boxes = np.array([[100, 200, 300, 400], [50, 100, 150, 200]])
        self.expected_output = np.array([[50, 0, 350, 400], [25, 0, 175, 200]])

    def tearDown(self):
        del self.boxes
        del self.expected_output

    def test_numpy_input(self):
        # Test that the function works with numpy input
        output = xywh2xyxy(self.boxes)
        self.assertTrue(np.allclose(output, self.expected_output))

    def test_tensor_input(self):
        # Test that the function works with tensor input
        boxes_tensor = torch.from_numpy(self.boxes)
        output = xywh2xyxy(boxes_tensor)
        self.assertTrue(torch.allclose(output, torch.from_numpy(self.expected_output)))

class TestScaleCoords(unittest.TestCase):
    def setUp(self):
        self.img1_shape = (800, 1200)
        self.coords = np.array([[100, 200, 300, 400], [50, 100, 150, 200]])
        self.img0_shape = (600, 900)
        self.expected_output = np.array([[50, 100, 150, 200], [25, 50, 75, 100]])

    def tearDown(self):
        del self.img1_shape
        del self.coords
        del self.img0_shape
        del self.expected_output

    def test_basic_functionality(self):
        # Test that the function works with basic inputs
        output = scale_coords(self.img1_shape, self.coords, self.img0_shape)
        self.assertTrue(np.allclose(output, self.expected_output))

    def test_ratio_pad(self):
        # Test that the function works with ratio_pad input
        ratio_pad = ((0.5, 0.5), (100, 200))
        output = scale_coords(self.img1_shape, self.coords, self.img0_shape, ratio_pad=ratio_pad)
        expected_output = np.array([[0, 0, 150, 200], [-25, -50, 25, 50]])
        self.assertTrue(np.allclose(output, expected_output))

class TestClipCoords(unittest.TestCase):
    def setUp(self):
        self.boxes = np.array([[100, 200, 1300, 800], [50, 100, 150, 200]])
        self.shape = (800, 1200)
        self.expected_output = np.array([[100, 200, 1200, 800], [50, 100, 150, 200]])

    def tearDown(self):
        del self.boxes
        del self.shape
        del self.expected_output

    def test_numpy_input(self):
        # Test that the function works with numpy input
        output = clip_coords(self.boxes, self.shape)
        self.assertTrue(np.allclose(torch.tensor(output), self.expected_output))

    def test_tensor_input(self):
        # Test that the function works with tensor input
        boxes_tensor = torch.from_numpy(self.boxes)
        shape_tensor = torch.tensor(self.shape)
        output = clip_coords(boxes_tensor, shape_tensor)
        self.assertTrue(torch.allclose(torch.tensor(output), torch.from_numpy(self.expected_output)))

if __name__ == '__main__':
    unittest.main()