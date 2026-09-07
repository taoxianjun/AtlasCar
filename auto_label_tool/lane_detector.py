import logging
from utils.lane_util import detect_edges, region_of_interest, detect_line_segments, average_slope_intercept, display_lines

class LaneDetector:
    def __init__(self, frame, hsv_txt=None) -> None:
        self.frame = frame
        self.hsv_txt = hsv_txt

    def __call__(self):
        logging.debug('detecting lane lines...')

        edges = detect_edges(self.frame, self.hsv_txt)

        cropped_edges = region_of_interest(edges)

        line_segments = detect_line_segments(cropped_edges)

        lane_lines = average_slope_intercept(self.frame, line_segments)
        lane_lines_image = display_lines(self.frame, lane_lines)

        return lane_lines, lane_lines_image