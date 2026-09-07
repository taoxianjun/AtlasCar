import argparse
import os

import torch
from torchvision.models import resnet18
import yaml

from train import export


def arg_parse():
    parser = argparse.ArgumentParser(description='PyTorch Training')
    parser.add_argument('--config', default='config.yaml', type=str, help='config file path (default: config.yaml)')

    return parser.parse_args()


if __name__ == '__main__':
    args = arg_parse()
    with open(args.config, 'r') as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)

    output_dir = config['common']['output_dir']
    onnx_model_name = config['export']['onnx_model_name']
    height = config['common']['height']
    width = config['common']['width']

    model_pth = os.path.join(output_dir, 'lfnet.pth')
    if not os.path.exists(model_pth):
        raise FileNotFoundError('No model was found. Please run train.py first.')

    model = resnet18(pretrained=True)
    model.fc = torch.nn.Linear(512, 1)
    weights = torch.load(model_pth, map_location='cpu')
    model.load_state_dict(weights)

    save_onnx_path = os.path.join(output_dir, config['export']['onnx_model_name'])
    export(model, height, width, save_onnx_path)
