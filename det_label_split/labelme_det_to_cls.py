import json
import os
from argparse import ArgumentParser

import cv2


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--dataset_path', type=str, required=True)
    parser.add_argument('--output_path', type=str, required=True)
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    image_list = os.listdir(args.dataset_path)

    index = 0
    for image_name in image_list:

        if not image_name.endswith('jpg'):
            continue
        image = cv2.imread(os.path.join(args.dataset_path, image_name), cv2.IMREAD_COLOR)
        basename, ext = os.path.splitext(image_name)
        with open(os.path.join(args.dataset_path, f'{basename}.json'), 'r') as f:
            info = json.load(f)

        for item in info['shapes']:
            points = item['points']
            print(points)

            sub_img = image[int(points[0][1]):int(points[1][1]), int(points[0][0]):int(points[1][0])]
            print(sub_img.shape)
            save_path = os.path.join(args.output_path, item['label'])
            if not os.path.exists(save_path):
                os.makedirs(save_path, exist_ok=True)
            pp = os.path.join(args.dataset_path, image_name)
            cv2.imwrite(os.path.join(save_path, f'{index}.jpg'), sub_img)
            index += 1
