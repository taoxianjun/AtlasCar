import cv2
from lane_detector import LaneDetector
import logging
import time
import os
from utils.steeer_util import compute_steering_angle, stabilize_steering_angle, display_heading_line

class HandCodedLaneFollower(object):

    def __init__(self):
        self.curr_steering_angle = 90
        self.frame_count = 0
        

        uuid_str = time.strftime("%Y-%m-%d-%H_%M_%S", time.localtime())
        self.dataset_path = "dataset-%s" % uuid_str
        os.makedirs(self.dataset_path)
        self.train_image_path = os.path.join(self.dataset_path, "images")
        os.makedirs(self.train_image_path)
        self.label_path = os.path.join(self.dataset_path, "label.txt")

    def follow_lane(self, frame, cur_file_ind):

        lane_detector = LaneDetector(frame)
        lane_lines, frame_with_lane = lane_detector()
        font = cv2.FONT_HERSHEY_SIMPLEX
        # cv2.putText(frame_with_lane, cur_file_ind, (600,100), font, 3, (0,0,255), 4)
        cv2.putText(frame_with_lane, "Current Image Idx: " + cur_file_ind, (200,100), font, 2, (0,0,255), 2)
        if len(lane_lines) > 1:
            new_steering_angle, final_frame = self.steer(frame_with_lane, lane_lines)
            self.make_dataset(frame, new_steering_angle)
            return final_frame  
        else:
            return frame_with_lane

    def steer(self, frame, lane_lines):
        if len(lane_lines) == 0:
            logging.error('No lane lines detected, nothing to do.')
            return frame

        _, _, new_steering_angle = compute_steering_angle(frame, lane_lines)
        self.curr_steering_angle = stabilize_steering_angle(self.curr_steering_angle, new_steering_angle, len(lane_lines))

        curr_heading_image = display_heading_line(frame, self.curr_steering_angle)
        cv2.putText(curr_heading_image, "steering_angle: "+str(self.curr_steering_angle)+" deg", (100,200), cv2.FONT_HERSHEY_COMPLEX, 2, (0,255,0), 2)

        return new_steering_angle, curr_heading_image
    
    def make_dataset(self, frame, x_offset):
        image_path = os.path.join(self.train_image_path, str(self.frame_count) + ".jpg")
        cv2.imwrite(image_path, frame)
        with open(self.label_path, 'a') as f:
            f.write(str(self.frame_count) + ".jpg " + str(x_offset) + "\n")
        self.frame_count += 1