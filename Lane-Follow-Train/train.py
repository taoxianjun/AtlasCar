import argparse
import math
import os

import torch
import torch.nn as nn
import yaml
from torch.optim.lr_scheduler import CosineAnnealingLR
from torchvision.models import resnet18
from tqdm.auto import tqdm

from utils import prepare_dataset


def resolve_device(req):
    """Resolve the actual torch device from config request.

    req can be:
      - "cpu"            -> force CPU (user explicit choice)
      - "cuda" / "cuda:0"-> use GPU if available, otherwise error out clearly
      - "auto"          -> use CUDA when available, fall back to CPU silently
    """
    print('=' * 20 + 'Device diagnostics' + '=' * 20)
    print(f'torch version      : {torch.__version__}')
    print(f'CUDA built-in      : {torch.version.cuda if torch.version.cuda else "NONE (CPU build)"}')
    print(f'cuda.is_available(): {torch.cuda.is_available()}')
    if torch.cuda.is_available():
        print(f'GPU count          : {torch.cuda.device_count()}')
        print(f'GPU name           : {torch.cuda.get_device_name(0)}')
    print('-' * 50)

    if req == 'cpu':
        return torch.device('cpu')

    if req == 'auto':
        if torch.cuda.is_available():
            print('[device] auto -> using CUDA:0')
            return torch.device('cuda', 0)
        print('[device] auto -> CUDA unavailable, falling back to CPU')
        return torch.device('cpu')

    # explicit cuda request
    if req.startswith('cuda'):
        if not torch.cuda.is_available():
            raise RuntimeError(
                'CUDA requested (' + req + ') but torch.cuda.is_available() is False.\n'
                'Causes: (1) torch is the CPU build (no +cuXXX suffix); '
                '(2) NVIDIA driver not loaded; (3) no GPU.\n'
                'Fix: install a CUDA build of torch, or set device: cpu / auto in config.yaml.'
            )
        return torch.device(req)

    # treat anything else as cpu
    print(f'[device] unknown request "{req}", defaulting to CPU')
    return torch.device('cpu')


def validate(model, val_loader, criterion, device):
    val_loss = 0.
    model.eval()
    for data in tqdm(val_loader):
        inputs, labels = data
        inputs = inputs.to(device)
        labels = labels.to(device)
        labels = labels.unsqueeze(1)

        with torch.no_grad():
            outputs = model(inputs)

        loss = criterion(outputs, labels)
        val_loss += loss.item()
    val_loss /= len(val_loader)

    return val_loss


def train(model, train_loader, criterion, optimizer, scheduler, device):
    running_loss = 0.0
    model.train()
    for data in tqdm(train_loader):
        inputs, labels = data
        inputs = inputs.to(device)
        labels = labels.to(device)
        labels = labels.unsqueeze(1)

        optimizer.zero_grad()

        outputs = model(inputs)
        loss = criterion(outputs, labels)
        loss.backward()

        optimizer.step()
        scheduler.step()

        running_loss += loss.item()

    running_loss /= len(train_loader)
    return running_loss


def export(model, height, width, save_path):
    input_names = ["input"]
    output_names = ["output"]
    dummy_input = torch.randn(1, 3, height, width)
    model.to('cpu')
    model.eval()
    torch.onnx.export(model, dummy_input, save_path, input_names=input_names,
                      output_names=output_names, opset_version=11)
    print('ONNX model exported!')


def main(config):
    dataset_path = config['common']['dataset_path']
    output_dir = config['common']['output_dir']
    os.makedirs(output_dir, exist_ok=True, mode=0o750)

    device = resolve_device(config['train']['device'])
    resume = config['train']['resume']
    num_epoch = config['train']['epoch_num']
    batch_size = config['train']['batch_size']
    lr = config['train']['lr']

    height = config['common']['height']
    width = config['common']['width']

    if not os.path.exists(dataset_path):
        rel_path = os.path.join(os.path.dirname(__file__), dataset_path)
        raise FileNotFoundError(f'The dataset "{rel_path}" was not found')

    train_loader, val_loader = prepare_dataset(dataset_path, batch_size,
                                               height=height,
                                               width=width)

    model = resnet18(pretrained=True)
    model.fc = torch.nn.Linear(512, 1)
    model.to(device)

    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = CosineAnnealingLR(optimizer, T_max=len(train_loader) * num_epoch, eta_min=1e-6)

    if resume:
        model.load_state_dict(torch.load(os.path.join(output_dir, 'lfnet.pth'), map_location=device))
        print("finish loading..")

    save_model_path = os.path.join(output_dir, 'lfnet.pth')
    best_loss = float('inf')
    patience = 10
    no_improve = 0
    print('=' * 20 + 'Start training' + '=' * 20)
    for epoch in range(num_epoch):
        train_loss = train(model, train_loader, criterion, optimizer, scheduler, device)
        val_loss = validate(model, val_loader, criterion, device)
        val_rmse = math.sqrt(val_loss)
        print(f'Epoch {epoch + 1} train_loss: {train_loss:.4f}  '
              f'val_loss: {val_loss:.4f}  val_RMSE: {val_rmse:.2f} deg')

        if val_loss < best_loss - 1e-4:
            best_loss = val_loss
            no_improve = 0
            torch.save(model.state_dict(), save_model_path)
            print('Best model saved')
        else:
            no_improve += 1
            if no_improve >= patience:
                print(f'Early stopping at epoch {epoch + 1} '
                      f'(no val improvement for {patience} epochs).')
                break
        # also keep latest every epoch, so a killed run still leaves a usable model
        torch.save(model.state_dict(), os.path.join(output_dir, 'lfnet_latest.pth'))

    print('=' * 20 + 'Finish training' + '=' * 20)

    if config['export']['to_onnx']:
        # export the BEST model, not the last epoch (cosine LR may end lower)
        best_path = os.path.join(output_dir, 'lfnet.pth')
        if os.path.exists(best_path):
            model.load_state_dict(torch.load(best_path, map_location='cpu'))
            print('Loaded best weights for ONNX export')
        save_onnx_path = os.path.join(output_dir, config['export']['onnx_model_name'])
        export(model, height, width, save_onnx_path)


def arg_parse():
    parser = argparse.ArgumentParser(description='PyTorch Training')
    parser.add_argument('--config', default='config.yaml', type=str, help='config file path (default: config.yaml)')

    return parser.parse_args()


if __name__ == '__main__':
    args = arg_parse()
    with open(args.config, 'r') as f:
        config_dict = yaml.load(f, Loader=yaml.SafeLoader)

    main(config_dict)
