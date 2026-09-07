import cv2
import numpy as np

from src.models.bsae_model import Model


class DetCls(Model):
    def __init__(self, model_path, acl_init=True):
        super().__init__(model_path, acl_init)
        self.name = ['left', 'right', 'stop', 'aournd']

    def infer(self, inputs):
        image = cv2.resize(inputs, (64, 64))
        inputs = np.ascontiguousarray(np.expand_dims(image, axis=0).transpose(0, 3, 1, 2)).astype(np.float32) / 255
        result = self.execute([inputs])
        result = self.name[np.argmax(result)]
        return result
