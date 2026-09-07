import cv2
import numpy as np

from src.models.bsae_model import Model


class LFNet(Model):
    def __init__(self, model_path, acl_init=True):
        super().__init__(model_path, acl_init)

    # ImageNet mean/std MUST match Lane-Follow-Train/utils.py get_transforms,
    # otherwise the deployed model receives un-normalized input and predicts wrong.
    MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def infer(self, inputs):
        # BGR -> RGB
        img = inputs[:, :, [2, 1, 0]]
        # resize to (H=180, W=320) to match training A.Resize(180, 320)
        img = cv2.resize(img, (320, 180))
        img = img.astype(np.float32) / 255.0
        # normalize with ImageNet stats (same as training)
        img = (img - self.MEAN) / self.STD
        # HWC -> CHW, then add batch dim -> (1, 3, 180, 320)
        img = img.transpose(2, 0, 1)
        batched_img = np.expand_dims(img, axis=0)
        result = self.execute([np.ascontiguousarray(batched_img)])
        return result
