import cv2 
import os
from land_follow import HandCodedLaneFollower
import configparser
import os


def main():    
    lane_follower = HandCodedLaneFollower()
    
    config = configparser.ConfigParser()
    cur_dir_path = os.path.dirname(os.path.realpath(__file__))
    cfg_dir_path = os.path.join(cur_dir_path, "config")
    cfg_file_path = os.path.join(cfg_dir_path, 'auto_label_setting.ini')
    config.read(cfg_file_path)
    data_folder_path = config['DEFAULT']['belabelleddatapath']
    
    img_list = os.listdir(data_folder_path)
    img_list = sorted(img_list, key=lambda x: int(x.split(".")[0]))

    for img_path in img_list:
        file_ind = img_path.split(".")[0]
        if int(file_ind) > 0: # revise
            
            file_full_path = os.path.join(data_folder_path, img_path)
            
            frame = cv2.imread(file_full_path)
            
            combo_image = lane_follower.follow_lane(frame, file_ind)
            cv2.imshow("result", combo_image)
            cv2.waitKey(200)
    cv2.destroyAllWindows()
    

if __name__ == "__main__":
    main()